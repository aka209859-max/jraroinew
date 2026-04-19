#!/usr/bin/env python3
"""
build_reliable_bins.py
======================
1. all_combined_ranking.csv を読み込み、grade A以上の結果を対象に
   analyze_combination を再実行してビン詳細データを取得する。
2. n >= MIN_N かつ win_roi > MIN_ROI のビンを「信頼できる高ROIビン」として抽出。
3. reports/screening/reliable_high_roi_bins.csv に出力。
4. TOP10 の best_bin サンプル数を検証レポートとして表示する。

Usage:
  py -3.12 -m backend.batch.build_reliable_bins [--min-n 100] [--min-roi 120] [--top-n 500] [--grades S A]
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

# ── Reuse factor_screening internals ──────────────────────────────────────────
from backend.batch.factor_screening import (
    load_data,
    load_prev_data,
    load_blood_data,
    compute_derived_factors,
    load_extra_tables_for_full_scan,
    analyze_combination,
    DEFAULT_CEO_ROWS,
    DEFAULT_OUTPUT_DIR,
    ALL_FACTORS,
)

RANKING_CSV = DEFAULT_OUTPUT_DIR / "all_combined_ranking.csv"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _apply_odds_filter(df: pd.DataFrame) -> pd.DataFrame:
    if "tansho_odds" in df.columns:
        odds_int = pd.to_numeric(
            df["tansho_odds"].astype(str).str.strip(), errors="coerce"
        )
        before = len(df)
        df = df[(odds_int >= 10) & (odds_int <= 1000)].copy()
        print(f"[INFO] Odds filter: {before:,} → {len(df):,} rows")
    return df


def _build_seg_dfs(df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """Build a dict of segment_name → sub-DataFrame for fast lookup."""
    segs: Dict[str, pd.DataFrame] = {"GLOBAL": df, "COURSE_27": df}
    if "surface" in df.columns:
        segs["SURFACE_2_芝"] = df[df["surface"] == "芝"]
        segs["SURFACE_2_ダ"] = df[df["surface"] == "ダ"]
    if "keibajo_code" in df.columns and "surface" in df.columns:
        for (kb, surf), sub in df.groupby(["keibajo_code", "surface"]):
            segs[f"KEIBAJO_SURFACE_{kb}_{surf}"] = sub
    return segs


def _load_and_prepare(row_limit: int) -> pd.DataFrame:
    print(f"[INFO] Loading {row_limit:,} rows...")
    df = load_data(limit=row_limit)
    print(f"[INFO] Main data: {len(df):,} rows")
    if df.empty:
        print("[ERROR] No data.")
        sys.exit(1)

    df["year_weight"] = (df["yy_int"] - 15).clip(lower=1, upper=10)

    for col, _, ftype in ALL_FACTORS:
        if col not in df.columns:
            continue
        raw = df[col].astype(str).str.strip()
        if ftype == "numeric":
            df[col] = pd.to_numeric(raw.replace({"": None, "nan": None}), errors="coerce")
        else:
            df[col] = raw.replace({"": None, "nan": None, "None": None})

    print("[INFO] Loading previous race data...")
    try:
        prev_df = load_prev_data()
        print(f"[INFO] Prev: {len(prev_df):,} rows")
    except Exception as e:
        print(f"[WARN] Prev data failed: {e}")
        prev_df = None

    print("[INFO] Loading bloodline data...")
    try:
        blood_df = load_blood_data()
        print(f"[INFO] Blood: {len(blood_df):,} rows")
    except Exception as e:
        print(f"[WARN] Blood data failed: {e}")
        blood_df = None

    print("[INFO] Computing derived factors...")
    df = compute_derived_factors(df, prev_df, blood_df)
    df = _apply_odds_filter(df)

    print("[INFO] Loading extra tables (jrd_joa_fixed, jrd_bac_fixed)...")
    try:
        df = load_extra_tables_for_full_scan(df)
        print(f"[INFO] After merge: {len(df):,} rows, {len(df.columns)} cols")
    except Exception as e:
        print(f"[WARN] Extra-table merge failed: {e}")

    return df


# ── Main analysis ─────────────────────────────────────────────────────────────

def extract_reliable_bins(
    df: pd.DataFrame,
    ranking_df: pd.DataFrame,
    seg_dfs: Dict[str, pd.DataFrame],
    min_n: int = 100,
    min_roi: float = 120.0,
    top_n: int = 500,
    grade_filter: List[str] = None,
) -> pd.DataFrame:
    """
    Re-run analyze_combination for each row in ranking_df (up to top_n).
    Return a DataFrame of all bins satisfying n >= min_n AND win_roi > min_roi.
    """
    if grade_filter is None:
        grade_filter = ["S", "A"]

    target = ranking_df[ranking_df["grade"].isin(grade_filter)].head(top_n)
    print(f"[INFO] Analysing {len(target)} results "
          f"(grades: {grade_filter}, top_n={top_n})")

    reliable_rows = []
    total = len(target)

    for i, (_, row) in enumerate(target.iterrows()):
        seg = str(row["segment"])
        factors_str = str(row["factor"])
        score_std = float(row["score_std"])
        source = str(row.get("source", ""))

        factors = factors_str.split("+")
        seg_df = seg_dfs.get(seg)
        if seg_df is None or len(seg_df) < 30:
            continue

        # Verify all factors exist in df
        if any(f not in df.columns for f in factors):
            continue

        result = analyze_combination(seg_df, factors, seg)
        if result is None:
            continue

        # Collect reliable bins
        for bin_data in result["bins"]:
            n = bin_data["n"]
            win_roi = bin_data["win_roi"]
            if n >= min_n and win_roi > min_roi:
                reliable_rows.append({
                    "rank": int(row["rank"]),
                    "source": source,
                    "segment": seg,
                    "factors": factors_str,
                    "bin_value": bin_data["bin_label"],
                    "n": n,
                    "win_rate": bin_data.get("win_rate", None),
                    "win_roi": win_roi,
                    "place_roi": bin_data["place_roi"],
                    "confidence": bin_data["confidence"],
                    "score_std": score_std,
                })

        if (i + 1) % 50 == 0 or (i + 1) == total:
            print(f"  [{i+1}/{total}] reliable bins so far: {len(reliable_rows)}")

    if not reliable_rows:
        return pd.DataFrame(columns=[
            "rank", "source", "segment", "factors", "bin_value",
            "n", "win_rate", "win_roi", "place_roi", "confidence", "score_std",
        ])

    out = pd.DataFrame(reliable_rows)
    out = out.sort_values(["win_roi", "n"], ascending=[False, False])
    out.insert(0, "reliable_rank", range(1, len(out) + 1))
    return out


def show_top10_best_bins(
    df: pd.DataFrame,
    ranking_df: pd.DataFrame,
    seg_dfs: Dict[str, pd.DataFrame],
) -> None:
    """Print the best_bin details for TOP10 entries in ranking_df."""
    top10 = ranking_df.head(10)
    print("\n" + "=" * 100)
    print("TOP 10 BEST-BIN VERIFICATION")
    print("=" * 100)
    print(f"{'Rank':>4} {'Segment':<25} {'Factors':<38} "
          f"{'best_n':>7} {'best_ROI':>9} {'reliable?':>10}")
    print("-" * 100)

    for _, row in top10.iterrows():
        seg = str(row["segment"])
        factors_str = str(row["factor"])
        factors = factors_str.split("+")
        seg_df = seg_dfs.get(seg)
        if seg_df is None:
            print(f"{int(row['rank']):>4} {seg[:24]:<25} {factors_str[:37]:<38} "
                  f"{'N/A':>7} {'N/A':>9} {'SEG MISSING':>10}")
            continue
        if any(f not in df.columns for f in factors):
            print(f"{int(row['rank']):>4} {seg[:24]:<25} {factors_str[:37]:<38} "
                  f"{'N/A':>7} {'N/A':>9} {'COL MISSING':>10}")
            continue

        result = analyze_combination(seg_df, factors, seg)
        if result is None:
            print(f"{int(row['rank']):>4} {seg[:24]:<25} {factors_str[:37]:<38} "
                  f"{'SKIP':>7} {'SKIP':>9} {'SKIP':>10}")
            continue

        # Best bin = highest win_roi
        best = max(result["bins"], key=lambda b: b["win_roi"])
        n = best["n"]
        win_roi = best["win_roi"]
        reliable = "OK" if n >= 100 else f"WARN n={n}<100"
        print(f"{int(row['rank']):>4} {seg[:24]:<25} {factors_str[:37]:<38} "
              f"{n:>7} {win_roi:>8.1f}% {reliable:>10}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build reliable high-ROI bin list from screening results"
    )
    parser.add_argument("--min-n", type=int, default=100,
                        help="Minimum samples per bin (default 100)")
    parser.add_argument("--min-roi", type=float, default=120.0,
                        help="Minimum win ROI%% for a reliable bin (default 120)")
    parser.add_argument("--top-n", type=int, default=500,
                        help="Analyse top-N results from ranking (default 500)")
    parser.add_argument("--grades", nargs="+", default=["S", "A"],
                        help="Grade filter (default: S A)")
    parser.add_argument("--rows", type=int, default=DEFAULT_CEO_ROWS,
                        help="Rows to load (default 100k)")
    parser.add_argument("--ranking-csv", type=str,
                        default=str(RANKING_CSV),
                        help="Path to all_combined_ranking.csv")
    parser.add_argument("--output", type=str,
                        default=str(DEFAULT_OUTPUT_DIR / "reliable_high_roi_bins.csv"))
    args = parser.parse_args()

    # Load ranking
    ranking_path = Path(args.ranking_csv)
    if not ranking_path.exists():
        print(f"[ERROR] Ranking CSV not found: {ranking_path}")
        sys.exit(1)
    ranking_df = pd.read_csv(ranking_path, encoding="utf-8-sig")
    print(f"[INFO] Loaded ranking: {len(ranking_df):,} rows, "
          f"grades: {ranking_df['grade'].value_counts().to_dict()}")

    # Load and prepare data
    df = _load_and_prepare(args.rows)
    seg_dfs = _build_seg_dfs(df)
    print(f"[INFO] Segments built: {len(seg_dfs)}")

    # TOP10 verification
    show_top10_best_bins(df, ranking_df, seg_dfs)

    # Build reliable bins
    print(f"\n[INFO] Building reliable bins "
          f"(n>={args.min_n}, win_roi>{args.min_roi}%, top_n={args.top_n}, "
          f"grades={args.grades})...")
    reliable_df = extract_reliable_bins(
        df=df,
        ranking_df=ranking_df,
        seg_dfs=seg_dfs,
        min_n=args.min_n,
        min_roi=args.min_roi,
        top_n=args.top_n,
        grade_filter=args.grades,
    )

    # Save
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        reliable_df.to_csv(output_path, index=False, encoding="utf-8-sig")
        print(f"\n[OK] {output_path}  ({len(reliable_df):,} rows)")
    except PermissionError:
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = output_path.with_stem(output_path.stem + f"_{ts}")
        reliable_df.to_csv(backup, index=False, encoding="utf-8-sig")
        print(f"\n[WARN] locked -- written to {backup}  ({len(reliable_df):,} rows)")

    # Summary
    if len(reliable_df) == 0:
        print("[INFO] No reliable bins found with current thresholds.")
        return

    print(f"\n[SUMMARY] reliable_high_roi_bins: {len(reliable_df):,} bins")
    print(f"  win_roi stats: "
          f"max={reliable_df['win_roi'].max():.1f}% "
          f"mean={reliable_df['win_roi'].mean():.1f}% "
          f"median={reliable_df['win_roi'].median():.1f}%")
    print(f"  n stats: "
          f"min={reliable_df['n'].min()} "
          f"mean={reliable_df['n'].mean():.0f} "
          f"max={reliable_df['n'].max()}")

    # TOP 20 console
    print("\n=== RELIABLE HIGH-ROI BINS TOP 20 ===")
    cols = ["reliable_rank", "segment", "factors", "bin_value", "n",
            "win_rate", "win_roi", "place_roi", "score_std"]
    top20 = reliable_df[cols].head(20)
    print(top20.to_string(index=False))

    print(f"\n[DONE] {len(reliable_df):,} reliable bins "
          f"(n>={args.min_n}, win_roi>{args.min_roi}%).")


if __name__ == "__main__":
    main()

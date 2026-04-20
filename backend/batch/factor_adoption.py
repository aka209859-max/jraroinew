#!/usr/bin/env python3
"""
factor_adoption.py
==================
スクリーニング結果（all_combined_ranking.csv）を元に、各ファクターの採用判定を行う。

採用基準:
  1. n >= 100 のビンだけ「有効ビン」とする
  2. 有効ビンのうち place_roi >= 80% のビンの割合 (pass_rate) を計算
  3. 有効ビン数 < 3 → 判定不能
  4. pass_rate >= 0.50 → 採用
  5. pass_rate >= 0.30 → 検討
  6. pass_rate < 0.30  → 不採用

Usage:
  py -3.12 -m backend.batch.factor_adoption [--limit N] [--min-n 100] [--pass-roi 80]
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

# ── Reuse factor_screening internals ─────────────────────────────────────────
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
ADOPTION_CSV = DEFAULT_OUTPUT_DIR / "factor_adoption_result.csv"
DETAIL_DIR = DEFAULT_OUTPUT_DIR / "factor_adoption_detail"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_filename(segment: str, factors: str) -> str:
    """Build a safe filename from segment + factors (strips non-ASCII, limits length)."""
    s = f"{segment}_{factors}"
    # Replace path-unsafe chars with underscore
    s = re.sub(r'[\\/:*?"<>|\s+]', '_', s)
    # Truncate to 120 chars to stay under Windows MAX_PATH
    return s[:120] + ".csv"


def _apply_odds_filter(df: pd.DataFrame) -> pd.DataFrame:
    """Keep tansho_odds 10-1000 (stored as int*10, so 1.0-100.0x)."""
    if "tansho_odds" in df.columns:
        odds_int = pd.to_numeric(
            df["tansho_odds"].astype(str).str.strip(), errors="coerce"
        )
        before = len(df)
        df = df[(odds_int >= 10) & (odds_int <= 1000)].copy()
        print(f"[INFO] Odds filter: {before:,} -> {len(df):,} rows")
    return df


def _build_seg_dfs(df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """Build segment_name -> sub-DataFrame for fast lookup (mirrors build_reliable_bins)."""
    segs: Dict[str, pd.DataFrame] = {
        "GLOBAL": df,
        "COURSE_27": df,
    }
    if "surface" in df.columns:
        segs["SURFACE_2_\u829d"] = df[df["surface"] == "\u829d"]   # 芝 (U+829D)
        segs["SURFACE_2_\u30c0"] = df[df["surface"] == "\u30c0"]   # ダ (U+30C0)
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


# ── Adoption logic ────────────────────────────────────────────────────────────

def _decide(valid_bins: int, pass_bins: int, pass_rate: float) -> str:
    if valid_bins < 3:
        return "判定不能"
    if pass_rate >= 0.50:
        return "採用"
    if pass_rate >= 0.30:
        return "検討"
    return "不採用"


def run_adoption(
    df: pd.DataFrame,
    ranking_df: pd.DataFrame,
    seg_dfs: Dict[str, pd.DataFrame],
    limit: Optional[int],
    min_n: int,
    pass_roi: float,
    save_detail: bool,
) -> pd.DataFrame:
    """
    For each row in ranking_df (up to limit), re-run analyze_combination,
    evaluate adoption criteria, and return a result DataFrame.
    """
    target = ranking_df if limit is None else ranking_df.head(limit)
    total = len(target)
    print(f"[INFO] Evaluating {total} entries from ranking...")

    DETAIL_DIR.mkdir(parents=True, exist_ok=True)

    result_rows = []

    for i, (_, row) in enumerate(target.iterrows()):
        seg = str(row["segment"])
        factors_str = str(row["factor"])
        factors = factors_str.split("+")
        rank_orig = int(row["rank"])
        source = str(row.get("source", ""))
        factor_type = str(row.get("factor_type", ""))
        score_std = float(row.get("score_std", 0.0))
        grade = str(row.get("grade", ""))

        seg_df = seg_dfs.get(seg)
        if seg_df is None or len(seg_df) < 30:
            # Segment not available
            result_rows.append({
                "rank": rank_orig, "source": source, "segment": seg,
                "factors": factors_str, "type": factor_type, "grade": grade,
                "score_std": score_std,
                "total_bins": 0, "valid_bins": 0, "pass_bins": 0,
                "pass_rate": None, "decision": "判定不能",
                "avg_place_roi": None, "avg_win_roi": None,
                "best_place_roi": None, "best_win_roi": None,
                "total_samples": 0,
            })
            continue

        # Verify all factor columns exist
        missing = [f for f in factors if f not in df.columns]
        if missing:
            result_rows.append({
                "rank": rank_orig, "source": source, "segment": seg,
                "factors": factors_str, "type": factor_type, "grade": grade,
                "score_std": score_std,
                "total_bins": 0, "valid_bins": 0, "pass_bins": 0,
                "pass_rate": None, "decision": "判定不能",
                "avg_place_roi": None, "avg_win_roi": None,
                "best_place_roi": None, "best_win_roi": None,
                "total_samples": 0,
            })
            continue

        try:
            result = analyze_combination(seg_df, factors, seg)
        except Exception as e:
            print(f"  [WARN] [{i+1}/{total}] {seg}/{factors_str} failed: {e}")
            result_rows.append({
                "rank": rank_orig, "source": source, "segment": seg,
                "factors": factors_str, "type": factor_type, "grade": grade,
                "score_std": score_std,
                "total_bins": 0, "valid_bins": 0, "pass_bins": 0,
                "pass_rate": None, "decision": "判定不能",
                "avg_place_roi": None, "avg_win_roi": None,
                "best_place_roi": None, "best_win_roi": None,
                "total_samples": 0,
            })
            continue

        if result is None:
            result_rows.append({
                "rank": rank_orig, "source": source, "segment": seg,
                "factors": factors_str, "type": factor_type, "grade": grade,
                "score_std": score_std,
                "total_bins": 0, "valid_bins": 0, "pass_bins": 0,
                "pass_rate": None, "decision": "判定不能",
                "avg_place_roi": None, "avg_win_roi": None,
                "best_place_roi": None, "best_win_roi": None,
                "total_samples": 0,
            })
            continue

        bins = result["bins"]
        total_bins = len(bins)
        valid = [b for b in bins if b["n"] >= min_n]
        valid_bins = len(valid)
        pass_bins = sum(1 for b in valid if b["place_roi"] >= pass_roi)
        pass_rate = round(pass_bins / valid_bins, 4) if valid_bins > 0 else None
        decision = _decide(valid_bins, pass_bins, pass_rate if pass_rate is not None else 0.0)

        all_place_rois = [b["place_roi"] for b in bins]
        all_win_rois = [b["win_roi"] for b in bins]
        avg_place_roi = round(sum(all_place_rois) / len(all_place_rois), 1) if all_place_rois else None
        avg_win_roi = round(sum(all_win_rois) / len(all_win_rois), 1) if all_win_rois else None
        best_place_roi = max(all_place_rois) if all_place_rois else None
        best_win_roi = max(all_win_rois) if all_win_rois else None

        result_rows.append({
            "rank": rank_orig, "source": source, "segment": seg,
            "factors": factors_str, "type": factor_type, "grade": grade,
            "score_std": score_std,
            "total_bins": total_bins,
            "valid_bins": valid_bins,
            "pass_bins": pass_bins,
            "pass_rate": pass_rate,
            "decision": decision,
            "avg_place_roi": avg_place_roi,
            "avg_win_roi": avg_win_roi,
            "best_place_roi": best_place_roi,
            "best_win_roi": best_win_roi,
            "total_samples": result["total_samples"],
        })

        # Save detail CSV
        if save_detail and bins:
            detail_rows = []
            for b in bins:
                n_b = b["n"]
                p_roi = b["place_roi"]
                detail_rows.append({
                    "bin": b["bin_label"],
                    "n": n_b,
                    "win_count": b.get("win_count", ""),
                    "place_count": "",       # not computed in _bin_stats; leave blank
                    "win_rate": b.get("win_rate", ""),
                    "place_rate": "",
                    "win_roi": b["win_roi"],
                    "place_roi": p_roi,
                    "decision_80pct": "O" if p_roi >= pass_roi else "X",
                })
            fname = _safe_filename(seg, factors_str)
            try:
                pd.DataFrame(detail_rows).to_csv(
                    DETAIL_DIR / fname, index=False, encoding="utf-8-sig"
                )
            except Exception as e:
                print(f"  [WARN] detail save failed ({fname}): {e}")

        if (i + 1) % 50 == 0 or (i + 1) == total:
            adopted = sum(1 for r in result_rows if r["decision"] == "採用")
            print(f"  [{i+1}/{total}] adopted so far: {adopted}")

    out = pd.DataFrame(result_rows)
    if out.empty:
        return out

    # Sort: pass_rate DESC (NaN last), avg_place_roi DESC
    out = out.sort_values(
        ["pass_rate", "avg_place_roi"],
        ascending=[False, False],
        na_position="last",
    )
    out.insert(0, "adoption_rank", range(1, len(out) + 1))
    return out


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Factor adoption decision from screening results"
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Limit number of entries to evaluate (default: all)"
    )
    parser.add_argument(
        "--min-n", type=int, default=100,
        help="Minimum bin sample count to be 'valid' (default 100)"
    )
    parser.add_argument(
        "--pass-roi", type=float, default=80.0,
        help="Minimum place_roi%% for a bin to pass (default 80)"
    )
    parser.add_argument(
        "--rows", type=int, default=DEFAULT_CEO_ROWS,
        help="Rows to load from DB (default 100k)"
    )
    parser.add_argument(
        "--ranking-csv", type=str, default=str(RANKING_CSV),
        help="Path to all_combined_ranking.csv"
    )
    parser.add_argument(
        "--output", type=str, default=str(ADOPTION_CSV),
        help="Output CSV path"
    )
    parser.add_argument(
        "--no-detail", action="store_true",
        help="Skip writing per-factor detail CSVs"
    )
    args = parser.parse_args()

    # Load ranking
    ranking_path = Path(args.ranking_csv)
    if not ranking_path.exists():
        print(f"[ERROR] Ranking CSV not found: {ranking_path}")
        sys.exit(1)
    ranking_df = pd.read_csv(ranking_path, encoding="utf-8-sig")
    print(f"[INFO] Loaded ranking: {len(ranking_df):,} rows, "
          f"grades: {ranking_df['grade'].value_counts().to_dict()}")

    # Load + prepare data
    df = _load_and_prepare(args.rows)
    seg_dfs = _build_seg_dfs(df)
    print(f"[INFO] Segments built: {len(seg_dfs)}")

    # Run adoption analysis
    print(f"\n[INFO] Running adoption analysis "
          f"(min_n={args.min_n}, pass_roi={args.pass_roi}%, "
          f"limit={args.limit if args.limit else 'all'})...")
    adoption_df = run_adoption(
        df=df,
        ranking_df=ranking_df,
        seg_dfs=seg_dfs,
        limit=args.limit,
        min_n=args.min_n,
        pass_roi=args.pass_roi,
        save_detail=(not args.no_detail),
    )

    # Save
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        adoption_df.to_csv(output_path, index=False, encoding="utf-8-sig")
        print(f"\n[OK] {output_path}  ({len(adoption_df):,} rows)")
    except PermissionError:
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = output_path.with_stem(output_path.stem + f"_{ts}")
        adoption_df.to_csv(backup, index=False, encoding="utf-8-sig")
        print(f"\n[WARN] locked -- written to {backup}  ({len(adoption_df):,} rows)")

    if adoption_df.empty:
        print("[INFO] No results.")
        return

    # Summary by decision
    counts = adoption_df["decision"].value_counts().to_dict()
    total_e = sum(counts.values())
    adopted = counts.get("採用", 0)
    kento = counts.get("判定不能", 0) + counts.get("検討", 0)
    fukai = counts.get("不採用", 0)
    hantei_funo = counts.get("判定不能", 0)
    kento_only = counts.get("検討", 0)

    print(f"\n[SUMMARY] total={total_e}")
    print(f"  採用   : {adopted}")
    print(f"  検討   : {kento_only}")
    print(f"  不採用 : {fukai}")
    print(f"  判定不能: {hantei_funo}")

    # TOP30 adopted factors
    adopted_df = adoption_df[adoption_df["decision"] == "採用"].head(30)
    if len(adopted_df) > 0:
        print("\n=== TOP 30 ADOPTED FACTORS (pass_rate DESC) ===")
        cols = [
            "adoption_rank", "segment", "factors", "grade",
            "total_bins", "valid_bins", "pass_bins", "pass_rate",
            "avg_place_roi", "avg_win_roi", "best_place_roi", "best_win_roi",
        ]
        print(adopted_df[cols].to_string(index=False))

    # All adopted factors list
    all_adopted = adoption_df[adoption_df["decision"] == "採用"]
    if len(all_adopted) > 0:
        print(f"\n=== ALL ADOPTED FACTORS ({len(all_adopted)} total) ===")
        for _, r in all_adopted.iterrows():
            pr = f"{r['pass_rate']*100:.0f}%" if r["pass_rate"] is not None else "N/A"
            print(f"  [{r['segment']}] {r['factors']}  "
                  f"pass={pr}  avg_place_roi={r['avg_place_roi']}%  grade={r['grade']}")

    print(f"\n[DONE] factor_adoption_result.csv saved. ({len(adoption_df):,} rows)")


if __name__ == "__main__":
    main()

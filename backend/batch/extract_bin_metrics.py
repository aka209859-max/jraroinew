#!/usr/bin/env python3
"""
extract_bin_metrics.py
=======================
Phase 1~4 で CLB>=80% を通過した全 COMBO について、
各ビン（具体的な条件値の組み合わせ）ごとの単勝・複勝詳細成績を算出し
master_bin_metrics.csv に出力する。

【出力カラム】
  phase, segment, combo, bin_key, n_horses,
  tansho_n, tansho_hit_rate, tansho_roi_raw, tansho_roi_corr,
  fukusho_n, fukusho_hit_rate, fukusho_roi_raw, fukusho_roi_corr,
  combo_clb, combo_mean_roi

【ROI 定義】
  raw : haraimodoshi (実払戻額, 円/100円ベット) の平均
  corr: 均等払戻補正ROI (_tansho_corrected_pay / _bet_amount 等)

Usage:
  py -3.12 -m backend.batch.extract_bin_metrics
"""

import time
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from backend.batch.factor_investment_screening import load_and_prepare
from backend.batch.master_combo_pipeline import (
    add_class_column,
    build_production_segments,
    SEGMENTS_DIR,
)

# --------------------------------------------------------------------------
OUTPUT_CSV = Path("reports/production_search/master_bin_metrics.csv")
# --------------------------------------------------------------------------


def _collect_passing_combos() -> List[Dict]:
    """
    Phase 1~4 の per-segment combo_results.csv から
    pass==True の全 (phase, segment, factors, clb, mean_roi) を収集。
    """
    records = []
    for phase in [1, 2, 3, 4]:
        factor_col = "factor" if phase == 1 else "factors"
        for seg_dir in sorted(SEGMENTS_DIR.iterdir()):
            if not seg_dir.is_dir():
                continue
            csv_path = seg_dir / f"combo{phase}_results.csv"
            if not csv_path.exists():
                continue
            try:
                df = pd.read_csv(csv_path)
            except Exception:
                continue
            if df.empty or "pass" not in df.columns:
                continue
            for _, row in df[df["pass"] == True].iterrows():
                raw = str(row.get(factor_col, "")).strip()
                factors = [raw] if phase == 1 else [f.strip() for f in raw.split("+") if f.strip()]
                if not factors:
                    continue
                records.append({
                    "phase":         phase,
                    "segment":       seg_dir.name,
                    "factors":       factors,
                    "combo":         "+".join(factors),
                    "combo_clb":     round(float(row.get("clb", 0)), 2),
                    "combo_mean_roi": round(float(row.get("mean_roi", 0)), 2),
                })
    return records


def _bin_metrics(seg_df: pd.DataFrame, factors: List[str],
                 phase: int, segment: str, combo: str,
                 combo_clb: float, combo_mean_roi: float) -> List[Dict]:
    """factors でグループ化し、ビンごとの単勝・複勝成績を返す。"""
    missing = [f for f in factors if f not in seg_df.columns]
    if missing:
        return []

    # NULL 除外
    mask = pd.Series(True, index=seg_df.index)
    for f in factors:
        mask &= seg_df[f].notna()
    sub = seg_df[mask].copy()
    if sub.empty:
        return []

    # 複合キー（"|" 区切り）
    key = sub[factors[0]].astype(str)
    for f in factors[1:]:
        key = key + "|" + sub[f].astype(str)
    sub["_k"] = key

    rows = []
    for bin_key, grp in sub.groupby("_k", sort=False):
        n = len(grp)

        # ===== 単勝 =====
        t_valid = grp["_bet_amount"].notna() & (grp["_bet_amount"] > 0)
        tg = grp[t_valid]
        tn = int(t_valid.sum())
        if tn > 0:
            t_hit = float(tg["_is_tansho_hit"].mean()) * 100
            # raw: haraimodoshi_tansho (yen/100yen-bet, 0 if miss)
            har_t = pd.to_numeric(tg.get("haraimodoshi_tansho", pd.Series(dtype=float)),
                                  errors="coerce").fillna(0.0)
            t_raw = round(float(har_t.mean()), 2)
            # corr: 均等払戻補正
            bet_s = float(tg["_bet_amount"].sum())
            pay_s = float(tg["_tansho_corrected_pay"].sum())
            t_corr = round(pay_s / bet_s * 100, 2) if bet_s > 0 else None
        else:
            t_hit = t_raw = t_corr = None

        # ===== 複勝 =====
        f_valid = grp["_fukusho_bet_amount"].notna() & (grp["_fukusho_bet_amount"] > 0)
        fg = grp[f_valid]
        fn = int(f_valid.sum())
        if fn > 0:
            f_hit = float(fg["_is_fukusho_hit"].mean()) * 100
            # raw: haraimodoshi_fukusho (yen/100yen-bet, 0 if miss)
            har_f = pd.to_numeric(fg.get("haraimodoshi_fukusho", pd.Series(dtype=float)),
                                  errors="coerce").fillna(0.0)
            f_raw = round(float(har_f.mean()), 2)
            # corr: 均等払戻補正
            fbet_s = float(fg["_fukusho_bet_amount"].sum())
            fpay_s = float(fg["_corrected_pay"].sum())
            f_corr = round(fpay_s / fbet_s * 100, 2) if fbet_s > 0 else None
        else:
            f_hit = f_raw = f_corr = None

        rows.append({
            "phase":            phase,
            "segment":          segment,
            "combo":            combo,
            "bin_key":          str(bin_key),
            "n_horses":         n,
            "tansho_n":         tn,
            "tansho_hit_rate":  round(t_hit, 2) if t_hit is not None else None,
            "tansho_roi_raw":   t_raw,
            "tansho_roi_corr":  t_corr,
            "fukusho_n":        fn,
            "fukusho_hit_rate": round(f_hit, 2) if f_hit is not None else None,
            "fukusho_roi_raw":  f_raw,
            "fukusho_roi_corr": f_corr,
            "combo_clb":        combo_clb,
            "combo_mean_roi":   combo_mean_roi,
        })
    return rows


def main() -> None:
    t0 = time.time()
    print("=" * 60)
    print("  extract_bin_metrics - ビン単位詳細成績抽出")
    print("=" * 60)

    # ---- データロード ----
    print("\n[STEP 1] データロード (load_and_prepare)...")
    df = load_and_prepare(row_limit=0)
    print(f"[INFO] 行数: {len(df):,}  列数: {len(df.columns)}")

    # haraimodoshi 列の有無を確認
    for col in ["haraimodoshi_tansho", "haraimodoshi_fukusho"]:
        coverage = df[col].notna().mean() * 100 if col in df.columns else 0.0
        print(f"[INFO] {col}: coverage={coverage:.1f}%")

    # ---- セグメントマップ ----
    print("\n[STEP 2] セグメントマップ構築...")
    df = add_class_column(df)
    seg_map = build_production_segments(df)
    print(f"[INFO] セグメント数: {len(seg_map)}")

    # ---- 採用COMBO 収集 ----
    print("\n[STEP 3] 採用COMBO収集...")
    combos = _collect_passing_combos()
    by_phase = {p: sum(1 for c in combos if c["phase"] == p) for p in [1, 2, 3, 4]}
    print(f"[INFO] 採用COMBO数: {len(combos):,}  "
          f"Phase1={by_phase[1]}, Phase2={by_phase[2]}, "
          f"Phase3={by_phase[3]}, Phase4={by_phase[4]}")

    # ---- ビン集計 ----
    print("\n[STEP 4] ビン集計...")
    all_rows: List[Dict] = []
    n_skip = 0
    for i, c in enumerate(combos, 1):
        seg_name = c["segment"]
        if seg_name not in seg_map:
            n_skip += 1
            continue
        all_rows.extend(_bin_metrics(
            seg_map[seg_name], c["factors"],
            c["phase"], seg_name, c["combo"],
            c["combo_clb"], c["combo_mean_roi"],
        ))
        if i % 200 == 0:
            print(f"  [{i}/{len(combos)}] ビン行数: {len(all_rows):,}")

    print(f"[INFO] 完了: {len(combos)-n_skip} combos / {n_skip} skip / {len(all_rows):,} 行")

    # ---- CSV 出力 ----
    print("\n[STEP 5] CSV 出力...")
    result_df = pd.DataFrame(all_rows)
    result_df = result_df.sort_values(
        ["phase", "segment", "combo", "fukusho_roi_corr"],
        ascending=[True, True, True, False],
        na_position="last",
    ).reset_index(drop=True)

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    result_df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

    elapsed = time.time() - t0
    print(f"\n[完了] {len(result_df):,} 行  elapsed={elapsed:.1f}s ({elapsed/60:.1f}min)")
    print(f"[OK] {OUTPUT_CSV.resolve()}")

    # ---- サマリー ----
    print("\n■ 複勝補正ROI Top 10 ビン:")
    top_f = result_df.dropna(subset=["fukusho_roi_corr"]).nlargest(10, "fukusho_roi_corr")
    print(top_f[["phase","segment","combo","bin_key","fukusho_n",
                 "fukusho_hit_rate","fukusho_roi_corr","combo_clb"]].to_string(index=False))

    print("\n■ 単勝補正ROI Top 10 ビン:")
    top_t = result_df.dropna(subset=["tansho_roi_corr"]).nlargest(10, "tansho_roi_corr")
    print(top_t[["phase","segment","combo","bin_key","tansho_n",
                 "tansho_hit_rate","tansho_roi_corr","combo_clb"]].to_string(index=False))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
clean_and_reextract_bins.py
============================
master_bin_metrics.csv の課題を修正した浄化版を生成する。

【変更点】
  1. Phase 1 の抽出閾値を CLB >= 75.0 に緩和（従来は 80.0）
  2. Phase 2~4 は CLB >= 80.0 のまま（pass==True 行）
  3. 出力時に tansho_n < 50 かつ fukusho_n < 50 のビンを除外
     （どちらか片方でも 50 未満なら除外）

出力: reports/production_search/master_bin_metrics_cleaned.csv

Usage:
  py -3.12 -u -m backend.batch.clean_and_reextract_bins
"""

import time
from pathlib import Path
from typing import Dict, List

import pandas as pd

from backend.batch.factor_investment_screening import load_and_prepare
from backend.batch.master_combo_pipeline import (
    add_class_column,
    build_production_segments,
    SEGMENTS_DIR,
)
from backend.batch.extract_bin_metrics import _bin_metrics

# --------------------------------------------------------------------------
OUTPUT_CSV = Path("reports/production_search/master_bin_metrics_cleaned.csv")
MIN_BIN_N  = 50    # 単勝・複勝ともにこれ未満のビンは除外
P1_CLB_THRESHOLD  = 75.0  # Phase 1 専用閾値
P24_CLB_THRESHOLD = 80.0  # Phase 2~4 閾値（pass==True と同値）
# --------------------------------------------------------------------------


def _collect_combos() -> List[Dict]:
    """
    Phase 1: CLB >= 75.0 の全ファクターを収集（pass フラグ非依存）
    Phase 2~4: pass==True の全 COMBO を収集（CLB >= 80.0 と等価）
    """
    records = []

    for phase in [1, 2, 3, 4]:
        factor_col = "factor" if phase == 1 else "factors"
        threshold  = P1_CLB_THRESHOLD if phase == 1 else P24_CLB_THRESHOLD

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
            if df.empty or "clb" not in df.columns:
                continue

            # Phase 1: CLB >= 75.0 でフィルタ
            # Phase 2~4: pass==True でフィルタ（= CLB >= 80.0 と同等）
            if phase == 1:
                target = df[df["clb"] >= threshold]
            else:
                if "pass" not in df.columns:
                    continue
                target = df[df["pass"] == True]

            if target.empty:
                continue

            seg_name = seg_dir.name
            for _, row in target.iterrows():
                raw     = str(row.get(factor_col, "")).strip()
                factors = [raw] if phase == 1 else [f.strip() for f in raw.split("+") if f.strip()]
                if not factors:
                    continue
                records.append({
                    "phase":          phase,
                    "segment":        seg_name,
                    "factors":        factors,
                    "combo":          "+".join(factors),
                    "combo_clb":      round(float(row.get("clb", 0)), 2),
                    "combo_mean_roi": round(float(row.get("mean_roi", 0)), 2),
                })

    return records


def main() -> None:
    t0 = time.time()
    print("=" * 60)
    print("  clean_and_reextract_bins")
    print("  Phase1 CLB>=75.0 / Phase2-4 CLB>=80.0 / min_bin_n=50")
    print("=" * 60)

    # ---- データロード ----
    print("\n[STEP 1] データロード...")
    df = load_and_prepare(row_limit=0)
    print(f"[INFO] {len(df):,} rows, {len(df.columns)} cols")

    # ---- セグメントマップ ----
    print("\n[STEP 2] セグメントマップ構築...")
    df = add_class_column(df)
    seg_map = build_production_segments(df)
    print(f"[INFO] {len(seg_map)} セグメント")

    # ---- COMBO 収集 ----
    print("\n[STEP 3] COMBO 収集...")
    combos = _collect_combos()
    by_phase = {p: sum(1 for c in combos if c["phase"] == p) for p in [1, 2, 3, 4]}
    print(f"[INFO] 採用COMBO数: {len(combos):,}")
    for p in [1, 2, 3, 4]:
        print(f"  Phase{p}: {by_phase[p]}")

    # ---- ビン集計 ----
    print("\n[STEP 4] ビン集計...")
    all_rows = []
    n_skip   = 0
    for i, c in enumerate(combos, 1):
        if c["segment"] not in seg_map:
            n_skip += 1
            continue
        all_rows.extend(_bin_metrics(
            seg_map[c["segment"]], c["factors"],
            c["phase"], c["segment"], c["combo"],
            c["combo_clb"], c["combo_mean_roi"],
        ))
        if i % 200 == 0:
            print(f"  [{i}/{len(combos)}] ビン行数: {len(all_rows):,}")

    print(f"[INFO] 集計完了: {len(all_rows):,} ビン行 (フィルタ前)")

    # ---- フィルタ: tansho_n >= 50 AND fukusho_n >= 50 ----
    print("\n[STEP 5] ノイズビン除外 (tansho_n >= 50 AND fukusho_n >= 50)...")
    raw_df = pd.DataFrame(all_rows)
    before = len(raw_df)

    keep = (
        (raw_df["tansho_n"].fillna(0) >= MIN_BIN_N) &
        (raw_df["fukusho_n"].fillna(0) >= MIN_BIN_N)
    )
    result_df = raw_df[keep].copy()

    print(f"[INFO] {before:,} -> {len(result_df):,} 行 ({before - len(result_df):,} 行除外)")

    by_phase_after = result_df.groupby("phase").size().to_dict()
    for p in [1, 2, 3, 4]:
        print(f"  Phase{p}: {by_phase_after.get(p, 0):,} 行")

    # ---- 並び替え & 出力 ----
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
    print("\n■ 複勝補正ROI Top 10 (n_horses >= 50 以上のビン):")
    top_f = result_df.dropna(subset=["fukusho_roi_corr"]).nlargest(10, "fukusho_roi_corr")
    print(top_f[["phase","segment","combo","bin_key","fukusho_n",
                 "fukusho_hit_rate","fukusho_roi_corr","combo_clb"]].to_string(index=False))

    print("\n■ 単勝補正ROI Top 10 (n_horses >= 50 以上のビン):")
    top_t = result_df.dropna(subset=["tansho_roi_corr"]).nlargest(10, "tansho_roi_corr")
    print(top_t[["phase","segment","combo","bin_key","tansho_n",
                 "tansho_hit_rate","tansho_roi_corr","combo_clb"]].to_string(index=False))


if __name__ == "__main__":
    main()

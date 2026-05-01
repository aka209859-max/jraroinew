#!/usr/bin/env python3
"""
split_bins_by_sample_size.py
=============================
master_bin_metrics_cleaned.csv を件数クラス × Phase 別に分割出力する。

【抽出閾値】(tansho_n OR fukusho_n のいずれかが閾値以上)
  - [150件クラス]: >= 130 件
  - [300件クラス]: >= 280 件
  - [500件クラス]: >= 480 件

【出力 (計9ファイル)】reports/production_search/ 以下
  phase{2,3,4}_bins_{150,300,500}.csv

Usage:
  py -3.12 -m backend.batch.split_bins_by_sample_size
"""

from pathlib import Path
import pandas as pd

# --------------------------------------------------------------------------
INPUT_CSV  = Path("reports/production_search/master_bin_metrics_cleaned.csv")
OUTPUT_DIR = Path("reports/production_search")

# (label, threshold)  ※指定件数 - 20 件 = 投資機会損失を防ぐ遊び
CLASSES = [
    (150, 130),
    (300, 280),
    (500, 480),
]

PHASES = [2, 3, 4]
# --------------------------------------------------------------------------


def main() -> None:
    print("=" * 60)
    print("  split_bins_by_sample_size")
    print("  150>=130 / 300>=280 / 500>=480  (tansho_n OR fukusho_n)")
    print("=" * 60)

    # ---- 読み込み ----
    print(f"\n[LOAD] {INPUT_CSV}")
    df = pd.read_csv(INPUT_CSV, encoding="utf-8-sig")
    print(f"[INFO] 総行数: {len(df):,}  Phase分布: {df.groupby('phase').size().to_dict()}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results = {}  # (label, phase) -> row_count

    print()
    for label, threshold in CLASSES:
        # tansho_n OR fukusho_n が閾値以上のビンを抽出
        mask = (
            (df["tansho_n"].fillna(0) >= threshold) |
            (df["fukusho_n"].fillna(0) >= threshold)
        )
        class_df = df[mask].copy()

        for phase in PHASES:
            phase_df = class_df[class_df["phase"] == phase].copy()

            # fukusho_roi_corr 降順で並び替え
            phase_df = phase_df.sort_values(
                ["fukusho_roi_corr", "tansho_roi_corr"],
                ascending=[False, False],
                na_position="last",
            ).reset_index(drop=True)

            out_path = OUTPUT_DIR / f"phase{phase}_bins_{label}.csv"
            phase_df.to_csv(out_path, index=False, encoding="utf-8-sig")

            results[(label, phase)] = len(phase_df)
            print(f"  [OUT] {out_path.name:35s}  {len(phase_df):>5,} 行")

    # ---- サマリー表 ----
    print("\n■ 出力結果サマリー")
    print(f"{'':12s} {'Phase2':>8} {'Phase3':>8} {'Phase4':>8} {'合計':>8}")
    print("-" * 50)
    for label, threshold in CLASSES:
        p2 = results[(label, 2)]
        p3 = results[(label, 3)]
        p4 = results[(label, 4)]
        print(f"  {label}件クラス (>={threshold:3d})  {p2:>8,} {p3:>8,} {p4:>8,} {p2+p3+p4:>8,}")
    print()


if __name__ == "__main__":
    main()

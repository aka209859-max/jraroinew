#!/usr/bin/env python3
"""
export_segment_summary.py
==========================
analyzed/ 内の全9CSVを読み込み、セグメント別のビン分布を集計して出力する。

集計項目:
  - 合計ビン数（行数）
  - ユニークCOMBO数
  - Phase2/3/4 別ビン数内訳

出力: reports/production_search/segment_summary.csv

Usage:
  py -3.12 -m backend.batch.export_segment_summary
"""

from pathlib import Path
import pandas as pd

# --------------------------------------------------------------------------
INPUT_DIR  = Path("reports/production_search/analyzed")
OUTPUT_CSV = Path("reports/production_search/segment_summary.csv")

FILES = [
    f"analyzed_phase{phase}_bins_{cls}.csv"
    for cls   in [150, 300, 500]
    for phase in [2, 3, 4]
]
# --------------------------------------------------------------------------


def main() -> None:
    print("=" * 60)
    print("  export_segment_summary")
    print("  全9ファイル セグメント別ビン分布集計")
    print("=" * 60)

    # ---- 全ファイル読み込み & 結合 ----
    frames = []
    for fname in FILES:
        fpath = INPUT_DIR / fname
        if not fpath.exists():
            print(f"  [SKIP] {fname}")
            continue
        df = pd.read_csv(fpath, encoding="utf-8-sig")
        frames.append(df)

    all_df = pd.concat(frames, ignore_index=True)
    # 重複排除（同一ビンが複数クラスファイルに重複して存在する場合）
    all_df = all_df.drop_duplicates(subset=["phase", "segment", "combo", "bin_key"])
    print(f"[INFO] 読み込み完了: {len(all_df):,} 行（重複排除後）")

    # ---- セグメント別集計 ----
    grp = all_df.groupby("segment")

    summary = pd.DataFrame({
        "total_bins":   grp.size(),
        "unique_combos": grp["combo"].nunique(),
        "phase2_bins":  grp.apply(lambda x: int((x["phase"] == 2).sum()), include_groups=False),
        "phase3_bins":  grp.apply(lambda x: int((x["phase"] == 3).sum()), include_groups=False),
        "phase4_bins":  grp.apply(lambda x: int((x["phase"] == 4).sum()), include_groups=False),
    }).reset_index()

    # 合計ビン数 降順ソート
    summary = summary.sort_values("total_bins", ascending=False).reset_index(drop=True)

    # ---- 出力 ----
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

    # ---- レポート ----
    n_seg = len(summary)
    print(f"\n■ セグメント総数: {n_seg} 種類")
    print(f"\n■ ビン数 Top10 セグメント:")
    print(f"  {'#':>3}  {'segment':45s}  {'total':>5}  {'combos':>6}  {'P2':>4}  {'P3':>4}  {'P4':>4}")
    print("  " + "-" * 80)
    for i, row in summary.head(10).iterrows():
        print(f"  {i+1:>3}  {str(row['segment']):45s}  "
              f"{int(row['total_bins']):>5}  "
              f"{int(row['unique_combos']):>6}  "
              f"{int(row['phase2_bins']):>4}  "
              f"{int(row['phase3_bins']):>4}  "
              f"{int(row['phase4_bins']):>4}")

    print(f"\n■ Phase別 合計ビン数:")
    print(f"  Phase2: {int(summary['phase2_bins'].sum()):,} 行")
    print(f"  Phase3: {int(summary['phase3_bins'].sum()):,} 行")
    print(f"  Phase4: {int(summary['phase4_bins'].sum()):,} 行")
    print(f"  全体  : {int(summary['total_bins'].sum()):,} 行")

    print(f"\n[OK] {OUTPUT_CSV.resolve()}")
    print("=" * 60)


if __name__ == "__main__":
    main()

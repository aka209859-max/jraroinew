#!/usr/bin/env python3
"""
extract_premium_factors.py
===========================
ストレステスト済み9CSVから、実戦均等払戻運用に耐えうる
プレミアムファクターを厳選して1つのCSVに集約する。

【フィルタ条件】A AND B を同時に満たすこと

  条件A (単複安定性):
    tansho_roi_corr > 100.0  AND  fukusho_roi_corr > 100.0

  条件B (サンプル数に応じたマージン確保):
    n_horses <  300 -> tansho_roi_corr >= 105.0 OR fukusho_roi_corr >= 105.0
    n_horses >= 300 -> tansho_roi_corr >= 102.0 OR fukusho_roi_corr >= 102.0

出力: reports/production_search/premium_selected_factors.csv

Usage:
  py -3.12 -m backend.batch.extract_premium_factors
"""

from pathlib import Path
import pandas as pd

# --------------------------------------------------------------------------
INPUT_DIR  = Path("reports/production_search/analyzed")
OUTPUT_CSV = Path("reports/production_search/premium_selected_factors.csv")

FILES = [
    f"analyzed_phase{phase}_bins_{cls}.csv"
    for cls   in [150, 300, 500]
    for phase in [2, 3, 4]
]

# フィルタ定数
COND_A_MIN          = 100.0   # 単複ともにこれを超えること (strictly >)
MARGIN_LOW_N        = 105.0   # n_horses < 300 の場合のマージン閾値
MARGIN_HIGH_N       = 102.0   # n_horses >= 300 の場合のマージン閾値
N_THRESHOLD         = 300     # 件数の境界値
# --------------------------------------------------------------------------


def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    """条件A AND 条件B でフィルタリングして返す"""
    # 条件A: 単複ともに100%超
    cond_a = (
        (df["tansho_roi_corr"]  > COND_A_MIN) &
        (df["fukusho_roi_corr"] > COND_A_MIN)
    )

    # 条件B: サンプル数に応じたマージン
    low_n  = df["n_horses"] < N_THRESHOLD
    high_n = df["n_horses"] >= N_THRESHOLD

    cond_b = (
        (low_n  & ((df["tansho_roi_corr"]  >= MARGIN_LOW_N) |
                   (df["fukusho_roi_corr"] >= MARGIN_LOW_N))) |
        (high_n & ((df["tansho_roi_corr"]  >= MARGIN_HIGH_N) |
                   (df["fukusho_roi_corr"] >= MARGIN_HIGH_N)))
    )

    return df[cond_a & cond_b].copy()


def main() -> None:
    print("=" * 65)
    print("  extract_premium_factors")
    print("  単複ROI > 100% + サンプル数別マージンでプレミアム厳選")
    print("=" * 65)

    all_frames = []
    load_summary = []

    for fname in FILES:
        fpath = INPUT_DIR / fname
        if not fpath.exists():
            print(f"  [SKIP] {fname} - ファイル未存在")
            continue

        df    = pd.read_csv(fpath, encoding="utf-8-sig")
        kept  = apply_filters(df)
        load_summary.append((fname, len(df), len(kept)))
        if len(kept) > 0:
            all_frames.append(kept)

        label = "★" if len(kept) > 0 else " "
        print(f"  {label} {fname:40s}  {len(df):>4}行 -> {len(kept):>3}件通過")

    # ---- 結合・重複排除 ----
    if not all_frames:
        print("\n[WARN] 条件を満たすビンが0件でした。フィルタを確認してください。")
        return

    combined = pd.concat(all_frames, ignore_index=True)

    # 重複排除 (segment + combo + bin_key で同一ビンの重複を排除)
    before_dedup = len(combined)
    combined = combined.drop_duplicates(subset=["segment", "combo", "bin_key"])
    after_dedup = len(combined)

    # fukusho_roi_corr 降順ソート
    combined = combined.sort_values(
        "fukusho_roi_corr", ascending=False, na_position="last"
    ).reset_index(drop=True)

    # ---- 出力 ----
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

    # ---- レポート ----
    print(f"\n[重複排除] {before_dedup} -> {after_dedup} 件")

    by_phase = combined.groupby("phase").size().to_dict()

    print("\n" + "=" * 65)
    print(f"■ プレミアムファクター厳選結果")
    print("=" * 65)
    print(f"  合計: {len(combined)} 件")
    print(f"  Phase2: {by_phase.get(2, 0)} 件")
    print(f"  Phase3: {by_phase.get(3, 0)} 件")
    print(f"  Phase4: {by_phase.get(4, 0)} 件")

    print(f"\n■ n_horses 分布:")
    bins_ = [0, 100, 200, 300, 500, 1000, float("inf")]
    labels = ["<100", "100-199", "200-299", "300-499", "500-999", "1000+"]
    for lo, hi, lbl in zip(bins_[:-1], bins_[1:], labels):
        n = int(((combined["n_horses"] >= lo) & (combined["n_horses"] < hi)).sum())
        if n > 0:
            print(f"    {lbl:>8s}: {n}件")

    print(f"\n■ fukusho_roi_corr 統計:")
    print(f"    min={combined['fukusho_roi_corr'].min():.2f}%  "
          f"mean={combined['fukusho_roi_corr'].mean():.2f}%  "
          f"max={combined['fukusho_roi_corr'].max():.2f}%")

    print(f"\n■ Top 10 (fukusho_roi_corr 降順):")
    cols = ["phase", "segment", "combo", "bin_key", "n_horses",
            "tansho_roi_corr", "fukusho_roi_corr", "noise_ratio", "combo_clb"]
    print(combined[cols].head(10).to_string(index=False))

    print(f"\n[OK] {OUTPUT_CSV.resolve()}")
    print("=" * 65)


if __name__ == "__main__":
    main()

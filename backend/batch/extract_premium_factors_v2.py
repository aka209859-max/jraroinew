#!/usr/bin/env python3
"""
extract_premium_factors_v2.py
==============================
ランク制採用基準でプレミアムファクターを再選別する。

【変数定義】
  W = n_horses
  N = tansho_roi_corr
  O = fukusho_roi_corr
  Y = N*0.3 + O*0.7   (ブレンド回収率)
  noise = noise_ratio

【採用ランク】
  S: Y >= 105.0 AND noise <= 40.0
  A: Y >= 100.0 AND noise <= 60.0
  B: Y >=  95.0 AND W >= 500

出力: reports/production_search/final_premium_factors.csv

Usage:
  py -3.12 -m backend.batch.extract_premium_factors_v2
"""

from pathlib import Path
import pandas as pd

# --------------------------------------------------------------------------
INPUT_DIR  = Path("reports/production_search/analyzed")
OUTPUT_CSV = Path("reports/production_search/final_premium_factors.csv")

FILES = [
    f"analyzed_phase{phase}_bins_{cls}.csv"
    for cls   in [150, 300, 500]
    for phase in [2, 3, 4]
]
# --------------------------------------------------------------------------


def assign_rank(df: pd.DataFrame) -> pd.DataFrame:
    """Y・noise・W を計算し、S/A/B ランクを付与して返す（非該当行は除外）"""
    df = df.copy()

    # 計算列
    df["Y"] = (df["tansho_roi_corr"] * 0.3 + df["fukusho_roi_corr"] * 0.7).round(4)

    # ランク判定 (S > A > B の優先順)
    cond_s = (df["Y"] >= 105.0) & (df["noise_ratio"] <= 40.0)
    cond_a = (df["Y"] >= 100.0) & (df["noise_ratio"] <= 60.0)
    cond_b = (df["Y"] >= 95.0)  & (df["n_horses"]   >= 500)

    df["rank"] = None
    df.loc[cond_b, "rank"] = "B"
    df.loc[cond_a, "rank"] = "A"   # A が B を上書き（優先）
    df.loc[cond_s, "rank"] = "S"   # S が A を上書き（最優先）

    return df[df["rank"].notna()].copy()


def main() -> None:
    print("=" * 65)
    print("  extract_premium_factors_v2")
    print("  S/A/B ランク制でプレミアムファクターを再選別")
    print("=" * 65)
    print(f"  S: Y>=105.0 AND noise<=40%")
    print(f"  A: Y>=100.0 AND noise<=60%")
    print(f"  B: Y>= 95.0 AND n_horses>=500")
    print()

    all_frames = []

    for fname in FILES:
        fpath = INPUT_DIR / fname
        if not fpath.exists():
            print(f"  [SKIP] {fname}")
            continue

        df   = pd.read_csv(fpath, encoding="utf-8-sig")
        kept = assign_rank(df)

        by_rank = kept.groupby("rank").size().to_dict() if len(kept) else {}
        s = by_rank.get("S", 0)
        a = by_rank.get("A", 0)
        b = by_rank.get("B", 0)

        marker = "★" if len(kept) > 0 else " "
        print(f"  {marker} {fname:42s} {len(df):>4}行 -> "
              f"S={s} A={a} B={b} (計{len(kept)}件)")

        if len(kept) > 0:
            all_frames.append(kept)

    # ---- 結合・重複排除 ----
    print()
    if not all_frames:
        print("[WARN] 採用ビンが0件でした。条件を確認してください。")
        return

    combined = pd.concat(all_frames, ignore_index=True)
    before   = len(combined)
    combined = combined.drop_duplicates(subset=["segment", "combo", "bin_key"])
    after    = len(combined)

    # Y 降順ソート
    combined = combined.sort_values("Y", ascending=False).reset_index(drop=True)

    # ---- 出力 ----
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

    # ---- レポート ----
    by_rank  = combined.groupby("rank").size().to_dict()
    by_phase = combined.groupby("phase").size().to_dict()

    print("=" * 65)
    print("■ 採用結果サマリー")
    print("=" * 65)
    print(f"  合計: {after} 件  (重複排除: {before - after} 件)")
    print(f"  Sランク: {by_rank.get('S', 0)} 件")
    print(f"  Aランク: {by_rank.get('A', 0)} 件")
    print(f"  Bランク: {by_rank.get('B', 0)} 件")
    print()
    print(f"  Phase別: Phase2={by_phase.get(2,0)} / "
          f"Phase3={by_phase.get(3,0)} / Phase4={by_phase.get(4,0)}")

    # ---- Y 統計 ----
    for rank in ["S", "A", "B"]:
        sub = combined[combined["rank"] == rank]
        if len(sub) == 0:
            continue
        print(f"\n  【{rank}ランク】{len(sub)}件  "
              f"Y: min={sub['Y'].min():.2f} / mean={sub['Y'].mean():.2f} / max={sub['Y'].max():.2f}")

    # ---- Sランク詳細 ----
    s_rows = combined[combined["rank"] == "S"]
    if len(s_rows) > 0:
        print(f"\n■ Sランクファクター一覧 (Y降順):")
        cols = ["phase", "segment", "combo", "bin_key", "n_horses",
                "tansho_roi_corr", "fukusho_roi_corr", "Y", "noise_ratio", "combo_clb"]
        print(s_rows[cols].to_string(index=False))
    else:
        print("\n  ※ Sランク該当なし")

    # ---- Aランク Top5 ----
    a_rows = combined[combined["rank"] == "A"]
    if len(a_rows) > 0:
        print(f"\n■ Aランクファクター Top5 (Y降順):")
        cols = ["phase", "segment", "combo", "bin_key", "n_horses",
                "tansho_roi_corr", "fukusho_roi_corr", "Y", "noise_ratio", "combo_clb"]
        print(a_rows[cols].head(5).to_string(index=False))

    print(f"\n[OK] {OUTPUT_CSV.resolve()}")
    print("=" * 65)


if __name__ == "__main__":
    main()

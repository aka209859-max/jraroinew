#!/usr/bin/env python3
"""
export_fragmentation_analysis.py
==================================
9つの「純金ビンCSV」全行に細分化ストレステストを実行し、
結果カラムを付与した新しいCSVを出力する。

【分割ファクター戦略】
  Primary  : keibajo_code（10値、GLOBALなど広域セグメント向け）
  Fallback : kyori_kubun → tenkai_kigo_code → class_code → pace_yoso
             （KEIBAJO_SURFACE 系は keibajo_code が1値のため自動フォールバック）

【追加カラム】
  split_factor    : 使用した分割ファクター名
  sub_bins_count  : 分割後サブビン総数
  sub_bins_sizes  : 各サブビンの件数（降順カンマ区切り文字列）
  noise_bins_count: 50件未満のサブビン数
  noise_ratio     : ノイズ化率（%）

出力先: reports/production_search/analyzed/

Usage:
  py -3.12 -u -m backend.batch.export_fragmentation_analysis
"""

import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from backend.batch.factor_investment_screening import load_and_prepare
from backend.batch.master_combo_pipeline import (
    add_class_column,
    build_production_segments,
)

# --------------------------------------------------------------------------
INPUT_DIR  = Path("reports/production_search")
OUTPUT_DIR = Path("reports/production_search/analyzed")

PHASES  = [2, 3, 4]
CLASSES = [150, 300, 500]

# 分割ファクター優先順（先頭から試して2値以上あるものを採用）
SPLIT_PRIORITY = [
    "keibajo_code",      # 競馬場（10値） ← primary
    "kyori_kubun",       # 距離区分（4値）
    "tenkai_kigo_code",  # 展開機号（5値）
    "class_code",        # クラスコード（~10値）
    "pace_yoso",         # ペース予想（3値: H/M/S）
]

NOISE_THRESHOLD = 50   # これ未満のサブビンをノイズと見なす
MIN_UNIQUE      = 2    # 分割ファクターに必要な最低ユニーク数
# --------------------------------------------------------------------------


def _pick_split_factor(
    sub_df: pd.DataFrame,
    exclude: List[str],
) -> Optional[str]:
    """サブDF内でユニーク数が最も多い有効ファクターを返す"""
    best_f, best_n = None, 0
    for f in SPLIT_PRIORITY:
        if f in exclude or f not in sub_df.columns:
            continue
        n_unique = sub_df[f].nunique()
        if n_unique >= MIN_UNIQUE and n_unique > best_n:
            best_f, best_n = f, n_unique
    return best_f


def _reconstruct_bin_df(
    seg_df: pd.DataFrame,
    factors: List[str],
    bin_key: str,
) -> pd.DataFrame:
    """combo + bin_key からビン内データを復元する"""
    values = bin_key.split("|")
    if len(values) != len(factors):
        return pd.DataFrame()
    mask = pd.Series(True, index=seg_df.index)
    for f, v in zip(factors, values):
        if f not in seg_df.columns:
            return pd.DataFrame()
        mask &= seg_df[f].astype(str).str.strip() == v.strip()
    return seg_df[mask]


def _analyze_row(
    row: pd.Series,
    seg_map: Dict[str, pd.DataFrame],
) -> Dict:
    """1ビン行の細分化分析を実行し、追加カラム値を返す"""
    seg_name = str(row["segment"])
    seg_df   = seg_map.get(seg_name)
    if seg_df is None:
        return _na_result("segment_not_found")

    factors  = [f.strip() for f in str(row["combo"]).split("+")]
    bin_key  = str(row["bin_key"])
    bin_df   = _reconstruct_bin_df(seg_df, factors, bin_key)
    if bin_df.empty:
        return _na_result("bin_reconstruct_failed")

    split_f = _pick_split_factor(bin_df, exclude=factors)
    if split_f is None:
        return _na_result("no_valid_split_factor")

    counts = bin_df.groupby(split_f, sort=False).size().sort_values(ascending=False)
    sizes  = list(counts.values)
    total  = len(sizes)
    noise  = int(sum(1 for s in sizes if s < NOISE_THRESHOLD))
    noise_ratio = round(noise / total * 100, 1) if total > 0 else 0.0

    return {
        "split_factor":     split_f,
        "sub_bins_count":   total,
        "sub_bins_sizes":   ",".join(str(s) for s in sizes),
        "noise_bins_count": noise,
        "noise_ratio":      noise_ratio,
    }


def _na_result(reason: str) -> Dict:
    return {
        "split_factor":     reason,
        "sub_bins_count":   0,
        "sub_bins_sizes":   "",
        "noise_bins_count": 0,
        "noise_ratio":      float("nan"),
    }


def process_file(
    csv_path: Path,
    seg_map: Dict[str, pd.DataFrame],
    output_path: Path,
) -> Tuple[int, float]:
    """1ファイルを処理して結果CSVを出力。(行数, 平均ノイズ率) を返す"""
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    results = []
    for _, row in df.iterrows():
        results.append(_analyze_row(row, seg_map))

    extra = pd.DataFrame(results)
    out_df = pd.concat([df.reset_index(drop=True), extra], axis=1)
    out_df.to_csv(output_path, index=False, encoding="utf-8-sig")

    valid = out_df["noise_ratio"].dropna()
    avg_noise = round(float(valid.mean()), 1) if len(valid) > 0 else float("nan")
    return len(df), avg_noise


def main() -> None:
    t0 = time.time()
    print("=" * 70)
    print("  export_fragmentation_analysis")
    print("  全9ファイル × 全ビン 細分化ストレステスト & CSV出力")
    print("=" * 70)

    # ---- データロード ----
    print("\n[LOAD] データロード中...")
    df = load_and_prepare(row_limit=0)
    df = add_class_column(df)
    seg_map = build_production_segments(df)
    print(f"[INFO] {len(df):,} rows, {len(seg_map)} segments")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ---- 9ファイル処理 ----
    print("\n[PROC] 処理開始...\n")
    summary_rows = []

    for cls in CLASSES:
        for phase in PHASES:
            in_path  = INPUT_DIR / f"phase{phase}_bins_{cls}.csv"
            out_path = OUTPUT_DIR / f"analyzed_phase{phase}_bins_{cls}.csv"

            if not in_path.exists():
                print(f"  [SKIP] {in_path.name} - ファイル未存在")
                continue

            n_rows, avg_noise = process_file(in_path, seg_map, out_path)
            label = f"phase{phase}_bins_{cls}.csv"
            print(f"  [OK] {label:30s}  {n_rows:>4} 行  avg_noise={avg_noise:.1f}%")
            summary_rows.append({
                "file":      label,
                "class":     cls,
                "phase":     phase,
                "rows":      n_rows,
                "avg_noise": avg_noise,
            })

    # ---- サマリー表 ----
    elapsed = time.time() - t0
    print(f"\n[完了] elapsed={elapsed:.1f}s ({elapsed/60:.1f}min)")

    print("\n" + "=" * 70)
    print("■ 細分化ノイズ率サマリー (keibajo_code 追加 / ノイズ閾値<50件)")
    print("=" * 70)
    sm = pd.DataFrame(summary_rows)

    print(f"\n{'ファイル名':35s} {'行数':>5} {'avg_noise%':>11}")
    print("-" * 55)
    for _, r in sm.iterrows():
        print(f"  {r['file']:33s} {int(r['rows']):>5}行  {r['avg_noise']:>9.1f}%")

    # クラス別サマリー
    print("\n■ クラス別 平均ノイズ率:")
    for cls in CLASSES:
        sub = sm[sm["class"] == cls]
        avg = round(float(sub["avg_noise"].mean()), 1)
        total = int(sub["rows"].sum())
        print(f"  {cls}件クラス: {total:>5}行  avg_noise={avg:.1f}%")

    print(f"\n出力先: {OUTPUT_DIR.resolve()}")
    print("=" * 70)


if __name__ == "__main__":
    main()

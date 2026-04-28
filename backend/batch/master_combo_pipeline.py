#!/usr/bin/env python3
"""
master_combo_pipeline.py
=========================
本番スケールの全セグメント × 全フェーズ COMBO探索パイプライン。

【フェーズ構成】
  Phase 1: COMBO 1 — 全プロダクションセグメントでの単独ファクタースクリーニング
  Phase 2: COMBO 2 — Phase 1 上位40ファクターのペア (C(40,2)=780) 探索
  Phase 3: COMBO 3 — Phase 2 上位25ファクターの3-COMBO (C(25,3)=2300) 探索
  Phase 4: COMBO 4 — Phase 3 精鋭3-COMBOへ1ファクター追加の4-COMBO探索

【プロダクションセグメント一覧 (~209)】
  マクロ枠:
    GLOBAL, SURFACE_2_芝, SURFACE_2_ダ,
    KEIBAJO_SURFACE_XX_YY (~20 segments),
    COURSE_27_XX_YY_ZZ (~27 segments)
  クラス細分化枠 (マクロ × 6 クラス — COURSE_27 除く):
    GLOBAL_[class], SURFACE_2_芝_[class], SURFACE_2_ダ_[class],
    KEIBAJO_SURFACE_XX_YY_[class]

【評価式】
  factor_4combo_targeted.py の SegmentCache 完全準拠。
  CLB = mean(bin_rois) - 1.96 × std(bin_rois) / √K

【チェックポイント (2層)】
  Layer 1: pipeline_master.json — 完了セグメントリスト
  Layer 2: per-segment combo1_results.csv の存在確認でリカバリ

Usage:
  py -3.12 -m backend.batch.master_combo_pipeline --phase 1
  py -3.12 -m backend.batch.master_combo_pipeline --phase 1 --resume
  py -3.12 -m backend.batch.master_combo_pipeline --phase 1 --dry-run
  py -3.12 -m backend.batch.master_combo_pipeline --phase 1 --seg-filter GLOBAL
  py -3.12 -m backend.batch.master_combo_pipeline --phase 1 --min-rows 1000

Output:
  reports/production_search/segments/{seg}/combo1_results.csv
  reports/production_search/checkpoints/pipeline_master.json
  reports/production_search/combo1_summary.csv
"""

import argparse
import json
import math
import sys
import time
from itertools import combinations
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# 共通インフラ再利用
# --------------------------------------------------------------------------
from backend.batch.factor_investment_screening import (
    load_and_prepare,
    TARGET_PAYOUT,
)
from backend.batch.factor_3combo_screening import _get_col_1d
from backend.batch.factor_4combo_targeted import SegmentCache
from backend.batch.factor_screening import (
    ALL_FACTORS,
    compute_derived_factors,
)

# --------------------------------------------------------------------------
# 定数
# --------------------------------------------------------------------------
BIN_MIN_N      = 100    # 有効ビンの最小サンプル数（Phase 1〜4 共通）
MIN_VALID_BINS = 3      # CLB計算に必要な最小ビン数
CLB_THRESHOLD  = 80.0  # 採用基準: CLB >= この値 (%)

# Phase 2〜3 の上位ファクター数
N_MAX_P2 = 40   # Phase 2: 上位40ファクターのペアを探索
N_MAX_P3 = 25   # Phase 3: 上位25ファクターの3-COMBOを探索 (C(25,3)=2,300)

# 最小セグメントサイズ: これ未満の行数のセグメントは skip
DEFAULT_MIN_ROWS = 1_000

# joken_class_code (jrd_kyi_fixed) → クラスラベルのマッピング
# 注: bac_jouken の A1/A3 は joken_class_code=0 に統合されるため、
#     2勝/3勝の分離はデータ上困難。5クラスで運用。
_JOKEN_CLASS_MAP: Dict[str, str] = {
    "1": "新馬",
    "2": "未勝利",
    "3": "1勝クラス",
    "0": "条件戦",    # 2勝+3勝条件を一括 (bac_jouken A1/A3)
    "9": "OP重賞",
}
# セグメント名に使うクラスラベル（joken_class_code の 5クラス）
RACE_CLASSES = list(_JOKEN_CLASS_MAP.values())  # ["新馬","未勝利","1勝クラス","条件戦","OP重賞"]

# プロダクションファクター定義
# ALL_FACTORS (50) + kyori_kubun (compute_derived_factors で計算済み)
_EXTRA_FACTORS: List[Tuple[str, str, str]] = [
    ("kyori_kubun", "距離区分", "code"),
]

def _build_prod_factors() -> List[Tuple[str, str, str]]:
    existing_cols = {c for c, _, _ in ALL_FACTORS}
    extra = [(c, lbl, t) for c, lbl, t in _EXTRA_FACTORS if c not in existing_cols]
    return list(ALL_FACTORS) + extra

PROD_FACTORS: List[Tuple[str, str, str]] = _build_prod_factors()
PROD_FACTOR_NAMES: List[str] = [c for c, _, _ in PROD_FACTORS]

# 出力先
OUTPUT_BASE       = Path("reports/production_search")
CHECKPOINT_DIR    = OUTPUT_BASE / "checkpoints"
SEGMENTS_DIR      = OUTPUT_BASE / "segments"
MASTER_CP_FILE    = CHECKPOINT_DIR / "pipeline_master.json"
COMBO1_SUMMARY    = OUTPUT_BASE / "combo1_summary.csv"


# --------------------------------------------------------------------------
# クラス列の付加
# --------------------------------------------------------------------------
def add_class_column(df: pd.DataFrame) -> pd.DataFrame:
    """
    _race_class 列を joken_class_code から生成。

    joken_class_code (jrd_kyi_fixed):
      '1' → 新馬  '2' → 未勝利  '3' → 1勝クラス  '0' → 条件戦  '9' → OP重賞

    注: bac_jouken の A1/A3 は joken_class_code=0 に統合されており、
        2勝/3勝の分離はデータ上困難なため 5クラスで運用する。
    """
    if "joken_class_code" not in df.columns:
        print("[WARN] joken_class_code カラムが存在しない — _race_class はすべて None")
        df["_race_class"] = None
        return df
    df = df.copy()
    raw = df["joken_class_code"].astype(str).str.strip().replace({"nan": None, "None": None, "": None})
    df["_race_class"] = raw.map(_JOKEN_CLASS_MAP)
    coverage = df["_race_class"].notna().mean() * 100
    dist = df["_race_class"].value_counts().to_dict()
    print(f"[INFO] _race_class カバレッジ: {coverage:.1f}%  分布: {dist}")
    return df


# --------------------------------------------------------------------------
# プロダクションセグメントの構築
# --------------------------------------------------------------------------
def build_production_segments(
    df: pd.DataFrame,
    min_rows: int = DEFAULT_MIN_ROWS,
) -> Dict[str, pd.DataFrame]:
    """
    ~209 のプロダクションセグメントを構築して辞書を返す。

    マクロ枠:
      GLOBAL, SURFACE_2_芝, SURFACE_2_ダ,
      KEIBAJO_SURFACE_{kb}_{surf}, COURSE_27_{kb}_{surf}_{kubun}

    クラス細分化枠 (COURSE_27 は除く):
      {マクロ名}_{class} for class in RACE_CLASSES
    """
    segs: Dict[str, pd.DataFrame] = {}

    def add_seg(name: str, sub: pd.DataFrame) -> None:
        if len(sub) >= min_rows:
            segs[name] = sub.reset_index(drop=True)

    # -- GLOBAL
    add_seg("GLOBAL", df)

    # -- SURFACE_2
    if "surface" in df.columns:
        for surf in ["芝", "ダ"]:
            sub = df[df["surface"] == surf]
            add_seg(f"SURFACE_2_{surf}", sub)

    # -- KEIBAJO_SURFACE
    if "keibajo_code" in df.columns and "surface" in df.columns:
        for (kb, surf), sub in df.groupby(["keibajo_code", "surface"], observed=True):
            if surf not in ("芝", "ダ"):
                continue
            add_seg(f"KEIBAJO_SURFACE_{kb}_{surf}", sub)

    # -- COURSE_27
    if "course_27" in df.columns:
        for ckey, sub in df.groupby("course_27", observed=True):
            ckey_str = str(ckey).replace(" ", "_")
            add_seg(f"COURSE_27_{ckey_str}", sub)

    # -- クラス細分化枠 (GLOBAL, SURFACE_2, KEIBAJO_SURFACE の各マクロ × 6クラス)
    if "_race_class" in df.columns:
        macro_names = [n for n in list(segs.keys()) if not n.startswith("COURSE_27")]
        for macro_name in macro_names:
            macro_df = segs[macro_name]
            for rc in RACE_CLASSES:
                sub = macro_df[macro_df["_race_class"] == rc]
                add_seg(f"{macro_name}_{rc}", sub)

    print(f"[INFO] 構築セグメント数: {len(segs)}")
    return segs


# --------------------------------------------------------------------------
# チェックポイント I/O
# --------------------------------------------------------------------------
def load_master_checkpoint() -> Dict:
    if MASTER_CP_FILE.exists():
        with open(MASTER_CP_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {
        "phase1_completed": [],
        "phase2_completed": [],
        "phase3_completed": [],
        "phase4_completed": [],
    }


def save_master_checkpoint(cp: Dict) -> None:
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    with open(MASTER_CP_FILE, "w", encoding="utf-8") as f:
        json.dump(cp, f, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------
# Phase 1: COMBO 1 — 単独ファクタースクリーニング
# --------------------------------------------------------------------------
def _evaluate_single_factor(
    cache: SegmentCache,
    factor: str,
    label: str,
    ftype: str,
) -> Optional[Dict]:
    """1ファクターを SegmentCache で評価。"""
    if not cache.has_factor(factor):
        return None
    result = cache.evaluate_combo([factor], bin_min_n=BIN_MIN_N, min_bins=MIN_VALID_BINS)
    if result is None:
        return None
    return {
        "factor":    factor,
        "label":     label,
        "ftype":     ftype,
        "n_bins":    result["n_valid_bins"],
        "n_bets":    result["n_valid_bets"],
        "mean_roi":  result["mean_corrected_roi"],
        "std_roi":   result["std_bin_roi"],
        "clb":       result["clb"],
        "pass":      result["pass"],
    }


def _run_phase1_segment(
    seg_name: str,
    seg_df: pd.DataFrame,
    factors: List[Tuple[str, str, str]],
    out_dir: Path,
) -> Optional[pd.DataFrame]:
    """
    1セグメントの Phase 1 を実行してCSVに保存。
    既存ファイルがある場合はスキップ（Layer 2 チェックポイント）。
    """
    out_csv = out_dir / "combo1_results.csv"
    if out_csv.exists():
        df = pd.read_csv(out_csv)
        print(f"  [SKIP] {seg_name} — 既存結果 ({len(df)} ファクター)")
        return df

    factor_names = [c for c, _, _ in factors]
    cache = SegmentCache(seg_df, factor_names)

    rows = []
    for col, label, ftype in factors:
        r = _evaluate_single_factor(cache, col, label, ftype)
        if r is not None:
            rows.append(r)

    if not rows:
        print(f"  [SKIP] {seg_name} — 有効ファクターなし")
        return None

    result_df = pd.DataFrame(rows)
    result_df = result_df.sort_values("clb", ascending=False).reset_index(drop=True)

    out_dir.mkdir(parents=True, exist_ok=True)
    result_df.to_csv(out_csv, index=False, encoding="utf-8-sig")

    n_pass = int(result_df["pass"].sum())
    best_clb = result_df["clb"].max()
    print(f"  [OK] {seg_name}: {len(result_df)} ファクター評価 / {n_pass} pass / best CLB={best_clb:.2f}%")
    return result_df


def run_phase1(
    seg_map: Dict[str, pd.DataFrame],
    cp: Dict,
    factors: List[Tuple[str, str, str]],
    seg_filter: Optional[str] = None,
) -> pd.DataFrame:
    """
    全セグメントで Phase 1 (単独ファクター評価) を実行。
    Returns: summary DataFrame
    """
    completed: Set[str] = set(cp.get("phase1_completed", []))
    seg_names = sorted(seg_map.keys())
    if seg_filter:
        seg_names = [s for s in seg_names if seg_filter in s]
        print(f"[INFO] --seg-filter '{seg_filter}' → {len(seg_names)} セグメント")

    summary_rows = []
    t0 = time.time()

    for i, seg_name in enumerate(seg_names, 1):
        seg_df = seg_map[seg_name]
        out_dir = SEGMENTS_DIR / seg_name

        # Layer 2 チェック: 既存CSVがあれば完了扱い
        out_csv = out_dir / "combo1_results.csv"
        already_done = seg_name in completed or out_csv.exists()

        print(f"[{i}/{len(seg_names)}] {seg_name}  rows={len(seg_df):,}  "
              f"{'(done)' if already_done else ''}")

        result_df = _run_phase1_segment(seg_name, seg_df, factors, out_dir)

        if result_df is not None:
            n_pass = int(result_df["pass"].sum())
            summary_rows.append({
                "segment":    seg_name,
                "n_rows":     len(seg_df),
                "n_factors":  len(result_df),
                "n_pass":     n_pass,
                "best_clb":   round(result_df["clb"].max(), 2),
                "best_factor": result_df.iloc[0]["factor"] if len(result_df) > 0 else None,
            })
        else:
            summary_rows.append({
                "segment":    seg_name,
                "n_rows":     len(seg_df),
                "n_factors":  0,
                "n_pass":     0,
                "best_clb":   None,
                "best_factor": None,
            })

        # Layer 1 チェックポイント更新
        if seg_name not in completed:
            completed.add(seg_name)
            cp["phase1_completed"] = sorted(completed)
            save_master_checkpoint(cp)

    elapsed = time.time() - t0
    print(f"\n[Phase 1 完了] {len(seg_names)} セグメント / {elapsed:.1f}s")

    summary_df = pd.DataFrame(summary_rows)
    OUTPUT_BASE.mkdir(parents=True, exist_ok=True)
    summary_df.to_csv(COMBO1_SUMMARY, index=False, encoding="utf-8-sig")
    print(f"[OK] サマリー保存: {COMBO1_SUMMARY}")
    return summary_df


# --------------------------------------------------------------------------
# Phase 2〜4 スタブ
# --------------------------------------------------------------------------
def run_phase2(seg_map, cp, factors, seg_filter=None):
    print("[INFO] Phase 2 (COMBO 2) は未実装です。Phase 1 完了後に実装予定。")


def run_phase3(seg_map, cp, factors, seg_filter=None):
    print("[INFO] Phase 3 (COMBO 3) は未実装です。Phase 2 完了後に実装予定。")


def run_phase4(seg_map, cp, factors, seg_filter=None):
    print("[INFO] Phase 4 (COMBO 4) は未実装です。Phase 3 完了後に実装予定。")


# --------------------------------------------------------------------------
# dry-run: セグメント一覧の表示
# --------------------------------------------------------------------------
def dry_run(seg_map: Dict[str, pd.DataFrame]) -> None:
    macro_segs = [n for n in seg_map if not any(rc in n for rc in RACE_CLASSES)]
    class_segs = [n for n in seg_map if any(rc in n for rc in RACE_CLASSES)]

    print(f"\n=== DRY RUN: {len(seg_map)} セグメント ===")
    print(f"  マクロ枠: {len(macro_segs)}")
    print(f"  クラス枠: {len(class_segs)}")
    print(f"  ファクター数: {len(PROD_FACTORS)}")
    print(f"\n--- マクロ枠 ({len(macro_segs)}) ---")
    for s in sorted(macro_segs):
        n = len(seg_map[s])
        print(f"  {s:<50}  rows={n:>8,}")
    print(f"\n--- クラス枠 ({len(class_segs)}) ---")
    for s in sorted(class_segs):
        n = len(seg_map[s])
        print(f"  {s:<60}  rows={n:>7,}")

    total_tasks = sum(len(seg_map[s]) > 0 for s in seg_map) * len(PROD_FACTORS)
    print(f"\n  Phase 1 推定タスク数: {total_tasks:,}")


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="本番スケール COMBO 探索パイプライン")
    parser.add_argument("--phase",      type=int,  default=1,
                        help="実行フェーズ (1=COMBO1, 2=COMBO2, 3=COMBO3, 4=COMBO4)")
    parser.add_argument("--resume",     action="store_true",
                        help="チェックポイントから再開")
    parser.add_argument("--dry-run",    action="store_true",
                        help="セグメント一覧のみ表示して終了")
    parser.add_argument("--seg-filter", type=str,  default=None,
                        help="セグメント名に含む文字列でフィルタ")
    parser.add_argument("--min-rows",   type=int,  default=DEFAULT_MIN_ROWS,
                        help=f"セグメントの最小行数 (default={DEFAULT_MIN_ROWS})")
    parser.add_argument("--limit",      type=int,  default=0,
                        help="DBから読み込む行数の上限 (0=無制限, テスト用)")
    args = parser.parse_args()

    print("=" * 60)
    print("  Enable Edge Engine - Master Combo Pipeline")
    print(f"  Phase {args.phase}  /  {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # --- データ読み込み ---
    print("\n[STEP 1] データ読み込み...")
    df = load_and_prepare(row_limit=args.limit)
    print(f"[INFO] 総行数: {len(df):,}")

    # --- クラス列付加 ---
    print("\n[STEP 2] クラス列付加...")
    df = add_class_column(df)

    # --- セグメント構築 ---
    print("\n[STEP 3] セグメント構築...")
    seg_map = build_production_segments(df, min_rows=args.min_rows)

    # --- dry-run ---
    if args.dry_run:
        dry_run(seg_map)
        return

    # --- チェックポイント ---
    if args.resume:
        cp = load_master_checkpoint()
        print(f"[INFO] チェックポイント読み込み: "
              f"Phase1 完了={len(cp.get('phase1_completed', []))} セグメント")
    else:
        cp = load_master_checkpoint()  # 既存があれば読む（--resume なしでも継続可）

    factors = PROD_FACTORS

    # --- フェーズ実行 ---
    print(f"\n[STEP 4] Phase {args.phase} 実行...")
    if args.phase == 1:
        summary = run_phase1(seg_map, cp, factors, seg_filter=args.seg_filter)
        _print_phase1_summary(summary)
    elif args.phase == 2:
        run_phase2(seg_map, cp, factors, seg_filter=args.seg_filter)
    elif args.phase == 3:
        run_phase3(seg_map, cp, factors, seg_filter=args.seg_filter)
    elif args.phase == 4:
        run_phase4(seg_map, cp, factors, seg_filter=args.seg_filter)
    else:
        print(f"[ERROR] 未知のフェーズ: {args.phase}")
        sys.exit(1)


def _print_phase1_summary(summary: pd.DataFrame) -> None:
    total_segs  = len(summary)
    valid_segs  = int((summary["n_factors"] > 0).sum())
    total_pass  = int(summary["n_pass"].sum())
    segs_w_pass = int((summary["n_pass"] > 0).sum())

    print("\n" + "=" * 60)
    print("  Phase 1 サマリー")
    print("=" * 60)
    print(f"  総セグメント数:         {total_segs}")
    print(f"  有効セグメント:         {valid_segs}")
    print(f"  CLB>=80% pass総数:     {total_pass}")
    print(f"  pass有りセグメント:     {segs_w_pass}")

    if valid_segs > 0:
        top = summary.nlargest(10, "best_clb")[["segment", "n_rows", "n_pass", "best_clb", "best_factor"]]
        print(f"\n  Top 10 セグメント (CLB降順):")
        for _, row in top.iterrows():
            print(f"    {row['segment']:<55} CLB={row['best_clb']:.2f}%  pass={row['n_pass']}  best={row['best_factor']}")
    print("=" * 60)


if __name__ == "__main__":
    main()

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

【メモリ最適化 v2】
  全セグメントを一括構築するのではなく、1セグメントずつオンデマンドに
  構築→処理→解放することでメモリ使用量を大幅削減。

出力: reports/production_search/master_bin_metrics_cleaned.csv

Usage:
  py -3.12 -u -m backend.batch.clean_and_reextract_bins
"""

import gc
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from backend.batch.factor_investment_screening import load_and_prepare
from backend.batch.master_combo_pipeline import (
    add_class_column,
    SEGMENTS_DIR,
    RACE_CLASSES,
    DEFAULT_MIN_ROWS,
)
from backend.batch.extract_bin_metrics import _bin_metrics

# --------------------------------------------------------------------------
OUTPUT_CSV = Path("reports/production_search/master_bin_metrics_cleaned.csv")
MIN_BIN_N  = 50    # 単勝・複勝ともにこれ未満のビンは除外
P1_CLB_THRESHOLD  = 75.0  # Phase 1 専用閾値
P24_CLB_THRESHOLD = 80.0  # Phase 2~4 閾値（pass==True と同値）
_SURFS = ("芝", "ダ")
_KBS = [f"{i:02d}" for i in range(1, 11)]  # "01" .. "10"
# --------------------------------------------------------------------------


def _build_one_segment(
    df_full: pd.DataFrame,
    seg_name: str,
    min_rows: int = DEFAULT_MIN_ROWS,
) -> Optional[pd.DataFrame]:
    """
    セグメント名からフィルタ条件を復元し、DataFrameを1つだけ構築して返す。
    全セグメントを同時保持しないためメモリ効率が良い。
    """
    # ---- GLOBAL ----
    if seg_name == "GLOBAL":
        return df_full if len(df_full) >= min_rows else None

    # GLOBAL_{class}
    if seg_name.startswith("GLOBAL_"):
        rc = seg_name[7:]
        sub = df_full[df_full["_race_class"] == rc]
        return sub.reset_index(drop=True) if len(sub) >= min_rows else None

    # ---- COURSE_27_{ckey} ----
    if seg_name.startswith("COURSE_27_"):
        ckey = seg_name[10:]  # e.g. "右回り急坂U字_芝"
        sub = df_full[df_full["course_27"] == ckey]
        return sub.reset_index(drop=True) if len(sub) >= min_rows else None

    # ---- SURFACE_2_{surf} or SURFACE_2_{surf}_{class} ----
    if seg_name.startswith("SURFACE_2_"):
        rest = seg_name[10:]
        for surf in _SURFS:
            if rest == surf:
                sub = df_full[df_full["surface"] == surf]
                return sub.reset_index(drop=True) if len(sub) >= min_rows else None
            if rest.startswith(f"{surf}_"):
                rc = rest[len(surf) + 1:]
                sub = df_full[
                    (df_full["surface"] == surf) &
                    (df_full["_race_class"] == rc)
                ]
                return sub.reset_index(drop=True) if len(sub) >= min_rows else None

    # ---- KEIBAJO_SURFACE_{kb}_{surf} or KEIBAJO_SURFACE_{kb}_{surf}_{class} ----
    if seg_name.startswith("KEIBAJO_SURFACE_"):
        rest = seg_name[16:]  # e.g. "06_芝" or "06_ダ_条件戦"
        for kb in _KBS:
            for surf in _SURFS:
                prefix = f"{kb}_{surf}"
                if rest == prefix:
                    sub = df_full[
                        (df_full["keibajo_code"] == kb) &
                        (df_full["surface"] == surf)
                    ]
                    return sub.reset_index(drop=True) if len(sub) >= min_rows else None
                if rest.startswith(f"{prefix}_"):
                    rc = rest[len(prefix) + 1:]
                    sub = df_full[
                        (df_full["keibajo_code"] == kb) &
                        (df_full["surface"] == surf) &
                        (df_full["_race_class"] == rc)
                    ]
                    return sub.reset_index(drop=True) if len(sub) >= min_rows else None

    return None  # unknown segment pattern


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
    print("  clean_and_reextract_bins  [memory-efficient v2]")
    print("  Phase1 CLB>=75.0 / Phase2-4 CLB>=80.0 / min_bin_n=50")
    print("=" * 60)

    # ---- データロード ----
    print("\n[STEP 1] データロード...")
    df = load_and_prepare(row_limit=0)
    print(f"[INFO] {len(df):,} rows, {len(df.columns)} cols")

    # ---- クラス列追加 ----
    print("\n[STEP 2] クラス列追加...")
    df = add_class_column(df)
    print(f"[INFO] _race_class 分布: {df['_race_class'].value_counts().to_dict()}")

    # ---- COMBO 収集 ----
    print("\n[STEP 3] COMBO 収集...")
    combos = _collect_combos()
    by_phase = {p: sum(1 for c in combos if c["phase"] == p) for p in [1, 2, 3, 4]}
    print(f"[INFO] 採用COMBO数: {len(combos):,}")
    for p in [1, 2, 3, 4]:
        print(f"  Phase{p}: {by_phase[p]}")

    # ---- セグメント別にグループ化 ----
    combos_by_seg: Dict[str, List[Dict]] = defaultdict(list)
    for c in combos:
        combos_by_seg[c["segment"]].append(c)

    print(f"[INFO] ユニークセグメント数: {len(combos_by_seg)}")

    # ---- ビン集計 (1セグメントずつ処理 → メモリ節約) ----
    print("\n[STEP 4] ビン集計 (1セグメントずつ処理)...")
    all_rows = []
    n_skip   = 0
    seg_total = len(combos_by_seg)

    for seg_i, (seg_name, seg_combos) in enumerate(sorted(combos_by_seg.items()), 1):
        # 対象セグメントだけ構築
        seg_df = _build_one_segment(df, seg_name)
        if seg_df is None:
            n_skip += len(seg_combos)
            print(f"  [{seg_i:3d}/{seg_total}] SKIP {seg_name} (not found or too small)")
            continue

        for c in seg_combos:
            all_rows.extend(_bin_metrics(
                seg_df, c["factors"],
                c["phase"], c["segment"], c["combo"],
                c["combo_clb"], c["combo_mean_roi"],
            ))

        del seg_df
        gc.collect()

        if seg_i % 10 == 0 or seg_i == seg_total:
            print(f"  [{seg_i:3d}/{seg_total}] ビン行数: {len(all_rows):,}  skip={n_skip}")

    print(f"[INFO] 集計完了: {len(all_rows):,} ビン行 (フィルタ前)  skip={n_skip}")

    # ---- フィルタ: tansho_n >= 50 AND fukusho_n >= 50 ----
    print("\n[STEP 5] ノイズビン除外 (tansho_n >= 50 AND fukusho_n >= 50)...")
    raw_df = pd.DataFrame(all_rows)
    del all_rows
    gc.collect()

    before = len(raw_df)
    keep = (
        (raw_df["tansho_n"].fillna(0) >= MIN_BIN_N) &
        (raw_df["fukusho_n"].fillna(0) >= MIN_BIN_N)
    )
    result_df = raw_df[keep].copy()
    del raw_df
    gc.collect()

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

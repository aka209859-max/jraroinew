#!/usr/bin/env python3
"""
factor_4combo_filtering.py
===========================
4-COMBOスクリーニング結果（512件）に対して3段階の過酷フィルターを適用し、
"真の精鋭" 4-COMBOを抽出する。

【フィルター設計（3-combo版と同一閾値）】
  Filter 1: OOT安定性（2023-2025）
    - OOT期間 (yy_int >= 23) のみで再評価
    - OOT_BIN_MIN_N=30, OOT_MIN_BINS=2
    - OOT_CLB >= 75.0%
    - 年別最低ROI >= 60.0%

  Filter 2: 印コード逆張りグリッドサーチ
    - shirushi_code_* 含有時のみ適用（非含有は自動通過）
    - Grid: tansho_odds_numeric >= [5,8,10,15] OR kijun_ninkijun_tansho >= [3,5,7]
    - best_CLB >= 78.0%

  Filter 3: クロスゲイン（4-COMBO独自性検証）
    - サブセット最大14パターン（C(4,1)+C(4,2)+C(4,3) = 4+6+4）を新式で再計算
    - cross_gain = combo4_clb - max(全サブセットCLB) >= 0.0%

【高速化】
  SegmentCache（factor_4combo_targeted.py 由来）を再利用。
  全ファクターを事前numpy配列化 → 内側ループでpandasアクセスゼロ。

Output:
  reports/screening/4combo_filtered.csv      (全Filter通過)
  reports/screening/4combo_filter_detail.csv (512件全フィルター詳細)

Usage:
  py -3.12 -m backend.batch.factor_4combo_filtering
  py -3.12 -m backend.batch.factor_4combo_filtering --limit 20  # テスト
"""

import argparse
import math
import sys
import time
from itertools import combinations as _combinations
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# 共通インフラ再利用
from backend.batch.factor_investment_screening import (
    load_and_prepare,
    build_seg_df_map,
    prepare_corrected_cols,
    ODDS_THRESHOLDS,
    RANK_THRESHOLDS,
)
# SegmentCache（numpy配列事前展開による高速化）
from backend.batch.factor_4combo_targeted import SegmentCache

# --------------------------------------------------------------------------
# 定数
# --------------------------------------------------------------------------
OUTPUT_DIR   = Path("reports/screening")
INPUT_CSV    = OUTPUT_DIR / "4combo_results.csv"
FILTERED_CSV = OUTPUT_DIR / "4combo_filtered.csv"
DETAIL_CSV   = OUTPUT_DIR / "4combo_filter_detail.csv"

# ── Filter 1: OOT ──────────────────────────────────────────────────────────
OOT_YY_MIN      = 23
OOT_BIN_MIN_N   = 30
OOT_MIN_BINS    = 2
OOT_CLB_THRESH  = 75.0
OOT_MIN_YR_ROI  = 60.0

# ── Filter 2: Shirushi ──────────────────────────────────────────────────────
SHIRUSHI_PREFIX = "shirushi_code"
SHIRUSHI_CLB    = 78.0

# ── Filter 3: Cross-gain ──────────────────────────────────────────────────
CROSS_GAIN_MIN  = 0.0
SUBSET_MIN_N    = 100


# --------------------------------------------------------------------------
# OOT/Shirushi/CrossGain の各評価は SegmentCache.evaluate_combo() を活用
# --------------------------------------------------------------------------

def _calc_yearly_roi_cache(
    cache: SegmentCache,
    seg_df: pd.DataFrame,
    factors: List[str],
    yy: int,
) -> Optional[float]:
    """
    指定年 (yy_int == yy) のOOTデータプールで単純補正ROIを返す。
    SegmentCacheを使わず seg_df を直接フィルタ（年単位は小さいため許容）。
    """
    yr_df = seg_df[seg_df["yy_int"] == yy]
    if len(yr_df) < 10:
        return None

    from backend.batch.factor_3combo_filtering import _get_col_1d

    # valid mask
    valid_mask = yr_df[factors[0]].notna()
    for f in factors[1:]:
        valid_mask = valid_mask & yr_df[f].notna()
    if isinstance(valid_mask, pd.DataFrame):
        valid_mask = valid_mask.iloc[:, 0]
    if int(valid_mask.sum()) < 10:
        return None

    mask_arr = valid_mask.to_numpy(dtype=bool)
    bet_arr  = _get_col_1d(yr_df, "_fukusho_bet_amount")[mask_arr].astype(float)
    pay_arr  = _get_col_1d(yr_df, "_corrected_pay")[mask_arr].astype(float)
    w_arr    = _get_col_1d(yr_df, "_year_weight")[mask_arr].astype(float)

    wbet = float((bet_arr * w_arr).sum())
    wpay = float((pay_arr * w_arr).sum())
    if wbet <= 0:
        return None
    return round(wpay / wbet * 100.0, 2)


# --------------------------------------------------------------------------
# Filter 1: OOT Stability (SegmentCache ベース)
# --------------------------------------------------------------------------
def evaluate_oot_cache(
    seg_cache: SegmentCache,
    seg_df: pd.DataFrame,
    factors: List[str],
    combo_clb: float,
) -> Dict:
    """
    Filter 1: OOT安定性評価。
    SegmentCache の evaluate_combo を OOT サブセットに適用。
    """
    # OOT行だけの SegmentCache を作成
    oot_df = seg_df[seg_df["yy_int"] >= OOT_YY_MIN].copy()

    if len(oot_df) < OOT_BIN_MIN_N * OOT_MIN_BINS:
        return {
            "oot_clb": None, "oot_n_bins": 0, "oot_n_bets": len(oot_df),
            "oot_roi_2023": None, "oot_roi_2024": None, "oot_roi_2025": None,
            "oot_min_yearly_roi": None,
            "f1_pass": False, "f1_reason": "insufficient_oot",
        }

    oot_cache = SegmentCache(oot_df, factors)
    oot_result = oot_cache.evaluate_combo(factors, bin_min_n=OOT_BIN_MIN_N, min_bins=OOT_MIN_BINS)

    if oot_result is None:
        return {
            "oot_clb": None, "oot_n_bins": 0, "oot_n_bets": len(oot_df),
            "oot_roi_2023": None, "oot_roi_2024": None, "oot_roi_2025": None,
            "oot_min_yearly_roi": None,
            "f1_pass": False, "f1_reason": "insufficient_oot_bins",
        }

    oot_clb    = oot_result["clb"]
    oot_n_bins = oot_result["n_valid_bins"]

    # 年別ROI
    yr_rois = {}
    for yy in [23, 24, 25]:
        r = _calc_yearly_roi_cache(None, oot_df, factors, yy)
        if r is not None:
            yr_rois[yy] = r

    min_yr_roi = min(yr_rois.values()) if yr_rois else None
    clb_ok  = oot_clb >= OOT_CLB_THRESH
    yr_ok   = (min_yr_roi is None) or (min_yr_roi >= OOT_MIN_YR_ROI)
    f1_pass = clb_ok and yr_ok

    reason = "pass" if f1_pass else (
        "oot_clb_low" if not clb_ok else "yearly_roi_low"
    )

    return {
        "oot_clb":          round(oot_clb, 2),
        "oot_n_bins":       int(oot_n_bins),
        "oot_n_bets":       int(len(oot_df)),
        "oot_roi_2023":     yr_rois.get(23),
        "oot_roi_2024":     yr_rois.get(24),
        "oot_roi_2025":     yr_rois.get(25),
        "oot_min_yearly_roi": round(min_yr_roi, 2) if min_yr_roi is not None else None,
        "f1_pass":          f1_pass,
        "f1_reason":        reason,
    }


# --------------------------------------------------------------------------
# Filter 2: Shirushi Contrarian (SegmentCache ベース)
# --------------------------------------------------------------------------
def _has_shirushi(factors: List[str]) -> bool:
    return any(f.startswith(SHIRUSHI_PREFIX) for f in factors)


def evaluate_shirushi_cache(
    seg_cache: SegmentCache,
    seg_df: pd.DataFrame,
    factors: List[str],
) -> Dict:
    """Filter 2: 印逆張りグリッドサーチ（SegmentCache使用）。"""
    if not _has_shirushi(factors):
        return {
            "has_shirushi": False,
            "best_shirushi_clb": None, "optimal_odds_t": None, "optimal_rank_t": None,
            "f2_pass": True, "f2_reason": "no_shirushi_auto_pass",
        }

    has_odds_col = "tansho_odds_numeric" in seg_df.columns
    has_rank_col = "kijun_ninkijun_tansho" in seg_df.columns

    best_clb    = -999.0
    best_odds_t = None
    best_rank_t = None

    for odds_t in ODDS_THRESHOLDS:
        for rank_t in RANK_THRESHOLDS:
            mask = pd.Series(False, index=seg_df.index)
            if has_odds_col:
                mask = mask | (pd.to_numeric(seg_df["tansho_odds_numeric"], errors="coerce") >= odds_t)
            if has_rank_col:
                mask = mask | (pd.to_numeric(seg_df["kijun_ninkijun_tansho"], errors="coerce") >= rank_t)

            filtered = seg_df[mask]
            if len(filtered) < OOT_BIN_MIN_N * 2:
                continue

            # SegmentCacheをgridフィルタ後のDFで都度構築
            fc = SegmentCache(filtered, factors)
            result = fc.evaluate_combo(factors, bin_min_n=30, min_bins=2)
            if result is not None:
                clb = result["clb"]
                if clb > best_clb:
                    best_clb    = clb
                    best_odds_t = odds_t
                    best_rank_t = rank_t

    f2_pass = (best_clb >= SHIRUSHI_CLB) if best_clb > -999 else False
    reason  = "pass" if f2_pass else (
        "no_valid_grid" if best_clb <= -999 else "shirushi_clb_low"
    )

    return {
        "has_shirushi":      True,
        "best_shirushi_clb": round(best_clb, 2) if best_clb > -999 else None,
        "optimal_odds_t":    best_odds_t,
        "optimal_rank_t":    best_rank_t,
        "f2_pass":           f2_pass,
        "f2_reason":         reason,
    }


# --------------------------------------------------------------------------
# Filter 3: Cross-gain (14 subsets: C(4,1)+C(4,2)+C(4,3))
# --------------------------------------------------------------------------
def evaluate_cross_gain_4combo(
    seg_cache: SegmentCache,
    factors: List[str],
    combo_clb: float,
) -> Dict:
    """
    Filter 3: 4-COMBOのクロスゲイン検証。
    サブセット最大14パターン:
      C(4,1) = 4  (単独)
      C(4,2) = 6  (ペア)
      C(4,3) = 4  (3-COMBO)
    cross_gain = combo4_clb - max(全サブセットCLB) >= CROSS_GAIN_MIN

    サブセット全データ不足(Noneのみ)の場合は cross_gain=None → 通過扱い。
    """
    subset_clbs: Dict[str, Optional[float]] = {}

    # C(4,1): 単独4個
    for r in range(1, 4):
        for subset in _combinations(factors, r):
            key = "+".join(subset)
            result = seg_cache.evaluate_combo(
                list(subset), bin_min_n=SUBSET_MIN_N, min_bins=2
            )
            subset_clbs[key] = result["clb"] if result is not None else None

    valid_clbs = [v for v in subset_clbs.values() if v is not None]

    if not valid_clbs:
        return {
            "n_subsets_evaluated": len(subset_clbs),
            "max_subset_clb":      None,
            "cross_gain":          None,
            "f3_pass":             True,
            "f3_reason":           "no_subset_data_auto_pass",
        }

    max_subset = max(valid_clbs)
    cross_gain = round(combo_clb - max_subset, 2)
    f3_pass    = cross_gain >= CROSS_GAIN_MIN

    return {
        "n_subsets_evaluated": len(subset_clbs),
        "max_subset_clb":      round(max_subset, 2),
        "cross_gain":          cross_gain,
        "f3_pass":             f3_pass,
        "f3_reason":           "pass" if f3_pass else "no_cross_gain",
    }


# --------------------------------------------------------------------------
# Main filtering loop
# --------------------------------------------------------------------------
def run_filtering(limit: int = 0) -> None:
    t0 = time.time()

    # ── 入力ロード ──────────────────────────────────────────────────────────
    if not INPUT_CSV.exists():
        print(f"[ERROR] {INPUT_CSV} が見つかりません。")
        sys.exit(1)

    combos_df = pd.read_csv(INPUT_CSV)
    print(f"[INFO] 4-COMBOスクリーニング結果: {len(combos_df)}件")

    if limit > 0:
        combos_df = combos_df.head(limit)
        print(f"[INFO] --limit {limit}: 先頭{limit}件のみ処理")

    # ── レースデータ読み込み ────────────────────────────────────────────────
    print("[INFO] レースデータ読み込み中...")
    df = load_and_prepare()
    df = prepare_corrected_cols(df)
    seg_map = build_seg_df_map(df)
    print(f"[INFO] セグメント数: {len(seg_map)} / データ準備完了 ({time.time()-t0:.1f}s)")

    # ── SegmentCache 構築（全セグメント）──────────────────────────────────
    used_segs   = combos_df["segment"].unique().tolist()
    seg_caches: Dict[str, Optional[SegmentCache]] = {}
    seg_dfs:    Dict[str, Optional[pd.DataFrame]] = {}

    print(f"[INFO] SegmentCache構築中 ({len(used_segs)}セグメント)...")
    t_cache = time.time()
    for seg in used_segs:
        seg_df = seg_map.get(seg)
        if seg_df is None or len(seg_df) < OOT_BIN_MIN_N:
            seg_caches[seg] = None
            seg_dfs[seg]    = None
            continue
        # そのセグメントで使う全ファクター
        seg_factors = list({
            f
            for _, row in combos_df[combos_df["segment"] == seg].iterrows()
            for f in str(row["factors"]).split("+")
        })
        seg_caches[seg] = SegmentCache(seg_df, seg_factors)
        seg_dfs[seg]    = seg_df
    print(f"[INFO] SegmentCache構築完了 ({time.time()-t_cache:.1f}s)")

    # ── 処理ループ ──────────────────────────────────────────────────────────
    results: List[Dict] = []
    n_total = len(combos_df)
    f1_cnt = f1f2_cnt = all_cnt = 0

    for i, row in combos_df.iterrows():
        seg      = str(row["segment"])
        factors  = str(row["factors"]).split("+")
        combo_clb = float(row["clb"])

        cache  = seg_caches.get(seg)
        seg_df = seg_dfs.get(seg)

        if cache is None or seg_df is None:
            results.append({
                "segment": seg, "factors": row["factors"],
                "base_3combo": row.get("base_3combo", ""),
                "combo_clb": combo_clb,
                "oot_clb": None, "oot_n_bins": 0, "oot_n_bets": 0,
                "oot_roi_2023": None, "oot_roi_2024": None, "oot_roi_2025": None,
                "oot_min_yearly_roi": None,
                "f1_pass": False, "f1_reason": "no_segment_data",
                "has_shirushi": _has_shirushi(factors),
                "best_shirushi_clb": None, "optimal_odds_t": None, "optimal_rank_t": None,
                "f2_pass": False, "f2_reason": "skipped",
                "n_subsets_evaluated": 0,
                "max_subset_clb": None, "cross_gain": None,
                "f3_pass": False, "f3_reason": "skipped",
                "all_pass": False,
            })
            continue

        # ── Filter 1: OOT ──────────────────────────────────────────────────
        f1 = evaluate_oot_cache(cache, seg_df, factors, combo_clb)

        if not f1["f1_pass"]:
            results.append({
                "segment": seg, "factors": row["factors"],
                "base_3combo": row.get("base_3combo", ""),
                "combo_clb": combo_clb,
                **f1,
                "has_shirushi": _has_shirushi(factors),
                "best_shirushi_clb": None, "optimal_odds_t": None, "optimal_rank_t": None,
                "f2_pass": False, "f2_reason": "skipped_f1_fail",
                "n_subsets_evaluated": 0,
                "max_subset_clb": None, "cross_gain": None,
                "f3_pass": False, "f3_reason": "skipped_f1_fail",
                "all_pass": False,
            })
            continue

        f1_cnt += 1

        # ── Filter 2: Shirushi ─────────────────────────────────────────────
        f2 = evaluate_shirushi_cache(cache, seg_df, factors)

        if not f2["f2_pass"]:
            results.append({
                "segment": seg, "factors": row["factors"],
                "base_3combo": row.get("base_3combo", ""),
                "combo_clb": combo_clb,
                **f1, **f2,
                "n_subsets_evaluated": 0,
                "max_subset_clb": None, "cross_gain": None,
                "f3_pass": False, "f3_reason": "skipped_f2_fail",
                "all_pass": False,
            })
            continue

        f1f2_cnt += 1

        # ── Filter 3: Cross-gain ───────────────────────────────────────────
        f3 = evaluate_cross_gain_4combo(cache, factors, combo_clb)

        all_pass = f3["f3_pass"]
        if all_pass:
            all_cnt += 1

        results.append({
            "segment":      seg,
            "factors":      row["factors"],
            "base_3combo":  row.get("base_3combo", ""),
            "combo_clb":    combo_clb,
            **f1, **f2,
            **f3,
            "all_pass":     all_pass,
        })

        # 進捗
        done = len(results)
        if done % 50 == 0:
            elapsed = time.time() - t0
            rate    = done / elapsed if elapsed > 0 else 0
            eta     = (n_total - done) / rate if rate > 0 else 0
            print(
                f"[{done:4d}/{n_total}] "
                f"F1:{f1_cnt} F1+2:{f1f2_cnt} 全通過:{all_cnt} | "
                f"{rate:.1f}件/s ETA:{eta/60:.1f}min"
            )

    # ── 保存 ───────────────────────────────────────────────────────────────
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    detail_df = pd.DataFrame(results)
    detail_df.to_csv(DETAIL_CSV, index=False, encoding="utf-8-sig")
    print(f"\n[SAVE] 詳細結果: {DETAIL_CSV} ({len(detail_df)}件)")

    filtered_df = detail_df[detail_df["all_pass"] == True].copy()
    if "combo_clb" in filtered_df.columns:
        filtered_df = filtered_df.sort_values("combo_clb", ascending=False)
    filtered_df.to_csv(FILTERED_CSV, index=False, encoding="utf-8-sig")
    print(f"[SAVE] 精鋭4-COMBO: {FILTERED_CSV} ({len(filtered_df)}件)")

    # ── サマリー ───────────────────────────────────────────────────────────
    elapsed = time.time() - t0
    print(f"\n{'='*60}")
    print(f"4-COMBOフィルタリング完了 ({elapsed/60:.1f}分)")
    print(f"{'='*60}")
    print(f"  入力:           {n_total:,}件")
    print(f"  Filter 1通過:   {f1_cnt:,}件  (OOT CLB>={OOT_CLB_THRESH}%)")
    print(f"  Filter 1+2通過: {f1f2_cnt:,}件  (+ 印逆張り CLB>={SHIRUSHI_CLB}%)")
    print(f"  全Filter通過:   {all_cnt:,}件  (+ クロスゲイン>={CROSS_GAIN_MIN}%)")
    print(f"{'='*60}")

    if len(filtered_df) > 0:
        print(f"\n【Top 10 精鋭4-COMBO (combo_CLB降順)】")
        top = filtered_df.head(10)
        for _, r in top.iterrows():
            cg = f"{r['cross_gain']:+.2f}" if pd.notna(r.get("cross_gain")) else "N/A"
            oot = f"{r['oot_clb']:.2f}" if pd.notna(r.get("oot_clb")) else "N/A"
            print(
                f"  [{r['segment']}] {r['factors']}\n"
                f"    combo_CLB={r['combo_clb']:.2f}%  OOT_CLB={oot}%  cross_gain={cg}%"
            )

    # 失敗内訳
    f1_fail = detail_df[~detail_df["f1_pass"]]["f1_reason"].value_counts()
    if len(f1_fail) > 0:
        print(f"\n【Filter 1失敗内訳】")
        for r, c in f1_fail.items():
            print(f"  {r}: {c}件")

    f2_fail = detail_df[detail_df["f1_pass"] & ~detail_df["f2_pass"]]["f2_reason"].value_counts()
    if len(f2_fail) > 0:
        print(f"\n【Filter 2失敗内訳（F1通過後）】")
        for r, c in f2_fail.items():
            print(f"  {r}: {c}件")

    f3_fail = detail_df[detail_df["f1_pass"] & detail_df["f2_pass"] & ~detail_df["f3_pass"]]["f3_reason"].value_counts()
    if len(f3_fail) > 0:
        print(f"\n【Filter 3失敗内訳（F1+2通過後）】")
        for r, c in f3_fail.items():
            print(f"  {r}: {c}件")


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="4-COMBOフィルタリング")
    parser.add_argument("--limit", type=int, default=0, help="テスト用: 先頭N件のみ")
    args = parser.parse_args()
    run_filtering(limit=args.limit)

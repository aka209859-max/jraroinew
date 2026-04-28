#!/usr/bin/env python3
"""
factor_3combo_filtering.py
===========================
3-COMBOスクリーニング結果（1,821件）に対して3段階の過酷フィルターを適用し、
"真の精鋭" 3-COMBOを抽出する。

【フィルター設計】
  Filter 1: OOT安定性（2023-2025）
    - OOT期間 (yy_int >= 23) のみで再評価
    - OOT_BIN_MIN_N=30 per bin, OOT_MIN_BINS=2
    - OOT_CLB >= 75.0%
    - 年別最低ROI (2023/2024/2025それぞれ) >= 60.0%
    ※ OOTデータ不足でビン構成不可能な場合: "insufficient_oot" = 失格

  Filter 2: 印コード逆張りグリッドサーチ
    - shirushi_code_* を含む場合のみ適用（含まない場合は自動通過）
    - Grid: tansho_odds_numeric >= [5.0, 8.0, 10.0, 15.0] OR
            kijun_ninkijun_tansho >= [3, 5, 7]
    - 最大CLB >= 78.0% で通過
    ※ shirushi_code非含有3-COMBOは自動通過

  Filter 3: クロスゲイン（3-combo独自性検証）
    - 単独ファクターCLB と ペアCLB を新式で再計算
      （旧採用CSVの値ではなく、kijun_odds_fukusho公式で再計算）
    - cross_gain = combo_clb - max(全サブセットCLB) >= 0.0%
    ※ サブセットのデータ不足（SUBSET_MIN_N=100未満）は cross_gain = None → 通過扱い

【出力】
  reports/screening/3combo_filtered.csv   (全フィルター通過分)
  reports/screening/3combo_filter_detail.csv (全1,821件 + 各フィルター結果)

Usage:
  py -3.12 -m backend.batch.factor_3combo_filtering
  py -3.12 -m backend.batch.factor_3combo_filtering --limit 100  # 先頭100件のみテスト
"""

import argparse
import math
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# 共通インフラを再利用
from backend.batch.factor_investment_screening import (
    load_and_prepare,
    build_seg_df_map,
    prepare_corrected_cols,
    TARGET_PAYOUT,
    ODDS_THRESHOLDS,
    RANK_THRESHOLDS,
)
from backend.batch.factor_3combo_screening import (
    _get_col_1d,
    BIN_MIN_N as COMBO_BIN_MIN_N,
)

# --------------------------------------------------------------------------
# 設定定数
# --------------------------------------------------------------------------
OUTPUT_DIR   = Path("reports/screening")
RESULT_CSV   = OUTPUT_DIR / "3combo_results.csv"
FILTERED_CSV = OUTPUT_DIR / "3combo_filtered.csv"
DETAIL_CSV   = OUTPUT_DIR / "3combo_filter_detail.csv"

# ── Filter 1: OOT ──────────────────────────────────────────────────────────
OOT_YY_MIN       = 23      # yy_int >= 23 (2023-2025)
OOT_BIN_MIN_N    = 30      # OOT有効ビン最小サンプル数
OOT_MIN_BINS     = 2       # OOT有効ビン最小数
OOT_CLB_THRESH   = 75.0    # OOT CLB閾値 (%)
OOT_MIN_YR_ROI   = 60.0    # 年別最低ROI閾値 (%)

# ── Filter 2: Shirushi ──────────────────────────────────────────────────────
SHIRUSHI_PREFIX  = "shirushi_code"
SHIRUSHI_CLB     = 78.0    # 印逆張り CLB閾値 (%)
# ODDS_THRESHOLDS / RANK_THRESHOLDS は factor_investment_screening から import

# ── Filter 3: Cross-gain ──────────────────────────────────────────────────
CROSS_GAIN_MIN   = 0.0     # cross_gain 最低値 (%) — >= 0 を要求
SUBSET_MIN_N     = 100     # サブセット評価最小ベット数


# --------------------------------------------------------------------------
# Numpy-based CLB calculation (same formula as 3combo_screening)
# --------------------------------------------------------------------------
def _np_clb(
    seg_df: pd.DataFrame,
    factors: List[str],
    bin_min_n: int = COMBO_BIN_MIN_N,
    min_bins: int = 3,
) -> Optional[Tuple[float, int]]:
    """
    指定ファクターリストでビン別補正ROI CLBと有効ビン数を計算する。
    factor_3combo_screening の evaluate_3combo と同じnumpy実装。

    Returns: (CLB: float, K: int) or None if insufficient data
    """
    # 全列の存在確認
    for col in factors:
        if col not in seg_df.columns:
            return None

    # valid mask
    valid_mask = seg_df[factors[0]].notna()
    for f in factors[1:]:
        valid_mask = valid_mask & seg_df[f].notna()
    if isinstance(valid_mask, pd.DataFrame):
        valid_mask = valid_mask.iloc[:, 0]

    if int(valid_mask.sum()) < bin_min_n * min_bins:
        return None

    mask_arr = valid_mask.to_numpy(dtype=bool)

    # Extract arrays
    f_arrs = [_get_col_1d(seg_df, f)[mask_arr].astype(str) for f in factors]
    bet_arr = _get_col_1d(seg_df, "_fukusho_bet_amount")[mask_arr].astype(float)
    pay_arr = _get_col_1d(seg_df, "_corrected_pay")[mask_arr].astype(float)
    w_arr   = _get_col_1d(seg_df, "_year_weight")[mask_arr].astype(float)

    # Group key
    key_arr = f_arrs[0]
    for fa in f_arrs[1:]:
        key_arr = key_arr + "\x01" + fa

    _, inverse = np.unique(key_arr, return_inverse=True)

    bin_rois: List[float] = []
    for gi in range(int(inverse.max()) + 1):
        grp_mask = (inverse == gi)
        n = int(grp_mask.sum())
        if n < bin_min_n:
            continue
        w    = w_arr[grp_mask]
        wbet = float((bet_arr[grp_mask] * w).sum())
        wpay = float((pay_arr[grp_mask] * w).sum())
        if wbet <= 0:
            continue
        bin_rois.append(wpay / wbet * 100.0)

    K = len(bin_rois)
    if K < min_bins:
        return None

    arr  = np.array(bin_rois, dtype=float)
    mean = float(arr.mean())
    std  = float(arr.std(ddof=1)) if K > 1 else 0.0
    clb  = mean - 1.96 * std / math.sqrt(K)
    return (clb, K)


# --------------------------------------------------------------------------
# Filter 1: OOT Stability
# --------------------------------------------------------------------------
def _calc_yearly_roi_np(
    oot_df: pd.DataFrame,
    factors: List[str],
    yy: int,
) -> Optional[float]:
    """
    指定年 (yy_int == yy) の単純プール補正ROIを返す。
    ビンなし（全OOTデータプール）—年別ドローダウン確認用。
    """
    yr_df = oot_df[oot_df["yy_int"] == yy]
    if len(yr_df) == 0:
        return None

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


def evaluate_oot(
    seg_df: pd.DataFrame,
    factors: List[str],
) -> Dict:
    """
    Filter 1: OOT安定性評価。

    Returns dict with:
      oot_clb, oot_n_bins, oot_n_bets,
      oot_roi_2023, oot_roi_2024, oot_roi_2025, oot_min_yearly_roi,
      f1_pass, f1_reason
    """
    oot_df = seg_df[seg_df["yy_int"] >= OOT_YY_MIN].copy()

    if len(oot_df) < OOT_BIN_MIN_N * OOT_MIN_BINS:
        return {
            "oot_clb": None, "oot_n_bins": 0, "oot_n_bets": 0,
            "oot_roi_2023": None, "oot_roi_2024": None, "oot_roi_2025": None,
            "oot_min_yearly_roi": None,
            "f1_pass": False, "f1_reason": "insufficient_oot",
        }

    # OOT CLB
    oot_result = _np_clb(oot_df, factors, bin_min_n=OOT_BIN_MIN_N, min_bins=OOT_MIN_BINS)

    if oot_result is None:
        return {
            "oot_clb": None, "oot_n_bins": 0, "oot_n_bets": 0,
            "oot_roi_2023": None, "oot_roi_2024": None, "oot_roi_2025": None,
            "oot_min_yearly_roi": None,
            "f1_pass": False, "f1_reason": "insufficient_oot_bins",
        }

    oot_clb, oot_n_bins = oot_result  # CLBと有効ビン数をアンパック

    # 年別ROI
    yr_rois = {}
    for yy in [23, 24, 25]:
        r = _calc_yearly_roi_np(oot_df, factors, yy)
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
        "oot_n_bins":       oot_n_bins,   # 修正: 実際の有効ビン数を格納
        "oot_n_bets":       int(len(oot_df)),
        "oot_roi_2023":     yr_rois.get(23),
        "oot_roi_2024":     yr_rois.get(24),
        "oot_roi_2025":     yr_rois.get(25),
        "oot_min_yearly_roi": round(min_yr_roi, 2) if min_yr_roi is not None else None,
        "f1_pass":          f1_pass,
        "f1_reason":        reason,
    }


# --------------------------------------------------------------------------
# Filter 2: Shirushi Contrarian Grid Search
# --------------------------------------------------------------------------
def _has_shirushi(factors: List[str]) -> bool:
    return any(f.startswith(SHIRUSHI_PREFIX) for f in factors)


def evaluate_shirushi(
    seg_df: pd.DataFrame,
    factors: List[str],
) -> Dict:
    """
    Filter 2: 印コード逆張りグリッドサーチ。
    shirushi_code_* を含まない場合は自動通過。

    Returns dict with:
      has_shirushi, best_shirushi_clb, optimal_odds_t, optimal_rank_t, f2_pass, f2_reason
    """
    if not _has_shirushi(factors):
        return {
            "has_shirushi": False,
            "best_shirushi_clb": None,
            "optimal_odds_t": None,
            "optimal_rank_t": None,
            "f2_pass": True,
            "f2_reason": "no_shirushi_auto_pass",
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
                odds_num = pd.to_numeric(seg_df["tansho_odds_numeric"], errors="coerce")
                mask = mask | (odds_num >= odds_t)
            if has_rank_col:
                rank_num = pd.to_numeric(seg_df["kijun_ninkijun_tansho"], errors="coerce")
                mask = mask | (rank_num >= rank_t)

            filtered = seg_df[mask]
            if len(filtered) < OOT_BIN_MIN_N * 2:
                continue

            clb_result = _np_clb(filtered, factors, bin_min_n=30, min_bins=2)
            if clb_result is not None:
                clb, _ = clb_result
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
# Filter 3: Cross-gain
# --------------------------------------------------------------------------
def _clb_or_none(seg_df: pd.DataFrame, factors: List[str], min_n: int = SUBSET_MIN_N) -> Optional[float]:
    """
    サブセット(単独 or ペア)のCLBをnumpy公式で再計算。
    min_n未満のビンは除外し、有効ビンが2以上なければNone。
    """
    # 単独ファクターの場合: min_bins=2 は緩めずに適用（= CLBが安定でないと0とみなさない）
    # CLBのみ返す（ビン数は不要）
    result = _np_clb(seg_df, factors, bin_min_n=min_n, min_bins=2)
    if result is None:
        return None
    clb, _ = result
    return clb


def evaluate_cross_gain(
    seg_df: pd.DataFrame,
    factors: List[str],
    combo_clb: float,
) -> Dict:
    """
    Filter 3: クロスゲイン検証。
    combo_clb - max(全サブセットCLB) >= CROSS_GAIN_MIN で通過。

    サブセット: 単独3個 + ペア3個 = 最大6パターン。
    サブセットCLBがすべてNone（データ不足）の場合は cross_gain=None → 通過扱い。

    Returns dict with:
      subset_clbs, max_subset_clb, cross_gain, f3_pass, f3_reason
    """
    from itertools import combinations as _combinations

    n = len(factors)
    subset_clbs: Dict[str, Optional[float]] = {}

    # 単独サブセット
    for f in factors:
        clb = _clb_or_none(seg_df, [f])
        subset_clbs[f] = clb

    # ペアサブセット（3因子の場合のみ）
    if n >= 3:
        for pair in _combinations(factors, 2):
            key = "+".join(pair)
            clb = _clb_or_none(seg_df, list(pair))
            subset_clbs[key] = clb

    valid_clbs = [v for v in subset_clbs.values() if v is not None]

    if not valid_clbs:
        # サブセット全データ不足 → cross_gain計算不能 → 通過扱い
        return {
            "subset_clbs":    subset_clbs,
            "max_subset_clb": None,
            "cross_gain":     None,
            "f3_pass":        True,
            "f3_reason":      "no_subset_data_auto_pass",
        }

    max_subset = max(valid_clbs)
    cross_gain = round(combo_clb - max_subset, 2)
    f3_pass    = cross_gain >= CROSS_GAIN_MIN

    return {
        "subset_clbs":    subset_clbs,
        "max_subset_clb": round(max_subset, 2),
        "cross_gain":     cross_gain,
        "f3_pass":        f3_pass,
        "f3_reason":      "pass" if f3_pass else "no_cross_gain",
    }


# --------------------------------------------------------------------------
# Main filtering loop
# --------------------------------------------------------------------------
def run_filtering(limit: int = 0) -> None:
    t0 = time.time()

    # ── Load screening results ──────────────────────────────────────────────
    if not RESULT_CSV.exists():
        print(f"[ERROR] {RESULT_CSV} が見つかりません。先に factor_3combo_screening.py を実行してください。")
        sys.exit(1)

    combos_df = pd.read_csv(RESULT_CSV)
    print(f"[INFO] 3-COMBOスクリーニング結果: {len(combos_df)}件")

    if limit > 0:
        combos_df = combos_df.head(limit)
        print(f"[INFO] --limit {limit}: 先頭{limit}件のみ処理")

    # ── Load and prepare race data ──────────────────────────────────────────
    print("[INFO] レースデータ読み込み中...")
    df = load_and_prepare()
    df = prepare_corrected_cols(df)
    seg_map = build_seg_df_map(df)
    print(f"[INFO] セグメント数: {len(seg_map)}")
    print(f"[INFO] データ準備完了 ({time.time()-t0:.1f}s)")

    # ── Processing ─────────────────────────────────────────────────────────
    results: List[Dict] = []
    n_total = len(combos_df)

    f1_pass_cnt = 0
    f1f2_pass_cnt = 0
    all_pass_cnt = 0

    for idx, row in combos_df.iterrows():
        seg      = str(row["segment"])
        factors  = str(row["factors"]).split("+")
        combo_clb = float(row["clb"])

        seg_df = seg_map.get(seg)
        if seg_df is None:
            result = {
                "segment": seg, "factors": row["factors"], "combo_clb": combo_clb,
                "f1_pass": False, "f1_reason": "no_segment_data",
                "f2_pass": False, "f2_reason": "skipped",
                "f3_pass": False, "f3_reason": "skipped",
                "all_pass": False,
            }
            results.append(result)
            continue

        # ── Filter 1: OOT ──────────────────────────────────────────────────
        f1 = evaluate_oot(seg_df, factors)

        if not f1["f1_pass"]:
            result = {
                "segment": seg, "factors": row["factors"],
                "combo_clb": combo_clb,
                **f1,
                "has_shirushi": _has_shirushi(factors),
                "best_shirushi_clb": None, "optimal_odds_t": None, "optimal_rank_t": None,
                "f2_pass": False, "f2_reason": "skipped_f1_fail",
                "max_subset_clb": None, "cross_gain": None,
                "f3_pass": False, "f3_reason": "skipped_f1_fail",
                "all_pass": False,
            }
            results.append(result)
            continue

        f1_pass_cnt += 1

        # ── Filter 2: Shirushi ─────────────────────────────────────────────
        f2 = evaluate_shirushi(seg_df, factors)

        if not f2["f2_pass"]:
            result = {
                "segment": seg, "factors": row["factors"],
                "combo_clb": combo_clb,
                **f1, **f2,
                "max_subset_clb": None, "cross_gain": None,
                "f3_pass": False, "f3_reason": "skipped_f2_fail",
                "all_pass": False,
            }
            results.append(result)
            continue

        f1f2_pass_cnt += 1

        # ── Filter 3: Cross-gain ───────────────────────────────────────────
        f3 = evaluate_cross_gain(seg_df, factors, combo_clb)

        all_pass = f3["f3_pass"]
        if all_pass:
            all_pass_cnt += 1

        result = {
            "segment":   seg,
            "factors":   row["factors"],
            "combo_clb": combo_clb,
            **f1,
            **f2,
            "max_subset_clb": f3["max_subset_clb"],
            "cross_gain":     f3["cross_gain"],
            "f3_pass":        f3["f3_pass"],
            "f3_reason":      f3["f3_reason"],
            "all_pass":       all_pass,
        }
        results.append(result)

        # Progress
        done = idx + 1 if isinstance(idx, int) else len(results)
        if len(results) % 100 == 0:
            elapsed = time.time() - t0
            rate = len(results) / elapsed if elapsed > 0 else 0
            eta = (n_total - len(results)) / rate if rate > 0 else 0
            print(
                f"[{len(results):4d}/{n_total}] "
                f"F1通過:{f1_pass_cnt} F1+2通過:{f1f2_pass_cnt} 全通過:{all_pass_cnt} | "
                f"{rate:.1f}件/s ETA:{eta/60:.1f}min"
            )

    # ── Save results ────────────────────────────────────────────────────────
    detail_df = pd.DataFrame(results)
    # Drop subset_clbs column (dict — not CSV-friendly)
    if "subset_clbs" in detail_df.columns:
        detail_df = detail_df.drop(columns=["subset_clbs"])

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    detail_df.to_csv(DETAIL_CSV, index=False, encoding="utf-8-sig")
    print(f"\n[SAVE] 詳細結果: {DETAIL_CSV} ({len(detail_df)}件)")

    filtered_df = detail_df[detail_df["all_pass"] == True].copy()
    filtered_df.to_csv(FILTERED_CSV, index=False, encoding="utf-8-sig")
    print(f"[SAVE] 精鋭3-COMBO: {FILTERED_CSV} ({len(filtered_df)}件)")

    # ── Summary ─────────────────────────────────────────────────────────────
    elapsed = time.time() - t0
    print(f"\n{'='*60}")
    print(f"3-COMBOフィルタリング完了 ({elapsed/60:.1f}分)")
    print(f"{'='*60}")
    print(f"  入力:           {n_total:,}件")
    print(f"  Filter 1通過:   {f1_pass_cnt:,}件  (OOT CLB>={OOT_CLB_THRESH}%)")
    print(f"  Filter 1+2通過: {f1f2_pass_cnt:,}件  (+ 印逆張り CLB>={SHIRUSHI_CLB}%)")
    print(f"  全Filter通過:   {all_pass_cnt:,}件  (+ クロスゲイン>={CROSS_GAIN_MIN}%)")
    print(f"{'='*60}")

    if len(filtered_df) > 0:
        print(f"\n【Top 10 精鋭3-COMBO (cross_gain降順)】")
        top = filtered_df.sort_values("cross_gain", ascending=False, na_position="last").head(10)
        for _, r in top.iterrows():
            cg = f"{r['cross_gain']:+.2f}" if r["cross_gain"] is not None else "N/A"
            print(
                f"  [{r['segment']}] {r['factors']}\n"
                f"    combo_CLB={r['combo_clb']:.2f}% "
                f"OOT_CLB={r['oot_clb']:.2f}% "
                f"cross_gain={cg}%"
            )

    # Filter 1失敗内訳
    if len(detail_df) > 0:
        f1_reason_cnt = detail_df[~detail_df["f1_pass"]]["f1_reason"].value_counts()
        if len(f1_reason_cnt) > 0:
            print(f"\n【Filter 1失敗内訳】")
            for reason, cnt in f1_reason_cnt.items():
                print(f"  {reason}: {cnt}件")

        f2_reason_cnt = detail_df[detail_df["f1_pass"] & ~detail_df["f2_pass"]]["f2_reason"].value_counts()
        if len(f2_reason_cnt) > 0:
            print(f"\n【Filter 2失敗内訳（F1通過後）】")
            for reason, cnt in f2_reason_cnt.items():
                print(f"  {reason}: {cnt}件")


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="3-COMBOフィルタリング")
    parser.add_argument("--limit", type=int, default=0, help="テスト用: 先頭N件のみ処理")
    args = parser.parse_args()

    run_filtering(limit=args.limit)

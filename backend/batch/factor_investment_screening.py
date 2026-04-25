#!/usr/bin/env python3
"""
factor_investment_screening.py
================================
EV特化型精鋭ファクター抽出スクリプト。

既存の採用ファクター（1,390件）に対して4つのフィルターを適用し、
年間回収率100%超えを実現する投資モデルの基盤となる精鋭ファクターを抽出する。

【ROI計算方式: 補正回収率（CLAUDE.md規約準拠）】
  - 均等払戻方式（TARGET_PAYOUT=10,000円）:
      bet_amount = TARGET_PAYOUT / tansho_odds
  - 108段階複勝配当補正係数（backend/config/odds_correction.py）:
      corrected_payout = TARGET_PAYOUT * correction_coeff(odds) * is_hit
  - 期間重み付け（2016=1, ..., 2025=10）:
      year_weight = yy_int - 15（clip 1-10）
  - 補正回収率 = Sigma(corrected_payout * year_weight)
                 / Sigma(bet_amount * year_weight) * 100

【CLB計算: ビン別補正ROIの95%信頼区間下限】
  個票レベルではなくビン別ROI（K個）の統計量を使用:
    CLB = mean(bin_rois) - 1.96 * std(bin_rois) / sqrt(K)
  → ビン間の一貫性（安定性）を保守的に評価

【フィルター一覧】
  Filter 1: CLB（ビン別補正ROIの95%CI下限）>= F1_CLB_THRESHOLD%
  Filter 2: OOT安定性（2023-2025）補正ROI CLB >= F2_OOT_CLB% / 年別最低 >= F2_MIN_YEARLY_ROI%
  Filter 3: クロスゲイン >= F3_CROSS_GAIN%（単独は自動通過）
  Filter 4: 印コード逆張りグリッドサーチ CLB >= F4_CLB_THRESHOLD%（非印は自動通過）

Usage:
  py -3.12 -m backend.batch.factor_investment_screening [--limit N] [--no-save]
  py -3.12 -m backend.batch.factor_investment_screening --recompute  # 閾値のみ再適用

Output:
  reports/screening/investment_factors.csv
  reports/screening/investment_factors_elite.csv
"""

import argparse
import math
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# Reuse factor_screening infrastructure
from backend.batch.factor_screening import (
    load_data,
    load_prev_data,
    load_blood_data,
    compute_derived_factors,
    load_extra_tables_for_full_scan,
    _build_combo_col,
    DEFAULT_CEO_ROWS,
    ALL_FACTORS,
)

# 補正係数マスタ（108段階）
from backend.config.odds_correction import FUKUSHO_CORRECTION

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------
OUTPUT_DIR = Path(__file__).parent.parent.parent / "reports" / "screening"
OUTPUT_CSV = OUTPUT_DIR / "investment_factors.csv"

# --------------------------------------------------------------------------
# 補正回収率パラメータ
# --------------------------------------------------------------------------
TARGET_PAYOUT: float = 10_000.0  # 均等払戻基準額（円）

# Filter thresholds（補正回収率ベース・ビン別CLB基準。初回実行後に校正予定）
# 補正回収率ベースライン ≒ 80%（JRA複勝控除率20%相当）
# ビン別CLBは個票CLBより安定的（binの一貫性を測定）
F1_CLB_THRESHOLD     = 80.0   # Filter1: ビン別補正ROI CLB下限 (%) 市場基準超え
F2_OOT_CLB           = 77.0   # Filter2: OOT 補正ROI CLB下限 (%)
F2_MIN_YEARLY_ROI    = 65.0   # Filter2: 年別最低補正ROI (%)
F2_MIN_OOT_BETS      = 100    # Filter2: OOT最小ベット数
F3_CROSS_GAIN        = 0.0    # Filter3: クロスゲイン最低値 (%) 正値のみ要求
F4_CLB_THRESHOLD     = 80.0   # Filter4: 印逆張り補正ROI CLB下限 (%)

# OOT year split
TRAIN_YEAR_MAX = 22   # yy_int: 2016-2022
OOT_YEAR_MIN   = 23  # yy_int: 2023-2025

# Filter4: Grid search parameters
# tansho_odds は整数×10で格納 (80 = 8.0倍, 50 = 5.0倍)
SHIRUSHI_COLS = {
    f"shirushi_code_{i}" for i in range(1, 8)
}
ODDS_THRESHOLDS  = [5.0, 8.0, 10.0, 15.0]   # 単勝オッズ閾値（倍）
RANK_THRESHOLDS  = [3, 5, 7]                  # 人気順位閾値

# Bin minimum samples
BIN_MIN_N = 100   # 有効ビンの最小サンプル数
OOT_BIN_MIN_N = 30  # OOT有効ビンの最小サンプル数（OOTはデータ少なめ）

# --------------------------------------------------------------------------
# Odds parsing helper
# --------------------------------------------------------------------------
def _parse_tansho_odds(df: pd.DataFrame) -> pd.DataFrame:
    """
    tansho_odds: 文字列、整数×10で格納 (e.g. "80" = 8.0倍, "150" = 15.0倍).
    tansho_odds_numeric: 実際の倍率（float）を生成。
    """
    if "tansho_odds" in df.columns:
        odds_int = pd.to_numeric(
            df["tansho_odds"].astype(str).str.strip(), errors="coerce"
        )
        df["tansho_odds_numeric"] = odds_int / 10.0
    else:
        df["tansho_odds_numeric"] = np.nan
    return df


# --------------------------------------------------------------------------
# 補正係数・補正列の一括計算（全DataFrame対象・高速ベクトル演算）
# --------------------------------------------------------------------------
def _vectorize_fukusho_correction(odds_series: pd.Series) -> pd.Series:
    """
    108段階複勝補正係数をベクトル演算で一括付与。
    各行のtansho_odds_numericに対応する補正係数を返す。
    境界条件: from_odds <= odds < to_odds
    """
    result = pd.Series(1.0, index=odds_series.index, dtype=float)
    for from_odds, to_odds, correction in FUKUSHO_CORRECTION:
        mask = (odds_series >= from_odds) & (odds_series < to_odds)
        result[mask] = correction
    return result


def prepare_corrected_cols(df: pd.DataFrame) -> pd.DataFrame:
    """
    補正回収率計算に必要な列を事前に一括生成（1回だけ呼び出す）。

    生成列:
      _fukusho_corr   : 108段階複勝補正係数
      _is_hit         : 複勝的中フラグ (1=的中, 0=外れ)
      _year_weight    : 期間重み (2016=1, ..., 2025=10)
      _bet_amount     : TARGET_PAYOUT / tansho_odds_numeric (均等払戻ベット額)
      _corrected_pay  : TARGET_PAYOUT * correction * is_hit (補正払戻額)
    """
    if "tansho_odds_numeric" not in df.columns:
        df = _parse_tansho_odds(df)

    # 108段階複勝補正係数（ベクトル演算）
    df["_fukusho_corr"] = _vectorize_fukusho_correction(df["tansho_odds_numeric"])

    # 複勝的中フラグ (haraimodoshi_fukusho > 0 で着内)
    df["_is_hit"] = (
        pd.to_numeric(df["haraimodoshi_fukusho"], errors="coerce")
        .fillna(0.0)
        .gt(0)
        .astype(float)
    )

    # 期間重み: yy_int(16-25) - 15 → 1-10
    if "year_weight" in df.columns:
        df["_year_weight"] = df["year_weight"].clip(lower=1, upper=10).astype(float)
    else:
        df["_year_weight"] = (df["yy_int"] - 15).clip(lower=1, upper=10).astype(float)

    # 均等払戻ベット額 (オッズ0/NaN は除外)
    safe_odds = df["tansho_odds_numeric"].replace(0.0, np.nan)
    df["_bet_amount"] = TARGET_PAYOUT / safe_odds

    # 補正払戻額（的中時のみ）
    df["_corrected_pay"] = TARGET_PAYOUT * df["_fukusho_corr"] * df["_is_hit"]

    print(
        f"[INFO] prepare_corrected_cols: correction range "
        f"[{df['_fukusho_corr'].min():.2f}, {df['_fukusho_corr'].max():.2f}], "
        f"hit_rate={df['_is_hit'].mean()*100:.1f}%"
    )
    return df


# --------------------------------------------------------------------------
# Segment DataFrame map
# --------------------------------------------------------------------------
def build_seg_df_map(df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """
    segment名 -> 絞り込み済みDataFrameの辞書を構築。
    factor_adoption.py の _build_seg_dfs と同様の構造。
    """
    segs: Dict[str, pd.DataFrame] = {
        "GLOBAL":    df,
        "COURSE_27": df,   # GLOBAL同様に全データ（コース複合キーは各ファクターで処理）
    }
    if "surface" in df.columns:
        for surf in ["芝", "ダ", "障"]:
            segs[f"SURFACE_2_{surf}"] = df[df["surface"] == surf]

    if "keibajo_code" in df.columns and "surface" in df.columns:
        for (kb, surf), sub in df.groupby(["keibajo_code", "surface"]):
            seg_name = f"KEIBAJO_SURFACE_{kb}_{surf}"
            segs[seg_name] = sub.reset_index(drop=True)

    return segs


# --------------------------------------------------------------------------
# Core: Get per-bin corrected ROI from valid bins
# --------------------------------------------------------------------------
def _bin_corrected_roi(grp: pd.DataFrame) -> Optional[float]:
    """
    ビン内の補正回収率を算出。
      corrected_roi = Sigma(corrected_pay * year_weight)
                      / Sigma(bet_amount * year_weight) * 100
    """
    w    = grp["_year_weight"]
    wbet = (grp["_bet_amount"] * w).sum()
    wpay = (grp["_corrected_pay"] * w).sum()
    if wbet <= 0 or np.isnan(wbet):
        return None
    return float(wpay / wbet * 100.0)


def get_valid_bin_rois(
    seg_df: pd.DataFrame,
    factors: List[str],
    min_n: int = BIN_MIN_N,
) -> Optional[Tuple[np.ndarray, int]]:
    """
    指定ファクター×セグメントで有効ビン（n >= min_n）を抽出し、
    各ビンの補正回収率リスト と 総ベット数 を返す。

    Returns: (bin_rois: np.ndarray, total_n: int) or None
    """
    missing = [f for f in factors if f not in seg_df.columns]
    if missing:
        return None

    # 補正列が存在しない場合（古いデータ等）は None
    if "_bet_amount" not in seg_df.columns:
        return None

    combo_col = _build_combo_col(seg_df, factors)
    valid_mask = combo_col.notna()
    if valid_mask.sum() < min_n:
        return None

    df2 = seg_df[valid_mask].copy()
    df2["_combo"] = combo_col[valid_mask].values

    bin_rois: List[float] = []
    total_n = 0
    for _, grp in df2.groupby("_combo", sort=True):
        if len(grp) >= min_n:
            roi = _bin_corrected_roi(grp)
            if roi is not None:
                bin_rois.append(roi)
                total_n += len(grp)

    if not bin_rois:
        return None

    arr = np.array(bin_rois, dtype=float)
    return (arr, total_n) if total_n >= min_n else None


# --------------------------------------------------------------------------
# Filter 1: Confidence Lower Bound（ビン別補正ROI版）
# --------------------------------------------------------------------------
def calc_confidence_lower_bound(bin_rois: np.ndarray) -> float:
    """
    ビン別補正ROI（K個）の95%信頼区間下限を計算。

    CLB = mean(bin_rois) - 1.96 * std(bin_rois) / sqrt(K)

    個票ではなくビン数 K を使うことで：
      - 個票間の自己相関/異分散の影響を低減
      - ビン間の一貫性（安定性）をより直接的に評価

    Returns: 保守的補正回収率下限 (%)
    """
    K = len(bin_rois)
    if K < 2:
        return float(bin_rois[0]) if K == 1 else -999.0
    mean_r = float(bin_rois.mean())
    std_r  = float(bin_rois.std(ddof=1))
    return mean_r - 1.96 * std_r / math.sqrt(K)


# --------------------------------------------------------------------------
# Filter 2: OOT Stability（補正ROI版）
# --------------------------------------------------------------------------
def _calc_pooled_corrected_roi(seg_df: pd.DataFrame, factors: List[str], min_n: int = 10) -> Optional[float]:
    """有効ビン全体プールの補正回収率（CLBではなく平均値）を返す。年別ROI用。"""
    result = get_valid_bin_rois(seg_df, factors, min_n=min_n)
    if result is None:
        return None
    bin_rois, _ = result
    return round(float(bin_rois.mean()), 2)


def evaluate_oot_stability(
    seg_df: pd.DataFrame,
    factors: List[str],
) -> Optional[Dict]:
    """
    OOT（Out-of-Time）安定性チェック（補正回収率ベース）。
    - 訓練期間: yy_int <= 22 (2016-2022)
    - 検証期間: yy_int >= 23 (2023-2025)

    Returns:
        dict with keys: oot_n_bets, oot_mean_roi, oot_conservative_roi,
                        yearly_roi (dict 23/24/25), min_yearly_roi, filter2_pass
        None if insufficient OOT data.
    """
    oot_df = seg_df[seg_df["yy_int"] >= OOT_YEAR_MIN]
    if len(oot_df) < F2_MIN_OOT_BETS:
        return None

    # OOT全体のビン別補正ROI → CLB
    oot_result = get_valid_bin_rois(oot_df, factors, min_n=OOT_BIN_MIN_N)
    if oot_result is None:
        return None
    oot_bin_rois, oot_total_n = oot_result
    if oot_total_n < F2_MIN_OOT_BETS:
        return None

    oot_clb  = calc_confidence_lower_bound(oot_bin_rois)
    oot_mean = float(oot_bin_rois.mean())

    # 年別補正ROI（ドローダウンチェック）
    yearly_roi: Dict[int, float] = {}
    for yr in [23, 24, 25]:
        yr_roi = _calc_pooled_corrected_roi(oot_df[oot_df["yy_int"] == yr], factors, min_n=10)
        if yr_roi is not None:
            yearly_roi[yr] = yr_roi

    min_yearly = min(yearly_roi.values()) if yearly_roi else None

    oot_pass = (
        oot_clb >= F2_OOT_CLB
        and (min_yearly is None or min_yearly >= F2_MIN_YEARLY_ROI)
    )

    return {
        "oot_n_bets":           oot_total_n,
        "oot_mean_roi":         round(oot_mean, 2),
        "oot_conservative_roi": round(oot_clb, 2),
        "oot_roi_2023":         yearly_roi.get(23),
        "oot_roi_2024":         yearly_roi.get(24),
        "oot_roi_2025":         yearly_roi.get(25),
        "oot_min_yearly_roi":   min_yearly,
        "filter2_pass":         oot_pass,
    }


# --------------------------------------------------------------------------
# Filter 3: Cross Gain（補正ROI版）
# --------------------------------------------------------------------------
def calc_simple_roi(
    seg_df: pd.DataFrame,
    factors: List[str],
    min_n: int = 30,
) -> Optional[float]:
    """
    ファクターの補正回収率（ビン平均）を返す（CLBではなく平均値）。
    クロスゲイン比較用。
    """
    return _calc_pooled_corrected_roi(seg_df, factors, min_n=min_n)


def calc_cross_gain(
    seg_df: pd.DataFrame,
    factors: List[str],
) -> Optional[float]:
    """
    クロスゲイン = ROI(A×B) - MAX(ROI(A), ROI(B))。
    単独ファクターには適用不可（Noneを返す）。

    Returns: cross_gain (%), or None if cannot be computed.
    """
    if len(factors) < 2:
        return None

    roi_combined = calc_simple_roi(seg_df, factors)
    if roi_combined is None:
        return None

    single_rois = []
    for f in factors:
        r = calc_simple_roi(seg_df, [f])
        if r is not None:
            single_rois.append(r)

    if not single_rois:
        return None

    max_single = max(single_rois)
    return round(roi_combined - max_single, 2)


# --------------------------------------------------------------------------
# Filter 4: Shirushi Contrarian (Grid Search)
# --------------------------------------------------------------------------
def _has_shirushi(factors: List[str]) -> bool:
    return any(f in SHIRUSHI_COLS for f in factors)


def find_optimal_shirushi_params(
    seg_df: pd.DataFrame,
    factors: List[str],
) -> Dict:
    """
    単勝オッズ閾値 × 人気順位閾値 のOR条件をグリッドサーチし、
    最大CLBを達成する最適パラメータを返す。

    Grid:
      ODDS_THRESHOLDS = [5.0, 8.0, 10.0, 15.0]  × 10 = raw整数比較
      RANK_THRESHOLDS = [3, 5, 7]                  (kijun_ninkijun_tansho)
    Condition (OR):
      tansho_odds_numeric >= odds_t  OR  kijun_ninkijun_tansho >= rank_t

    Returns dict with:
      best_clb, optimal_odds_threshold, optimal_rank_threshold,
      shirushi_market_gap_roi, filter4_pass
    """
    best_clb        = -999.0
    best_odds_t     = None
    best_rank_t     = None
    best_gap_roi    = None

    has_odds_col  = "tansho_odds_numeric" in seg_df.columns
    has_rank_col  = "kijun_ninkijun_tansho" in seg_df.columns

    if not has_odds_col and not has_rank_col:
        # 必要カラムなし → フィルター適用不可（失格扱い）
        return {
            "best_shirushi_clb":      None,
            "optimal_odds_threshold": None,
            "optimal_rank_threshold": None,
            "shirushi_market_gap_roi": None,
            "filter4_pass":            False,
        }

    for odds_t in ODDS_THRESHOLDS:
        for rank_t in RANK_THRESHOLDS:
            # 市場乖離マスク（OR条件）
            mask = pd.Series(False, index=seg_df.index)
            if has_odds_col:
                mask = mask | (seg_df["tansho_odds_numeric"] >= odds_t)
            if has_rank_col:
                rank_numeric = pd.to_numeric(
                    seg_df["kijun_ninkijun_tansho"], errors="coerce"
                )
                mask = mask | (rank_numeric >= rank_t)

            filtered_df = seg_df[mask]
            if len(filtered_df) < BIN_MIN_N:
                continue

            f4_result = get_valid_bin_rois(filtered_df, factors, min_n=30)
            if f4_result is None:
                continue
            f4_bin_rois, _ = f4_result

            clb = calc_confidence_lower_bound(f4_bin_rois)
            if clb > best_clb:
                best_clb     = clb
                best_odds_t  = odds_t
                best_rank_t  = rank_t
                best_gap_roi = round(float(f4_bin_rois.mean()), 2)

    passed = best_clb >= F4_CLB_THRESHOLD

    return {
        "best_shirushi_clb":      round(best_clb, 2) if best_clb > -999 else None,
        "optimal_odds_threshold": best_odds_t,
        "optimal_rank_threshold": best_rank_t,
        "shirushi_market_gap_roi": best_gap_roi,
        "filter4_pass":            passed,
    }


# --------------------------------------------------------------------------
# Main evaluation: one factor × segment
# --------------------------------------------------------------------------
def evaluate_factor(
    seg_df: pd.DataFrame,
    factors: List[str],
    segment: str,
    source_meta: Dict,
) -> Dict:
    """
    1件のファクター×セグメントに対して4フィルターを適用し、結果dictを返す。

    Parameters
    ----------
    seg_df      : セグメント絞り込み済みDataFrame
    factors     : ファクター列名リスト
    segment     : セグメント名
    source_meta : factor_adoption_result.csvからのメタデータ（type, grade等）
    """
    factors_str = "+".join(factors)
    is_cross    = len(factors) > 1
    has_sh      = _has_shirushi(factors)

    base = {
        "segment":     segment,
        "factors":     factors_str,
        "type":        source_meta.get("type", ""),
        "grade":       source_meta.get("grade", ""),
        "n_factors":   len(factors),
        "is_cross":    is_cross,
        "has_shirushi": has_sh,
        # adoption metadata
        "orig_avg_place_roi": source_meta.get("avg_place_roi"),
        "orig_total_samples": source_meta.get("total_samples"),
        "orig_pass_rate":     source_meta.get("pass_rate"),
    }

    # ── 有効ビン別補正ROI 取得 ─────────────────────────────────────────
    bin_result = get_valid_bin_rois(seg_df, factors, min_n=BIN_MIN_N)
    if bin_result is None:
        return {**base,
                "skip_reason": "no_valid_bins",
                "filter1_pass": False, "filter2_pass": False,
                "filter3_pass": False, "filter4_pass": False,
                "all_pass": False, "scaling_raw_score": None}

    bin_rois, n_valid_bets = bin_result
    n_valid_bins = len(bin_rois)
    mean_roi     = round(float(bin_rois.mean()), 2)   # ビン別補正ROI平均
    std_bin      = round(float(bin_rois.std(ddof=1)) if n_valid_bins > 1 else 0.0, 2)

    # ── Filter 1: ビン別補正ROI CLB ───────────────────────────────────
    clb = calc_confidence_lower_bound(bin_rois)
    clb_r = round(clb, 2)
    f1_pass = clb >= F1_CLB_THRESHOLD

    # ── Filter 2: OOT ──────────────────────────────────────────────────
    oot = evaluate_oot_stability(seg_df, factors)
    if oot is None:
        f2_result = {
            "oot_n_bets": 0, "oot_mean_roi": None, "oot_conservative_roi": None,
            "oot_roi_2023": None, "oot_roi_2024": None, "oot_roi_2025": None,
            "oot_min_yearly_roi": None, "filter2_pass": False,
        }
        f2_skip = "insufficient_oot_data"
    else:
        f2_result = oot
        f2_skip   = None

    # ── Filter 3: Cross Gain ────────────────────────────────────────────
    if is_cross:
        gain   = calc_cross_gain(seg_df, factors)
        f3_pass = (gain is not None) and (gain >= F3_CROSS_GAIN)
    else:
        gain   = None
        f3_pass = True  # 単独ファクターは自動通過

    # ── Filter 4: Shirushi Contrarian ──────────────────────────────────
    if has_sh:
        sh_result  = find_optimal_shirushi_params(seg_df, factors)
        f4_pass    = sh_result["filter4_pass"]
        shirushi_applied = True
    else:
        sh_result = {
            "best_shirushi_clb":       None,
            "optimal_odds_threshold":  None,
            "optimal_rank_threshold":  None,
            "shirushi_market_gap_roi": None,
            "filter4_pass":            True,
        }
        f4_pass           = True
        shirushi_applied  = False

    # ── All pass ────────────────────────────────────────────────────────
    all_pass = f1_pass and f2_result["filter2_pass"] and f3_pass and f4_pass

    # scaling_raw_score: CLB - ベースライン(80%) → TANHスケーリング用
    scaling_raw = round(clb - 80.0, 2) if f1_pass else None

    row = {
        **base,
        # F1（補正回収率ベース）
        "n_valid_bins":        n_valid_bins,
        "n_valid_bets":        n_valid_bets,
        "mean_corrected_roi":  mean_roi,
        "std_bin_roi":         std_bin,
        "conservative_roi_lb": clb_r,
        "filter1_pass":        f1_pass,
        # F2
        **{k: f2_result.get(k) for k in [
            "oot_n_bets", "oot_mean_roi", "oot_conservative_roi",
            "oot_roi_2023", "oot_roi_2024", "oot_roi_2025",
            "oot_min_yearly_roi",
        ]},
        "filter2_pass":        f2_result["filter2_pass"],
        "oot_skip_reason":     f2_skip,
        # F3
        "cross_gain":          gain,
        "filter3_pass":        f3_pass,
        # F4
        "shirushi_filter_applied":  shirushi_applied,
        "best_shirushi_clb":        sh_result["best_shirushi_clb"],
        "optimal_odds_threshold":   sh_result["optimal_odds_threshold"],
        "optimal_rank_threshold":   sh_result["optimal_rank_threshold"],
        "shirushi_market_gap_roi":  sh_result["shirushi_market_gap_roi"],
        "filter4_pass":             f4_pass,
        # Final
        "all_pass":            all_pass,
        "scaling_raw_score":   scaling_raw,
    }
    return row


# --------------------------------------------------------------------------
# Main screening loop
# --------------------------------------------------------------------------
def run_investment_screening(
    df: pd.DataFrame,
    adoption_df: pd.DataFrame,
    limit: Optional[int] = None,
) -> pd.DataFrame:
    """
    全採用ファクターに対して4フィルターを適用する。

    Parameters
    ----------
    df          : 全データ（derive済み）
    adoption_df : factor_adoption_result.csv (decision=='採用')
    limit       : デバッグ用：評価件数上限（None=全件）

    Returns: 全結果DataFrame（all_pass=True が精鋭）
    """
    # セグメントDF辞書を構築
    print("[INFO] Building segment DataFrames...")
    seg_map = build_seg_df_map(df)
    print(f"[INFO] Segments available: {len(seg_map)}")

    # 採用ファクターのみ
    candidates = adoption_df[adoption_df["decision"] == "採用"].copy()
    if limit:
        candidates = candidates.head(limit)
    total = len(candidates)
    print(f"[INFO] Candidates to evaluate: {total:,}")

    results = []
    t0 = time.time()

    for i, (_, row) in enumerate(candidates.iterrows(), 1):
        segment     = str(row["segment"])
        factors_str = str(row["factors"])
        factors     = factors_str.split("+")

        seg_df = seg_map.get(segment)
        if seg_df is None or len(seg_df) < BIN_MIN_N:
            results.append({
                "segment": segment, "factors": factors_str,
                "skip_reason": "segment_not_found", "all_pass": False,
            })
            continue

        source_meta = row.to_dict()
        result = evaluate_factor(seg_df, factors, segment, source_meta)
        results.append(result)

        # Progress log (every 50 or at end)
        if i % 50 == 0 or i == total:
            elapsed = time.time() - t0
            passed_so_far = sum(1 for r in results if r.get("all_pass"))
            eta = (elapsed / i) * (total - i)
            print(
                f"  [{i:4d}/{total}] passed={passed_so_far} "
                f"elapsed={elapsed/60:.1f}min ETA={eta/60:.1f}min"
            )

    return pd.DataFrame(results)


# --------------------------------------------------------------------------
# Data loading
# --------------------------------------------------------------------------
def _apply_odds_filter(df: pd.DataFrame) -> pd.DataFrame:
    """tansho_odds 10-1000 (1.0〜100.0倍) に絞る（CLAUDE.md 規約）。"""
    if "tansho_odds" in df.columns:
        odds_int = pd.to_numeric(
            df["tansho_odds"].astype(str).str.strip(), errors="coerce"
        )
        before = len(df)
        df = df[(odds_int >= 10) & (odds_int <= 1000)].copy()
        print(f"[INFO] Odds filter: {before:,} -> {len(df):,}")
    return df


def load_and_prepare(row_limit: int = 0) -> pd.DataFrame:
    """全データ読み込み・前処理（factor_adoption.py と同等）。"""
    print(f"[INFO] Loading main data (limit={row_limit or '無制限'})...")
    df = load_data(limit=row_limit)
    print(f"[INFO] Main rows: {len(df):,}")

    # year_weight
    df["year_weight"] = (df["yy_int"] - 15).clip(lower=1, upper=10)

    # ファクター前処理
    for col, _, ftype in ALL_FACTORS:
        if col not in df.columns:
            continue
        raw = df[col].astype(str).str.strip()
        if ftype == "numeric":
            df[col] = pd.to_numeric(raw.replace({"": None, "nan": None}), errors="coerce")
        else:
            df[col] = raw.replace({"": None, "nan": None, "None": None})

    # 前走・血統データ
    print("[INFO] Loading prev race data...")
    try:
        prev_df = load_prev_data()
        print(f"[INFO] Prev: {len(prev_df):,}")
    except Exception as e:
        print(f"[WARN] Prev failed: {e}")
        prev_df = None

    print("[INFO] Loading bloodline data...")
    try:
        blood_df = load_blood_data()
        print(f"[INFO] Blood: {len(blood_df):,}")
    except Exception as e:
        print(f"[WARN] Blood failed: {e}")
        blood_df = None

    print("[INFO] Computing derived factors...")
    df = compute_derived_factors(df, prev_df, blood_df)
    df = _apply_odds_filter(df)

    print("[INFO] Loading extra tables (jrd_joa, jrd_bac)...")
    try:
        df = load_extra_tables_for_full_scan(df)
        print(f"[INFO] After extra merge: {len(df):,} rows, {len(df.columns)} cols")
    except Exception as e:
        print(f"[WARN] Extra-table merge failed: {e}")

    # tansho_odds → 倍率（float）
    df = _parse_tansho_odds(df)
    print(f"[INFO] tansho_odds_numeric: range [{df['tansho_odds_numeric'].min():.1f}, {df['tansho_odds_numeric'].max():.1f}]")

    # 補正回収率計算用列を一括生成（108段階補正係数 + 期間重み + 均等払戻）
    print("[INFO] Preparing corrected ROI columns...")
    df = prepare_corrected_cols(df)

    return df


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------
def save_investment_factors(results_df: pd.DataFrame, path: Path) -> None:
    """精鋭ファクターをCSVに保存。"""
    path.parent.mkdir(parents=True, exist_ok=True)

    # 全結果（all_pass有無問わず保存、フィルター内訳も参照可能）
    try:
        results_df.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"[OK] {path}  ({len(results_df):,} rows)")
    except PermissionError:
        from datetime import datetime
        ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = path.with_stem(path.stem + f"_{ts}")
        results_df.to_csv(bak, index=False, encoding="utf-8-sig")
        print(f"[WARN] Permission denied → {bak}")

    # 精鋭のみ別ファイル
    elite = results_df[results_df["all_pass"] == True].copy()
    if not elite.empty:
        elite_path = path.with_name("investment_factors_elite.csv")
        elite.to_csv(elite_path, index=False, encoding="utf-8-sig")
        print(f"[OK] {elite_path}  ({len(elite):,} rows)")


def _reapply_thresholds(df: pd.DataFrame) -> pd.DataFrame:
    """既存の投資スクリーニングCSVに対して、現在の閾値定数を再適用する。
    DBロード不要で高速（閾値変更時の再評価用）。
    """
    # Filter 1
    df["filter1_pass"] = df["conservative_roi_lb"] >= F1_CLB_THRESHOLD

    # Filter 2: OOT安定性
    oot_valid = df["oot_skip_reason"].isna()
    oot_clb_ok = df["oot_conservative_roi"] >= F2_OOT_CLB
    oot_yearly_ok = df["oot_min_yearly_roi"].isna() | (df["oot_min_yearly_roi"] >= F2_MIN_YEARLY_ROI)
    oot_skip = df["oot_skip_reason"] == "insufficient_oot_data"
    df["filter2_pass"] = df["filter1_pass"] & (oot_valid & oot_clb_ok & oot_yearly_ok | oot_skip)

    # Filter 3: クロスゲイン
    is_single = ~df["is_cross"]
    cross_ok = df["cross_gain"] >= F3_CROSS_GAIN
    df["filter3_pass"] = df["filter2_pass"] & (is_single | cross_ok)

    # Filter 4: 印コード逆張り
    no_shirushi = ~df["has_shirushi"]
    shirushi_ok = df["best_shirushi_clb"] >= F4_CLB_THRESHOLD
    df["filter4_pass"] = df["filter3_pass"] & (no_shirushi | shirushi_ok)

    # all_pass & scaling_raw_score
    df["all_pass"] = df["filter4_pass"]
    df["scaling_raw_score"] = df["conservative_roi_lb"].where(df["all_pass"]).apply(
        lambda x: round(x - 80.0, 4) if pd.notna(x) else None
    )
    return df


def print_summary(results_df: pd.DataFrame) -> None:
    """実行結果のサマリーを出力。"""
    total = len(results_df)
    skip  = results_df["skip_reason"].notna().sum() if "skip_reason" in results_df else 0
    evaluated = total - skip

    f1 = results_df["filter1_pass"].sum() if "filter1_pass" in results_df else 0
    f2 = results_df["filter2_pass"].sum() if "filter2_pass" in results_df else 0
    f3 = results_df["filter3_pass"].sum() if "filter3_pass" in results_df else 0
    f4 = results_df["filter4_pass"].sum() if "filter4_pass" in results_df else 0
    final = results_df["all_pass"].sum() if "all_pass" in results_df else 0

    print("\n" + "="*60)
    print("  INVESTMENT FACTOR SCREENING -- SUMMARY")
    print("="*60)
    print(f"  候補ファクター:          {total:>6,} 件")
    print(f"  評価スキップ:            {skip:>6,} 件")
    print(f"  評価実施:                {evaluated:>6,} 件")
    print(f"  ------------------------------------------")
    print(f"  Filter1通過 CLB>={F1_CLB_THRESHOLD}%:  {f1:>6,} 件")
    print(f"  Filter2通過 OOT>={F2_OOT_CLB}%:  {f2:>6,} 件")
    print(f"  Filter3通過 CrossGain>={F3_CROSS_GAIN}%:{f3:>5,} 件 (単独は自動通過)")
    print(f"  Filter4通過 印逆張り>={F4_CLB_THRESHOLD}%:{f4:>5,} 件 (非印は自動通過)")
    print(f"  ------------------------------------------")
    print(f"  ★ 精鋭ファクター（全通過）: {final:>4,} 件")
    print("="*60)

    # TOP 3（CLB降順）
    elite = results_df[results_df["all_pass"] == True].copy()
    if not elite.empty and "conservative_roi_lb" in elite.columns:
        elite_sorted = elite.sort_values("conservative_roi_lb", ascending=False).head(3)
        print("\n  ★★ TOP3 ファクター（CLB降順）:")
        for rank, (_, r) in enumerate(elite_sorted.iterrows(), 1):
            mean_col = "mean_corrected_roi" if "mean_corrected_roi" in r.index else "mean_place_roi"
            print(
                f"  #{rank}: [{r['segment']}] {r['factors']}"
                f"  CLB={r['conservative_roi_lb']:.2f}%"
                f"  mean={r[mean_col]:.1f}%"
                f"  n={int(r['n_valid_bets']):,}"
            )
    print()

    # フィルター別内訳
    if not elite.empty:
        print("  【精鋭ファクター内訳】")
        cross_e = elite["is_cross"].sum() if "is_cross" in elite else 0
        sh_e    = elite["has_shirushi"].sum() if "has_shirushi" in elite else 0
        print(f"    単独ファクター: {final - cross_e} 件")
        print(f"    クロスファクター: {cross_e} 件")
        print(f"    印コード逆張り: {sh_e} 件")

        print("\n  【セグメント別採用数 TOP10】")
        seg_counts = elite["segment"].value_counts().head(10)
        for seg, cnt in seg_counts.items():
            print(f"    {seg:<35} {cnt:>3} 件")
    print("="*60)


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="EV特化型精鋭ファクター抽出スクリプト"
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="デバッグ用：評価するファクター件数上限"
    )
    parser.add_argument(
        "--rows", type=int, default=DEFAULT_CEO_ROWS,
        help="DBからロードする行数（0=全件）"
    )
    parser.add_argument(
        "--adoption-csv", type=str,
        default=str(Path(__file__).parent.parent.parent / "reports" / "screening" / "factor_adoption_result.csv"),
        help="採用判定CSVのパス"
    )
    parser.add_argument(
        "--output", type=str, default=str(OUTPUT_CSV),
        help="出力CSVのパス"
    )
    parser.add_argument(
        "--no-save", action="store_true",
        help="CSVを保存しない（テスト用）"
    )
    parser.add_argument(
        "--recompute", action="store_true",
        help="既存CSVから閾値のみ再適用して投資ファクターを再判定（DBロード不要・高速）"
    )
    args = parser.parse_args()

    t_start = time.time()

    # --recompute モード: 既存CSVから閾値再適用
    if args.recompute:
        csv_path = Path(args.output)
        if not csv_path.exists():
            print(f"[ERROR] --recompute requires existing CSV: {csv_path}")
            sys.exit(1)
        print(f"[INFO] --recompute: loading {csv_path}")
        results_df = pd.read_csv(csv_path)
        results_df = _reapply_thresholds(results_df)
        if not args.no_save:
            save_investment_factors(results_df, csv_path)
        print_summary(results_df)
        print(f"[DONE] recompute time: {(time.time()-t_start):.1f}s")
        return

    # 1. データ読み込み
    df = load_and_prepare(args.rows)

    # 2. 採用ファクター読み込み
    adoption_path = Path(args.adoption_csv)
    if not adoption_path.exists():
        print(f"[ERROR] {adoption_path} not found")
        sys.exit(1)
    adoption_df = pd.read_csv(adoption_path, encoding="utf-8-sig")
    print(f"[INFO] Adoption CSV: {len(adoption_df):,} rows")
    adopted = adoption_df[adoption_df["decision"] == "採用"]
    print(f"[INFO] 採用ファクター: {len(adopted):,} 件")

    # 3. スクリーニング実行
    print(f"\n[INFO] Starting investment screening...")
    results_df = run_investment_screening(df, adoption_df, limit=args.limit)

    # 4. 出力
    if not args.no_save:
        save_investment_factors(results_df, Path(args.output))

    # 5. サマリー表示
    print_summary(results_df)

    total_min = (time.time() - t_start) / 60
    print(f"[DONE] Total time: {total_min:.1f} min")


if __name__ == "__main__":
    main()

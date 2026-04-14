"""
補正回収率算出エンジン

均等払戻方式:
    全ての馬券を同じ払戻金額（10,000円）で買った場合の回収率を算出する。

計算式:
    補正回収率 = SUM(的中馬の corrected_payout * year_weight)
                / SUM(全該当馬の bet_amount * year_weight)

    bet_amount = TARGET_PAYOUT / odds
    corrected_payout = TARGET_PAYOUT * get_odds_correction(odds, is_fukusho)

基準点:
    score = corrected_return_rate - 80.0
    score > 0 → エッジが存在する可能性
    score < 0 → 市場平均以下
"""
import pandas as pd
import numpy as np

from backend.config.odds_correction import get_odds_correction
from backend.config.year_weights import get_year_weight

TARGET_PAYOUT: float = 10000.0
BASELINE_RATE: float = 80.0


def calc_corrected_return_rate(
    results: pd.DataFrame,
    odds_col: str = "tansho_odds",
    hit_flag_col: str = "is_hit",
    year_col: str = "race_year",
    is_fukusho: bool = False,
) -> dict:
    """
    補正回収率を算出する。

    Args:
        results: 対象データ。以下のカラムが必要:
            - odds_col: オッズ（float型に変換済み）
            - hit_flag_col: 的中フラグ（1=的中, 0=不的中）
            - year_col: 年度（str型 "2016"〜"2025"）
        odds_col: オッズカラム名
        hit_flag_col: 的中フラグカラム名
        year_col: 年度カラム名
        is_fukusho: True=複勝, False=単勝

    Returns:
        dict with keys:
            - corrected_return_rate: 補正回収率（%）
            - score: 補正回収率 - 80.0
            - total_weighted_bet: 加重合計ベット額
            - total_weighted_payout: 加重合計払戻額
            - n_samples: サンプル数
            - n_hits: 的中数
            - hit_rate: 的中率（%）
    """
    df = results.dropna(subset=[odds_col, hit_flag_col, year_col]).copy()

    if len(df) == 0:
        return {
            "corrected_return_rate": 0.0,
            "score": -BASELINE_RATE,
            "total_weighted_bet": 0.0,
            "total_weighted_payout": 0.0,
            "n_samples": 0,
            "n_hits": 0,
            "hit_rate": 0.0,
        }

    odds = df[odds_col].astype(float)
    is_hit = df[hit_flag_col].astype(int)
    years = df[year_col].astype(str)

    # 各行の重み・ベット額・補正払戻額を算出
    year_weights = years.map(lambda y: get_year_weight(y)).astype(float)
    corrections = odds.map(lambda o: get_odds_correction(o, is_fukusho)).astype(float)

    # bet_amount = TARGET_PAYOUT / odds (オッズ0以下はNaN→除外)
    bet_amounts = TARGET_PAYOUT / odds.replace(0, np.nan)

    # corrected_payout = TARGET_PAYOUT * correction (的中時のみ)
    corrected_payouts = TARGET_PAYOUT * corrections * is_hit

    # 加重合計
    total_weighted_bet = (bet_amounts * year_weights).sum()
    total_weighted_payout = (corrected_payouts * year_weights).sum()

    n_samples = len(df)
    n_hits = int(is_hit.sum())

    if total_weighted_bet == 0:
        corrected_return_rate = 0.0
    else:
        corrected_return_rate = (total_weighted_payout / total_weighted_bet) * 100.0

    return {
        "corrected_return_rate": round(corrected_return_rate, 4),
        "score": round(corrected_return_rate - BASELINE_RATE, 4),
        "total_weighted_bet": round(total_weighted_bet, 2),
        "total_weighted_payout": round(total_weighted_payout, 2),
        "n_samples": n_samples,
        "n_hits": n_hits,
        "hit_rate": round((n_hits / n_samples) * 100.0, 4) if n_samples > 0 else 0.0,
    }


def calc_return_rate_by_bins(
    results: pd.DataFrame,
    bin_col: str,
    odds_col: str = "tansho_odds",
    hit_flag_col: str = "is_hit",
    year_col: str = "race_year",
    is_fukusho: bool = False,
) -> pd.DataFrame:
    """
    ビン（カテゴリ）別に補正回収率を算出する。

    Args:
        results: 対象データ
        bin_col: ビン/カテゴリ列名
        odds_col: オッズカラム名
        hit_flag_col: 的中フラグカラム名
        year_col: 年度カラム名
        is_fukusho: True=複勝, False=単勝

    Returns:
        ビン別の補正回収率テーブル（DataFrame）
    """
    records = []
    for bin_val, group in results.groupby(bin_col, sort=True):
        result = calc_corrected_return_rate(
            group,
            odds_col=odds_col,
            hit_flag_col=hit_flag_col,
            year_col=year_col,
            is_fukusho=is_fukusho,
        )
        result["bin_value"] = bin_val
        records.append(result)

    if not records:
        return pd.DataFrame()

    df_result = pd.DataFrame(records)
    cols = ["bin_value"] + [c for c in df_result.columns if c != "bin_value"]
    return df_result[cols]

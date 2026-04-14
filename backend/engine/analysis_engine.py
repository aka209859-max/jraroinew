"""
分析エンジン - CrossFactor相当の回収率分析

任意のファクターを集計キーとしてクロス集計し、
ビンごとの的中率・回収率・補正回収率を算出する。
"""
from __future__ import annotations

import math
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from backend.engine.data_loader_v2 import load_base_race_data_v2
from backend.engine.prev_race_loader import load_global_prev_races, load_course27_prev_races
from backend.engine.derived_factors import derive_all_factors
from backend.engine.corrected_return import calc_corrected_return_rate

logger = logging.getLogger(__name__)

# =============================================================================
# AnalysisQuery
# =============================================================================

@dataclass
class AnalysisQuery:
    name: str
    segment: str                                     # "GLOBAL" / "SURFACE_2" / "COURSE_27"
    key1: str
    key2: Optional[str] = None
    key3: Optional[str] = None
    conditions: dict = field(default_factory=dict)
    odds_filter: dict = field(default_factory=lambda: {
        "tansho": [1.0, 100.0],
        "fukusho": [1.0, 17.0],
    })
    prev_race_type: str = "none"                     # "none" / "global" / "course27"
    data_period: list = field(default_factory=lambda: ["2016-01-01", "2025-12-31"])
    year_weights: dict = field(default_factory=lambda: {
        2016: 1, 2017: 2, 2018: 3, 2019: 4, 2020: 5,
        2021: 6, 2022: 7, 2023: 8, 2024: 9, 2025: 10,
    })
    min_samples: int = 30
    bin_config: dict = field(default_factory=dict)


# =============================================================================
# データ取得
# =============================================================================

_PREV_JOIN_KEYS = [
    "keibajo_code", "kaisai_nen", "kaisai_tsukihi",
    "kaisai_kai", "kaisai_nichime", "race_bango", "umaban",
]


def _date_to_yyyymmdd(date_str: str) -> str:
    return date_str.replace("-", "")


def _strip_cols(df: pd.DataFrame, cols: list) -> pd.DataFrame:
    for c in cols:
        if c in df.columns:
            df[c] = df[c].astype(str).str.strip()
    return df


def _merge_prev(df: pd.DataFrame, prev_df: pd.DataFrame) -> pd.DataFrame:
    """前走DataFrameの prev_* カラムをベースDataFrameにマージする。"""
    actual_keys = [k for k in _PREV_JOIN_KEYS if k in prev_df.columns and k in df.columns]
    # base df の join キーを正規化
    df = _strip_cols(df.copy(), actual_keys)
    prev_df = _strip_cols(prev_df.copy(), actual_keys)
    # 新規カラムのみ取得
    new_cols = [c for c in prev_df.columns if c not in df.columns]
    if not new_cols:
        return df
    merge_src = prev_df[actual_keys + new_cols].copy()
    return df.merge(merge_src, on=actual_keys, how="left")


def _load_data(conn, query: AnalysisQuery) -> pd.DataFrame:
    date_from = _date_to_yyyymmdd(query.data_period[0])
    date_to = _date_to_yyyymmdd(query.data_period[1])

    logger.info("load_base_race_data_v2: %s 〜 %s", date_from, date_to)
    df = load_base_race_data_v2(date_from, date_to)

    if query.prev_race_type == "global":
        logger.info("load_global_prev_races: マージ中")
        prev_df = load_global_prev_races(conn, date_from, date_to)
        df = _merge_prev(df, prev_df)

    elif query.prev_race_type == "course27":
        logger.info("load_course27_prev_races: マージ中")
        prev_df = load_course27_prev_races(conn, date_from, date_to)
        df = _merge_prev(df, prev_df)

    logger.info("derive_all_factors: 開始")
    df = derive_all_factors(df, conn)
    return df


# =============================================================================
# 基本フィルタ
# =============================================================================

def _apply_basic_filters(df: pd.DataFrame, conditions: dict) -> pd.DataFrame:
    orig_len = len(df)

    # ijo_kubun_code: '0' 以外を除外
    if "ijo_kubun_code" in df.columns:
        ijo = df["ijo_kubun_code"].astype(str).str.strip()
        df = df[ijo == "0"].copy()

    # kakutei_chakujun: 0(取消), NULL, 空白 を除外
    if "kakutei_chakujun" in df.columns:
        chaku_num = pd.to_numeric(
            df["kakutei_chakujun"].astype(str).str.strip(), errors="coerce"
        )
        df = df[chaku_num.notna() & (chaku_num != 0)].copy()

    # 追加フィルタ
    for col, val in conditions.items():
        if col not in df.columns:
            logger.warning("conditions: カラム '%s' 存在しない → スキップ", col)
            continue
        if isinstance(val, list):
            df = df[df[col].isin(val)].copy()
        else:
            df = df[df[col] == val].copy()

    logger.info("基本フィルタ: %d → %d 行", orig_len, len(df))
    return df


# =============================================================================
# セグメント分割
# =============================================================================

def _get_surface(track_code_series: pd.Series) -> pd.Series:
    s = track_code_series.astype(str).str.strip()
    result = pd.Series("不明", index=track_code_series.index, dtype=str)
    result[s.str.startswith("1")] = "芝"
    result[s.str.startswith("2")] = "ダート"
    return result


def _get_course27_series(df: pd.DataFrame) -> pd.Series:
    from backend.engine.course_categories import get_category

    kyori_col = next((c for c in ["ra_kyori", "kyori", "bac_kyori"] if c in df.columns), None)
    if not kyori_col or "track_code" not in df.columns or "keibajo_code" not in df.columns:
        return pd.Series("unknown", index=df.index, dtype=str)

    surface = _get_surface(df["track_code"])
    surf_map = {"芝": "芝", "ダート": "ダ"}
    result = pd.Series("unknown", index=df.index, dtype=str)

    for idx in df.index:
        code = str(df.at[idx, "keibajo_code"]).strip()
        surf = surf_map.get(surface.at[idx])
        if surf is None:
            continue
        try:
            dist = int(pd.to_numeric(
                str(df.at[idx, kyori_col]).strip(), errors="coerce"
            ))
        except (ValueError, TypeError):
            continue
        result.at[idx] = get_category(code, surf, dist)
    return result


def _split_segments(df: pd.DataFrame, segment: str) -> dict:
    if segment == "SURFACE_2":
        if "track_code" not in df.columns:
            logger.warning("SURFACE_2: track_code なし → GLOBAL扱い")
            return {"GLOBAL": df}
        surface = _get_surface(df["track_code"])
        result = {}
        for name in ["芝", "ダート"]:
            mask = surface == name
            if mask.sum() > 0:
                result[name] = df[mask].copy()
        return result

    if segment == "COURSE_27":
        cats = _get_course27_series(df)
        result = {}
        for cat in sorted(cats.unique()):
            if cat == "unknown":
                continue
            mask = cats == cat
            if mask.sum() > 0:
                result[cat] = df[mask].copy()
        return result

    return {"GLOBAL": df}


# =============================================================================
# ビン生成
# =============================================================================

_HIGH_CARD = 500
_TOP_N = 50
_AUTO_Q = 10


def _is_continuous_numeric(series: pd.Series, n_unique: int) -> bool:
    if n_unique <= 30:
        return False
    if pd.api.types.is_numeric_dtype(series):
        return True
    num = pd.to_numeric(series, errors="coerce")
    non_null = series.notna().sum()
    if non_null == 0:
        return False
    return (num.notna().sum() / non_null) > 0.9


def _binify(series: pd.Series, key: str, bin_config: dict) -> pd.Series:
    null_mask = series.isna() | series.astype(str).str.strip().isin(["", "nan", "None", "nan"])
    n_unique = series.nunique(dropna=True)

    # 高カーディナリティ
    if n_unique > _HIGH_CARD:
        top_vals = series.value_counts(dropna=True).head(_TOP_N).index
        result = series.where(series.isin(top_vals), other="その他").astype(str)
        result[null_mask] = "不明"
        return result

    # bin_config 指定
    if key in bin_config:
        cfg = bin_config[key]
        method = cfg.get("method", "cut")
        bins = cfg.get("bins", [])
        labels = cfg.get("labels", None)
        if bins and method == "cut":
            num = pd.to_numeric(series, errors="coerce")
            result = pd.cut(num, bins=bins, labels=labels, right=False).astype(str)
            result[null_mask] = "不明"
            return result

    # 連続値 → qcut
    if _is_continuous_numeric(series, n_unique):
        num = pd.to_numeric(series, errors="coerce")
        try:
            result = pd.qcut(num, q=_AUTO_Q, duplicates="drop").astype(str)
            result[null_mask] = "不明"
            return result
        except Exception as e:
            logger.warning("qcut失敗 (%s): %s → カテゴリ扱い", key, e)

    # カテゴリ
    result = series.astype(str).str.strip()
    result[null_mask] = "不明"
    return result


def _make_bin_labels(df: pd.DataFrame, keys: list, bin_config: dict) -> pd.Series:
    binned = []
    for key in keys:
        if key not in df.columns:
            logger.warning("集計キー '%s' が存在しない", key)
            s = pd.Series("不明", index=df.index, dtype=str)
        else:
            s = _binify(df[key], key, bin_config)
        binned.append(s)

    if len(binned) == 1:
        return binned[0]
    result = binned[0]
    for b in binned[1:]:
        result = result + " × " + b
    return result


# =============================================================================
# ビンソート
# =============================================================================

def _bin_sort_key(label: str):
    if label in ("不明", "その他"):
        return (1, float("inf"), label)
    try:
        return (0, float(label), "")
    except (ValueError, TypeError):
        pass
    # "X × Y" 形式
    parts = label.split(" × ")
    try:
        return (0, float(parts[0]), label)
    except (ValueError, TypeError):
        pass
    # "(0.5, 2.5]" などの区間表現
    nums = re.findall(r"[-\d.]+", label)
    if nums:
        try:
            return (0, float(nums[0]), label)
        except (ValueError, TypeError):
            pass
    return (0, float("inf"), label)


def _sort_bins(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df["_sk"] = df["bin_label"].apply(_bin_sort_key)
    df = df.sort_values("_sk").drop(columns=["_sk"]).reset_index(drop=True)
    return df


# =============================================================================
# ビンごとの集計
# =============================================================================

_RESULT_COLS = [
    "bin_label", "tansho_count", "tansho_hit", "tansho_hit_rate", "tansho_roi",
    "fukusho_count", "fukusho_hit", "fukusho_hit_rate", "fukusho_roi",
    "tansho_corrected_roi", "fukusho_corrected_roi", "confidence",
]


def _compute_bin_stats(bin_df: pd.DataFrame, query: AnalysisQuery) -> dict:
    tlo, thi = query.odds_filter["tansho"]
    flo, fhi = query.odds_filter["fukusho"]

    tansho_odds = pd.to_numeric(
        bin_df.get("tansho_odds", pd.Series(np.nan, index=bin_df.index)).astype(str).str.strip(),
        errors="coerce",
    )
    fukusho_odds = pd.to_numeric(
        bin_df.get("fukusho_odds", pd.Series(np.nan, index=bin_df.index)).astype(str).str.strip(),
        errors="coerce",
    )

    chaku_num = pd.to_numeric(
        bin_df["kakutei_chakujun"].astype(str).str.strip(), errors="coerce"
    ) if "kakutei_chakujun" in bin_df.columns else pd.Series(np.nan, index=bin_df.index)

    if "race_date" in bin_df.columns:
        race_year = bin_df["race_date"].astype(str).str[:4]
    elif "kaisai_nen" in bin_df.columns:
        race_year = bin_df["kaisai_nen"].astype(str).str.strip()
    else:
        race_year = pd.Series("2020", index=bin_df.index)

    # ---- 単勝 ----
    t_mask = (tansho_odds >= tlo) & (tansho_odds <= thi)
    t_odds = tansho_odds[t_mask]
    t_chaku = chaku_num[t_mask]
    t_year = race_year[t_mask]
    t_count = int(t_mask.sum())
    t_hit = int((t_chaku == 1).sum())
    t_hit_rate = round(t_hit / t_count * 100, 4) if t_count > 0 else 0.0
    t_roi = round((t_odds * 100 * (t_chaku == 1)).sum() / t_count, 4) if t_count > 0 else 0.0

    if t_count > 0:
        _df_t = pd.DataFrame({
            "_odds": t_odds.values,
            "_hit": (t_chaku == 1).astype(int).values,
            "_year": t_year.values,
        })
        t_corr = calc_corrected_return_rate(
            _df_t, odds_col="_odds", hit_flag_col="_hit",
            year_col="_year", is_fukusho=False,
        )["corrected_return_rate"]
    else:
        t_corr = 0.0

    # ---- 複勝 (tansho_odds を proxy として使用) ----
    f_mask = (tansho_odds >= flo) & (tansho_odds <= fhi)
    f_odds_proxy = tansho_odds[f_mask]
    f_chaku = chaku_num[f_mask]
    f_year = race_year[f_mask]
    f_fukusho_odds = fukusho_odds[f_mask]
    f_count = int(f_mask.sum())
    f_hit_mask = f_chaku.isin([1, 2, 3])
    f_hit = int(f_hit_mask.sum())
    f_hit_rate = round(f_hit / f_count * 100, 4) if f_count > 0 else 0.0

    # 複勝払戻: 的中馬は fukusho_odds * 100、落馬は 0
    f_payout = (f_fukusho_odds * 100).where(f_hit_mask, other=0.0).fillna(0.0)
    f_roi = round(f_payout.sum() / f_count, 4) if f_count > 0 else 0.0

    if f_count > 0:
        _df_f = pd.DataFrame({
            "_odds": f_odds_proxy.values,
            "_hit": f_hit_mask.astype(int).values,
            "_year": f_year.values,
        })
        f_corr = calc_corrected_return_rate(
            _df_f, odds_col="_odds", hit_flag_col="_hit",
            year_col="_year", is_fukusho=True,
        )["corrected_return_rate"]
    else:
        f_corr = 0.0

    # 信頼度
    n_min = min(t_count, f_count)
    confidence = round(math.sqrt(n_min / (n_min + 400)), 6) if n_min > 0 else 0.0

    return {
        "tansho_count": t_count,
        "tansho_hit": t_hit,
        "tansho_hit_rate": t_hit_rate,
        "tansho_roi": t_roi,
        "fukusho_count": f_count,
        "fukusho_hit": f_hit,
        "fukusho_hit_rate": f_hit_rate,
        "fukusho_roi": f_roi,
        "tansho_corrected_roi": round(t_corr, 4),
        "fukusho_corrected_roi": round(f_corr, 4),
        "confidence": confidence,
    }


def _analyze_segment(seg_df: pd.DataFrame, query: AnalysisQuery) -> pd.DataFrame:
    keys = [k for k in [query.key1, query.key2, query.key3] if k is not None]
    seg_df = seg_df.copy()
    seg_df["_bl"] = _make_bin_labels(seg_df, keys, query.bin_config)

    records = []
    for bin_val, group in seg_df.groupby("_bl", sort=False):
        stats = _compute_bin_stats(group, query)
        stats["bin_label"] = str(bin_val)
        records.append(stats)

    if not records:
        return pd.DataFrame(columns=_RESULT_COLS)

    df_res = pd.DataFrame(records)[_RESULT_COLS]
    return _sort_bins(df_res)


# =============================================================================
# メイン関数
# =============================================================================

def run_analysis(conn, query: AnalysisQuery) -> dict:
    """
    分析を実行し結果を返す。

    Returns:
        {
            "query": query,
            "segments": { "セグメント名": DataFrame },
            "summary": {
                "total_rows": int,
                "filtered_rows": int,
                "valid_tansho_rows": int,
                "valid_fukusho_rows": int,
                "edge_bins_tansho": int,
                "edge_bins_fukusho": int,
            }
        }
    """
    logger.info("run_analysis: '%s' 開始", query.name)

    # Step 1: データ取得
    df = _load_data(conn, query)
    total_rows = len(df)

    # Step 2: 基本フィルタ
    df = _apply_basic_filters(df, query.conditions)
    filtered_rows = len(df)

    # Step 3: セグメント分割
    segments_dfs = _split_segments(df, query.segment)

    # Step 4-6: セグメントごとに分析
    result_segments = {}
    edge_bins_tansho = 0
    edge_bins_fukusho = 0
    valid_tansho_rows = 0
    valid_fukusho_rows = 0

    for seg_name, seg_df in segments_dfs.items():
        logger.info("セグメント '%s': %d 行", seg_name, len(seg_df))
        seg_result = _analyze_segment(seg_df, query)
        result_segments[seg_name] = seg_result

        if not seg_result.empty:
            valid_tansho_rows += int(seg_result["tansho_count"].sum())
            valid_fukusho_rows += int(seg_result["fukusho_count"].sum())
            edge_bins_tansho += int(
                ((seg_result["tansho_corrected_roi"] >= 80) &
                 (seg_result["confidence"] >= 0.25)).sum()
            )
            edge_bins_fukusho += int(
                ((seg_result["fukusho_corrected_roi"] >= 80) &
                 (seg_result["confidence"] >= 0.25)).sum()
            )

    logger.info("run_analysis: '%s' 完了", query.name)
    return {
        "query": query,
        "segments": result_segments,
        "summary": {
            "total_rows": total_rows,
            "filtered_rows": filtered_rows,
            "valid_tansho_rows": valid_tansho_rows,
            "valid_fukusho_rows": valid_fukusho_rows,
            "edge_bins_tansho": edge_bins_tansho,
            "edge_bins_fukusho": edge_bins_fukusho,
        },
    }

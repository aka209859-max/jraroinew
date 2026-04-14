"""
加工ファクター生成エンジン

prev_race_loader.py が返す DataFrame（前走付き）に対して、
CEOの組み合わせ分析用の加工カラムを追加する。

生成する加工ファクター一覧:
  1. bataiju_bin_20kg       : 前走馬体重 20kg 刻みビン
  2. kyori_hendo            : 今走距離 変化（増/減/同）
  3. kyori_kubun            : 距離区分（短/マイル/中/長）
  4. corner4_group_prev1    : 前走4角通過順位グループ（先行/中団/後方）
  5. babajotai_heavy_flag   : 重・不良フラグ（1=重か不良、0=良か稍重）
  6. chichi_name            : 種牡馬名（父、jvd_sk.ketto_joho_01a）
  7. hahachichi_name        : 母父名（jvd_sk.ketto_joho_05a）
  8. sanchimei              : 産地名（jvd_sk.sanchimei）
  9. idm_rank               : IDMランク S/A/B/C/D（jrd_kyi_fixed.idm）
  10. chokyoshi_rank        : 調教師ランク S/A/B/C/D（2025年勝率）
  11. kishu_rank            : 騎手ランク S/A/B/C/D（2025年勝率）
  12. kijun_odds_bin5       : 前日基準単勝オッズ 5倍刻みビン（jrd_joa.kijun_odds_tansho）
  13. ls_shisu_bin4         : LS指数 4刻みビン（jrd_joa_fixed.ls_shisu）
  14. cid_soten             : CID総点（jrd_joa.cid）
  15. kyakushitsu_kyi       : 今走予想脚質（jrd_kyi_fixed.kyakushitsu）
  16. kishu_code_kyi        : 騎手コード（jrd_kyi_fixed.kishu_code）
  17. chokyoshi_code_kyi    : 調教師コード（jrd_kyi_fixed.chokyoshi_code）
  18. ichi_shisu            : 位置指数（jrd_kyi_fixed.ichi_shisu）
  19. taikei                : 体型_胴（jrd_kyi.taikei ※sparse）
  20. taikei_sogo_1         : 体型_トモ（jrd_kyi.taikei_sogo_1 ※sparse）
  21. pace_yoso             : ペース予想（jrd_kyi.pace_yoso ※sparse）
  22. ichi_shisu_juni       : 位置指数順位（jrd_kyi.ichi_shisu_juni ※sparse）
  23. yuso_kubun            : 予想区分（jrd_kyi.yuso_kubun ※sparse）
  24. prev_rpci             : 前走RPCI（スキーマ未存在 → NULL）

■ 制約
  - ACTUAL_DB_SCHEMA_2293_COLUMNS.csv に存在するカラムのみ使用
  - 存在しないカラムは WARNING を出して NULL カラムとして追加
  - ターゲットリーク禁止（当日データ不使用）
  - 調教師・騎手ランクは 2025 年通算で固定計算（走-forward 外）

Usage:
    from backend.engine.derived_factors import derive_all_factors
    df_prev = load_global_prev_races(conn, "20240101", "20241231")
    df_full = derive_all_factors(df_prev, conn)
"""
from __future__ import annotations

import logging
import warnings
from typing import Optional

import numpy as np
import pandas as pd

from backend.engine.data_loader_v2 import JVAN_TO_JRDB_RACE_KEY8

logger = logging.getLogger(__name__)

# =============================================================================
# 定数
# =============================================================================

# JRA 競馬場コード
_JRA_CODES_SQL = "('01','02','03','04','05','06','07','08','09','10')"

# 調教師・騎手ランク計算に使う年
_RANK_YEAR: str = "2025"

# percentile 境界（S: 上位10%, A: 10-25%, B: 25-50%, C: 50-75%, D: 下位25%）
_PCTILE_CUTS = [0, 25, 50, 75, 90, 100]
_PCTILE_LABELS = ["D", "C", "B", "A", "S"]  # 低→高の順


# =============================================================================
# ユーティリティ
# =============================================================================

def _add_null_col(df: pd.DataFrame, col_name: str, reason: str) -> pd.DataFrame:
    """カラムが取得できない場合に NULL カラムを追加してログを記録する。"""
    if col_name not in df.columns:
        logger.warning("derived_factors: カラム '%s' は取得不可（%s）→ NULL で追加", col_name, reason)
        df = df.copy()
        df[col_name] = np.nan
    return df


def _synth_jrdb_key8_series(df: pd.DataFrame) -> pd.Series:
    """
    jvd_se の jvd_se 列群から JRDB 8byte レースキーを Python で合成する。

    SQL の JVAN_TO_JRDB_RACE_KEY8 式と同等の変換を行う。

    keibajo_code(2) + year_last2(2) + kai(1) + hex(nichime)(1) + race_bango.zfill(2)
    """
    def _nichi_char(n: int) -> str:
        if n <= 9:
            return str(n)
        elif n == 10:
            return "a"
        elif n == 11:
            return "b"
        elif n == 12:
            return "c"
        return str(n)

    codes = df["keibajo_code"].astype(str).str.strip()
    year2 = df["kaisai_nen"].astype(str).str.strip().str[-2:]
    kai = df["kaisai_kai"].astype(str).str.strip().apply(
        lambda x: str(int(x)) if x.isdigit() else x
    )
    nichime_int = pd.to_numeric(
        df["kaisai_nichime"].astype(str).str.strip(), errors="coerce"
    ).fillna(0).astype(int)
    nichi = nichime_int.apply(_nichi_char)
    race = df["race_bango"].astype(str).str.strip().apply(
        lambda x: str(int(x)).zfill(2) if x.isdigit() else x.zfill(2)
    )
    return codes + year2 + kai + nichi + race


def _get_unique_race_keys(df: pd.DataFrame) -> pd.DataFrame:
    """df から一意のレースキー（競馬場+日付+開催+日目+レース番号）を返す。"""
    key_cols = ["keibajo_code", "kaisai_nen", "kaisai_tsukihi",
                "kaisai_kai", "kaisai_nichime", "race_bango"]
    existing = [c for c in key_cols if c in df.columns]
    return df[existing].drop_duplicates()


def _safe_merge(
    df: pd.DataFrame,
    extra: pd.DataFrame,
    on: list[str],
    suffix: str = "_extra",
) -> pd.DataFrame:
    """
    extra をマージする。extra が空の場合はスキップ。
    重複カラムはリネームせず、extra 側の新カラムのみを追加する。
    """
    if extra is None or extra.empty:
        return df
    new_cols = [c for c in extra.columns if c not in on and c not in df.columns]
    if not new_cols:
        return df
    merge_cols = [c for c in on if c in extra.columns and c in df.columns]
    if not merge_cols:
        return df
    subset = extra[merge_cols + new_cols].drop_duplicates(subset=merge_cols)
    return df.merge(subset, on=merge_cols, how="left")


# =============================================================================
# Phase 1: 既存カラムからの純計算
# =============================================================================

def _bin_bataiju_20kg(df: pd.DataFrame) -> pd.Series:
    """
    前走馬体重（bataiju_prev1）を 20kg 刻みでビン化する。

    ビン:
      380未満 / 380-399 / 400-419 / 420-439 / 440-459 /
      460-479 / 480-499 / 500-519 / 520以上
    """
    col = "bataiju_prev1"
    if col not in df.columns:
        logger.warning("derived_factors: '%s' が df に存在しない → bataiju_bin_20kg は NULL", col)
        return pd.Series(np.nan, index=df.index, dtype=object)

    bins = [0, 380, 400, 420, 440, 460, 480, 500, 520, 9999]
    labels = [
        "380未満", "380-399", "400-419", "420-439", "440-459",
        "460-479", "480-499", "500-519", "520以上",
    ]
    return pd.cut(
        pd.to_numeric(df[col], errors="coerce"),
        bins=bins,
        labels=labels,
        right=False,
    )


def _compute_kyori_hendo(df: pd.DataFrame) -> pd.Series:
    """
    今走距離（kyori）と前走距離（kyori_prev1）を比較し、増/減/同 を返す。
    """
    if "kyori" not in df.columns or "kyori_prev1" not in df.columns:
        logger.warning("derived_factors: kyori / kyori_prev1 が df に存在しない → kyori_hendo は NULL")
        return pd.Series(np.nan, index=df.index, dtype=object)

    cur = pd.to_numeric(df["kyori"], errors="coerce")
    prev = pd.to_numeric(df["kyori_prev1"], errors="coerce")
    diff = cur - prev

    result = pd.Series(np.nan, index=df.index, dtype=object)
    result[diff > 0] = "増"
    result[diff < 0] = "減"
    result[diff == 0] = "同"
    return result


def _compute_kyori_kubun(df: pd.DataFrame) -> pd.Series:
    """
    距離区分（短/マイル/中/長）を返す。

    短: ~1399m / マイル: 1400-1799m / 中: 1800-2199m / 長: 2200m~
    """
    if "kyori" not in df.columns:
        logger.warning("derived_factors: 'kyori' が df に存在しない → kyori_kubun は NULL")
        return pd.Series(np.nan, index=df.index, dtype=object)

    kyori = pd.to_numeric(df["kyori"], errors="coerce")
    result = pd.Series(np.nan, index=df.index, dtype=object)
    result[kyori < 1400] = "短"
    result[(kyori >= 1400) & (kyori < 1800)] = "マイル"
    result[(kyori >= 1800) & (kyori < 2200)] = "中"
    result[kyori >= 2200] = "長"
    return result


def _compute_corner4_group(df: pd.DataFrame) -> pd.Series:
    """
    前走4角通過順位（corner_4_prev1）を 先行/中団/後方 に分類する。

    先行: 1-3 / 中団: 4-6 / 後方: 7以上
    """
    col = "corner_4_prev1"
    if col not in df.columns:
        logger.warning("derived_factors: '%s' が df に存在しない → corner4_group_prev1 は NULL", col)
        return pd.Series(np.nan, index=df.index, dtype=object)

    pos = pd.to_numeric(df[col], errors="coerce")
    result = pd.Series(np.nan, index=df.index, dtype=object)
    result[(pos >= 1) & (pos <= 3)] = "先行"
    result[(pos >= 4) & (pos <= 6)] = "中団"
    result[pos >= 7] = "後方"
    return result


def _compute_babajotai_flag(df: pd.DataFrame) -> pd.Series:
    """
    馬場状態フラグ（重・不良=1, 良・稍重=0）を返す。

    使用カラム（優先順）:
      1. babajotai_code_shiba  （芝）
      2. babajotai_code_dirt   （ダート）
    コード:
      1=良, 2=稍重, 3=重, 4=不良
    """
    # まずどちらかのカラムがあれば使う。track_code で芝/ダートを判別。
    shiba_col = "babajotai_code_shiba"
    dirt_col = "babajotai_code_dirt"
    track_col = "track_code"

    has_shiba = shiba_col in df.columns
    has_dirt = dirt_col in df.columns

    if not has_shiba and not has_dirt:
        logger.warning("derived_factors: babajotai_code_shiba/dirt が df に存在しない → babajotai_heavy_flag は NULL")
        return pd.Series(np.nan, index=df.index, dtype=object)

    result = pd.Series(np.nan, index=df.index, dtype=float)

    def _is_heavy(code_series: pd.Series) -> pd.Series:
        code_num = pd.to_numeric(code_series.astype(str).str.strip(), errors="coerce")
        return code_num.isin([3, 4])

    def _is_light(code_series: pd.Series) -> pd.Series:
        code_num = pd.to_numeric(code_series.astype(str).str.strip(), errors="coerce")
        return code_num.isin([1, 2])

    if has_shiba and has_dirt and track_col in df.columns:
        track = df[track_col].astype(str).str.strip()
        turf_mask = track.str.startswith("1")
        dirt_mask = track.str.startswith("2")
        result[turf_mask & _is_heavy(df[shiba_col])] = 1.0
        result[turf_mask & _is_light(df[shiba_col])] = 0.0
        result[dirt_mask & _is_heavy(df[dirt_col])] = 1.0
        result[dirt_mask & _is_light(df[dirt_col])] = 0.0
    elif has_shiba:
        result[_is_heavy(df[shiba_col])] = 1.0
        result[_is_light(df[shiba_col])] = 0.0
    else:
        result[_is_heavy(df[dirt_col])] = 1.0
        result[_is_light(df[dirt_col])] = 0.0

    return result


# =============================================================================
# Phase 2: DB から追加データ取得
# =============================================================================

def _load_extra_from_kyi_fixed(conn, df: pd.DataFrame) -> pd.DataFrame:
    """
    jrd_kyi_fixed から追加カラムを取得する。

    取得カラム:
      idm, kyakushitsu (予想脚質), kishu_code, chokyoshi_code,
      ichi_shisu, pace_shisu, kyusha_rank
    """
    try:
        # 一意の jrdb_race_key8 を生成
        key_series = _synth_jrdb_key8_series(df)
        unique_keys = key_series.dropna().unique().tolist()
        if not unique_keys:
            return pd.DataFrame()

        keys_sql = ", ".join(f"'{k}'" for k in unique_keys)
        query = f"""
        SELECT
            jrdb_race_key8,
            TRIM(umaban) AS umaban,
            idm AS kyi_idm_raw,
            kyakushitsu AS kyakushitsu_kyi,
            kishu_code AS kishu_code_kyi,
            chokyoshi_code AS chokyoshi_code_kyi,
            ichi_shisu AS ichi_shisu_kyi,
            pace_shisu AS pace_shisu_kyi,
            kyusha_rank AS kyusha_rank_kyi
        FROM jrd_kyi_fixed
        WHERE jrdb_race_key8 IN ({keys_sql})
        """
        extra = pd.read_sql_query(query, conn)
        extra["jrdb_race_key8"] = extra["jrdb_race_key8"].astype(str).str.strip()
        extra["umaban"] = extra["umaban"].astype(str).str.strip()
        return extra
    except Exception as e:
        logger.warning("derived_factors: jrd_kyi_fixed 取得エラー: %s", e)
        return pd.DataFrame()


def _load_extra_from_joa(conn, df: pd.DataFrame) -> pd.DataFrame:
    """
    jrd_joa から追加カラムを取得する。

    取得カラム:
      kijun_odds_tansho, cid（CID総点）

    jrd_joa には jrdb_race_key8 がない。
    keibajo_code + race_shikonen(=kaisai_nen) + kaisai_kai + kaisai_nichime + race_bango + umaban で JOIN。
    """
    try:
        key_cols = ["keibajo_code", "kaisai_nen", "kaisai_kai",
                    "kaisai_nichime", "race_bango", "umaban"]
        missing = [c for c in key_cols if c not in df.columns]
        if missing:
            logger.warning("derived_factors: jrd_joa JOIN キー不足: %s", missing)
            return pd.DataFrame()

        # ユニークな (keibajo_code, kaisai_nen, kaisai_kai, kaisai_nichime, race_bango, umaban) を IN 句で絞る
        # kaisai_nenで年を絞り、全件取得してマージ（大量行を避けるため年リストでフィルタ）
        unique_years = df["kaisai_nen"].astype(str).str.strip().unique().tolist()
        years_sql = ", ".join(f"'{y}'" for y in unique_years)
        unique_keibajo = df["keibajo_code"].astype(str).str.strip().unique().tolist()
        keibajo_sql = ", ".join(f"'{k}'" for k in unique_keibajo)

        query = f"""
        SELECT
            TRIM(keibajo_code) AS keibajo_code,
            TRIM(race_shikonen) AS kaisai_nen,
            TRIM(kaisai_kai) AS kaisai_kai,
            TRIM(kaisai_nichime) AS kaisai_nichime,
            TRIM(race_bango) AS race_bango,
            TRIM(umaban) AS umaban,
            kijun_odds_tansho AS kijun_odds_tansho_joa,
            cid AS cid_soten
        FROM jrd_joa
        WHERE race_shikonen IN ({years_sql})
          AND keibajo_code IN ({keibajo_sql})
        """
        extra = pd.read_sql_query(query, conn)
        for c in ["keibajo_code", "kaisai_nen", "kaisai_kai",
                  "kaisai_nichime", "race_bango", "umaban"]:
            extra[c] = extra[c].astype(str).str.strip()
        return extra
    except Exception as e:
        logger.warning("derived_factors: jrd_joa 取得エラー: %s", e)
        return pd.DataFrame()


def _load_extra_from_joa_fixed(conn, df: pd.DataFrame) -> pd.DataFrame:
    """
    jrd_joa_fixed から ls_shisu を取得する。

    jrd_joa_fixed には jrdb_race_key8 がある。
    """
    try:
        key_series = _synth_jrdb_key8_series(df)
        unique_keys = key_series.dropna().unique().tolist()
        if not unique_keys:
            return pd.DataFrame()

        keys_sql = ", ".join(f"'{k}'" for k in unique_keys)
        query = f"""
        SELECT
            jrdb_race_key8,
            TRIM(umaban) AS umaban,
            ls_shisu AS ls_shisu_joa
        FROM jrd_joa_fixed
        WHERE jrdb_race_key8 IN ({keys_sql})
        """
        extra = pd.read_sql_query(query, conn)
        extra["jrdb_race_key8"] = extra["jrdb_race_key8"].astype(str).str.strip()
        extra["umaban"] = extra["umaban"].astype(str).str.strip()
        return extra
    except Exception as e:
        logger.warning("derived_factors: jrd_joa_fixed 取得エラー: %s", e)
        return pd.DataFrame()


def _load_extra_from_kyi_raw(conn, df: pd.DataFrame) -> pd.DataFrame:
    """
    jrd_kyi（生テーブル、sparse）から追加カラムを取得する。

    取得カラム:
      taikei, taikei_sogo_1, pace_yoso, ichi_shisu_juni, yuso_kubun,
      kijun_odds_tansho（jrd_joa で取得できない場合のフォールバック）

    注意: jrd_kyi は直近データのみ（2026-03 時点で 517 行）。
    ほとんどのケースで NULL になる。
    """
    try:
        unique_years = df["kaisai_nen"].astype(str).str.strip().unique().tolist()
        years_sql = ", ".join(f"'{y}'" for y in unique_years)
        unique_keibajo = df["keibajo_code"].astype(str).str.strip().unique().tolist()
        keibajo_sql = ", ".join(f"'{k}'" for k in unique_keibajo)

        query = f"""
        SELECT
            TRIM(keibajo_code) AS keibajo_code,
            TRIM(race_shikonen) AS kaisai_nen,
            TRIM(kaisai_kai) AS kaisai_kai,
            TRIM(kaisai_nichime) AS kaisai_nichime,
            TRIM(race_bango) AS race_bango,
            TRIM(umaban) AS umaban,
            taikei,
            taikei_sogo_1,
            pace_yoso,
            ichi_shisu_juni,
            yuso_kubun
        FROM jrd_kyi
        WHERE race_shikonen IN ({years_sql})
          AND keibajo_code IN ({keibajo_sql})
        """
        extra = pd.read_sql_query(query, conn)
        for c in ["keibajo_code", "kaisai_nen", "kaisai_kai",
                  "kaisai_nichime", "race_bango", "umaban"]:
            extra[c] = extra[c].astype(str).str.strip()
        return extra
    except Exception as e:
        logger.warning("derived_factors: jrd_kyi（raw）取得エラー: %s", e)
        return pd.DataFrame()


def _load_extra_from_sk(conn, df: pd.DataFrame) -> pd.DataFrame:
    """
    jvd_sk から血統・産地情報を取得する。

    取得カラム:
      ketto_joho_01a（父）, ketto_joho_05a（母父）, sanchimei（産地）

    JOIN キー: ketto_toroku_bango（馬個体識別）
    """
    try:
        if "ketto_toroku_bango" not in df.columns:
            logger.warning("derived_factors: ketto_toroku_bango が df に存在しない → jvd_sk 取得不可")
            return pd.DataFrame()

        unique_ids = (
            df["ketto_toroku_bango"].astype(str).str.strip()
            .dropna().unique().tolist()
        )
        if not unique_ids:
            return pd.DataFrame()

        ids_sql = ", ".join(f"'{i}'" for i in unique_ids)
        query = f"""
        SELECT
            TRIM(ketto_toroku_bango) AS ketto_toroku_bango,
            TRIM(ketto_joho_01a) AS chichi_name,
            TRIM(ketto_joho_05a) AS hahachichi_name,
            TRIM(sanchimei) AS sanchimei
        FROM jvd_sk
        WHERE ketto_toroku_bango IN ({ids_sql})
        """
        extra = pd.read_sql_query(query, conn)
        extra["ketto_toroku_bango"] = extra["ketto_toroku_bango"].astype(str).str.strip()
        # 同一 ketto_toroku_bango に複数行の可能性（data_kubun 違い等）→ 先頭を採用
        extra = extra.drop_duplicates(subset=["ketto_toroku_bango"], keep="first")
        return extra
    except Exception as e:
        logger.warning("derived_factors: jvd_sk 取得エラー: %s", e)
        return pd.DataFrame()


def _load_babajotai_from_ra(conn, df: pd.DataFrame) -> pd.DataFrame:
    """
    jvd_ra から馬場状態コードを取得する（df に存在しない場合のフォールバック）。
    """
    try:
        key_cols = ["keibajo_code", "kaisai_nen", "kaisai_tsukihi",
                    "kaisai_kai", "kaisai_nichime", "race_bango"]
        missing = [c for c in key_cols if c not in df.columns]
        if missing:
            return pd.DataFrame()

        unique_years = df["kaisai_nen"].astype(str).str.strip().unique().tolist()
        years_sql = ", ".join(f"'{y}'" for y in unique_years)
        unique_keibajo = df["keibajo_code"].astype(str).str.strip().unique().tolist()
        keibajo_sql = ", ".join(f"'{k}'" for k in unique_keibajo)

        query = f"""
        SELECT
            TRIM(keibajo_code) AS keibajo_code,
            TRIM(kaisai_nen) AS kaisai_nen,
            TRIM(kaisai_tsukihi) AS kaisai_tsukihi,
            TRIM(kaisai_kai) AS kaisai_kai,
            TRIM(kaisai_nichime) AS kaisai_nichime,
            TRIM(race_bango) AS race_bango,
            TRIM(babajotai_code_shiba) AS babajotai_code_shiba,
            TRIM(babajotai_code_dirt) AS babajotai_code_dirt
        FROM jvd_ra
        WHERE kaisai_nen IN ({years_sql})
          AND keibajo_code IN ({keibajo_sql})
        """
        extra = pd.read_sql_query(query, conn)
        for c in ["keibajo_code", "kaisai_nen", "kaisai_tsukihi",
                  "kaisai_kai", "kaisai_nichime", "race_bango"]:
            extra[c] = extra[c].astype(str).str.strip()
        return extra
    except Exception as e:
        logger.warning("derived_factors: jvd_ra（babajotai）取得エラー: %s", e)
        return pd.DataFrame()


# =============================================================================
# Phase 3: ランク計算
# =============================================================================

def _percentile_rank(series: pd.Series) -> pd.Series:
    """
    数値 Series を S/A/B/C/D の 5 ランクに変換する。

    S: 上位 10% / A: 10-25% / B: 25-50% / C: 50-75% / D: 下位 25%
    """
    result = pd.Series(np.nan, index=series.index, dtype=object)
    valid = series.dropna()
    if valid.empty:
        return result

    p25 = valid.quantile(0.25)
    p50 = valid.quantile(0.50)
    p75 = valid.quantile(0.75)
    p90 = valid.quantile(0.90)

    result[series < p25] = "D"
    result[(series >= p25) & (series < p50)] = "C"
    result[(series >= p50) & (series < p75)] = "B"
    result[(series >= p75) & (series < p90)] = "A"
    result[series >= p90] = "S"
    return result


def _compute_idm_rank(df: pd.DataFrame) -> pd.Series:
    """
    IDM 値（kyi_idm_raw または既存の idm 系カラム）から S/A/B/C/D ランクを付与する。
    """
    # 優先順位: kyi_idm_raw > kyi_idm > idm
    for col in ["kyi_idm_raw", "kyi_idm", "idm"]:
        if col in df.columns:
            return _percentile_rank(pd.to_numeric(df[col], errors="coerce"))
    logger.warning("derived_factors: IDM カラムが存在しない → idm_rank は NULL")
    return pd.Series(np.nan, index=df.index, dtype=object)


def _compute_trainer_rank(conn) -> dict:
    """
    2025 年通算の調教師コード別勝率を計算し S/A/B/C/D ランクを返す辞書。

    勝率 = 1着数 / 全出走数（kakutei_chakujun = 1 の割合）
    """
    try:
        query = f"""
        SELECT
            TRIM(chokyoshi_code) AS chokyoshi_code,
            COUNT(*) AS total,
            SUM(CASE WHEN TRIM(kakutei_chakujun) = '1' THEN 1 ELSE 0 END) AS wins
        FROM jvd_se
        WHERE keibajo_code IN {_JRA_CODES_SQL}
          AND kaisai_nen = '{_RANK_YEAR}'
          AND TRIM(chokyoshi_code) != ''
          AND TRIM(chokyoshi_code) IS NOT NULL
        GROUP BY chokyoshi_code
        HAVING COUNT(*) >= 10
        """
        agg = pd.read_sql_query(query, conn)
        agg["win_rate"] = agg["wins"] / agg["total"]
        rank_series = _percentile_rank(agg["win_rate"])
        return dict(zip(agg["chokyoshi_code"], rank_series))
    except Exception as e:
        logger.warning("derived_factors: 調教師ランク計算エラー: %s", e)
        return {}


def _compute_jockey_rank(conn) -> dict:
    """
    2025 年通算の騎手コード別勝率を計算し S/A/B/C/D ランクを返す辞書。
    """
    try:
        query = f"""
        SELECT
            TRIM(kishu_code) AS kishu_code,
            COUNT(*) AS total,
            SUM(CASE WHEN TRIM(kakutei_chakujun) = '1' THEN 1 ELSE 0 END) AS wins
        FROM jvd_se
        WHERE keibajo_code IN {_JRA_CODES_SQL}
          AND kaisai_nen = '{_RANK_YEAR}'
          AND TRIM(kishu_code) != ''
          AND TRIM(kishu_code) IS NOT NULL
        GROUP BY kishu_code
        HAVING COUNT(*) >= 10
        """
        agg = pd.read_sql_query(query, conn)
        agg["win_rate"] = agg["wins"] / agg["total"]
        rank_series = _percentile_rank(agg["win_rate"])
        return dict(zip(agg["kishu_code"], rank_series))
    except Exception as e:
        logger.warning("derived_factors: 騎手ランク計算エラー: %s", e)
        return {}


def _bin_kijun_odds_5(df: pd.DataFrame) -> pd.Series:
    """
    前日基準単勝オッズ（kijun_odds_tansho_joa）を 5 倍刻みでビン化する。

    ビン: 1-4.9 / 5-9.9 / 10-14.9 / 15-19.9 / 20-29.9 /
           30-49.9 / 50-99.9 / 100以上
    """
    col = "kijun_odds_tansho_joa"
    if col not in df.columns:
        logger.warning("derived_factors: '%s' が df に存在しない → kijun_odds_bin5 は NULL", col)
        return pd.Series(np.nan, index=df.index, dtype=object)

    odds = pd.to_numeric(df[col], errors="coerce")
    bins = [0, 5, 10, 15, 20, 30, 50, 100, 99999]
    labels = [
        "1-4.9", "5-9.9", "10-14.9", "15-19.9",
        "20-29.9", "30-49.9", "50-99.9", "100以上",
    ]
    return pd.cut(odds, bins=bins, labels=labels, right=False)


def _bin_ls_shisu_4(df: pd.DataFrame) -> pd.Series:
    """
    LS指数（ls_shisu_joa）を 4 刻みでビン化する。

    floor(ls_shisu / 4) * 4 でビン文字列を生成。
    例: ls=14 → "12-15", ls=16 → "16-19"
    """
    col = "ls_shisu_joa"
    if col not in df.columns:
        logger.warning("derived_factors: '%s' が df に存在しない → ls_shisu_bin4 は NULL", col)
        return pd.Series(np.nan, index=df.index, dtype=object)

    ls = pd.to_numeric(df[col], errors="coerce")
    bin_start = (ls // 4) * 4
    result = pd.Series(np.nan, index=df.index, dtype=object)
    valid = bin_start.notna()
    result[valid] = bin_start[valid].astype(int).astype(str) + "-" + (bin_start[valid].astype(int) + 3).astype(str)
    return result


def _compute_kyuyou_weeks(df: pd.DataFrame) -> pd.Series:
    """
    休養週数（今走 race_date - 前走 race_date_prev1）をビン化して返す。

    race_date は YYYYMMDD 文字列。race_date_prev1 はprev_race_loaderが付与する。
    ビン:
      1未満 / 1以上3未満 / 3以上5未満 / 5以上7未満 /
      7以上9未満 / 9以上10未満 / 10以上

    初出走・前走不明は NaN。
    """
    if "race_date" not in df.columns or "race_date_prev1" not in df.columns:
        logger.warning("derived_factors: race_date / race_date_prev1 が df に存在しない → kyuyou_weeks は NULL")
        return pd.Series(np.nan, index=df.index, dtype=object)

    cur = pd.to_datetime(df["race_date"], format="%Y%m%d", errors="coerce")
    prev = pd.to_datetime(df["race_date_prev1"], format="%Y%m%d", errors="coerce")
    weeks = (cur - prev).dt.days / 7.0

    bins = [0, 1, 3, 5, 7, 9, 10, 9999]
    labels = ["1未満", "1-3未満", "3-5未満", "5-7未満", "7-9未満", "9-10未満", "10以上"]
    return pd.cut(weeks, bins=bins, labels=labels, right=False)


def _load_sed_prev(conn, df: pd.DataFrame) -> pd.DataFrame:
    """
    jrd_sed から前走の race_pace と kyakushitsu_code を取得してマージする。

    JOIN キー（df 側）:
      ketto_toroku_bango + race_date_prev1[:4](=kaisai_nen)
      + race_date_prev1[4:](=kaisai_tsukihi) + keibajo_code_prev1 + race_bango_prev1

    jrd_sed 側:
      ketto_toroku_bango + kaisai_nen + kaisai_tsukihi + keibajo_code + race_bango

    必要条件: race_date_prev1, keibajo_code_prev1, race_bango_prev1 が df に存在すること。
    """
    req = ["race_date_prev1", "keibajo_code_prev1", "race_bango_prev1", "ketto_toroku_bango"]
    missing = [c for c in req if c not in df.columns]
    if missing:
        logger.warning("derived_factors: jrd_sed JOIN キー不足 %s → prev1_race_pace/kyakushitsu_sed は NULL", missing)
        return pd.DataFrame()

    try:
        unique_years = set()
        for rd in df["race_date_prev1"].dropna():
            s = str(rd).strip()
            if len(s) >= 4:
                unique_years.add(s[:4])
        if not unique_years:
            return pd.DataFrame()

        years_sql = ", ".join(f"'{y}'" for y in unique_years)
        unique_keibajo = df["keibajo_code_prev1"].dropna().astype(str).str.strip().unique().tolist()
        keibajo_sql = ", ".join(f"'{k}'" for k in unique_keibajo) if unique_keibajo else "'00'"

        query = f"""
        SELECT
            TRIM(ketto_toroku_bango) AS ketto_toroku_bango,
            TRIM(keibajo_code)       AS keibajo_code_prev1,
            TRIM(kaisai_nen)         AS _sed_kaisai_nen,
            TRIM(kaisai_tsukihi)     AS _sed_kaisai_tsukihi,
            TRIM(race_bango)         AS race_bango_prev1,
            TRIM(race_pace)          AS prev1_race_pace,
            TRIM(kyakushitsu_code)   AS prev1_kyakushitsu_sed
        FROM jrd_sed
        WHERE kaisai_nen IN ({years_sql})
          AND keibajo_code IN ({keibajo_sql})
        """
        sed = pd.read_sql_query(query, conn)
        if sed.empty:
            return pd.DataFrame()

        # race_date_prev1 から kaisai_nen / kaisai_tsukihi を分割
        df2 = df[req + ["umaban"]].copy()
        df2["_prev1_kaisai_nen"] = df2["race_date_prev1"].astype(str).str[:4]
        df2["_prev1_kaisai_tsukihi"] = df2["race_date_prev1"].astype(str).str[4:]
        df2["race_bango_prev1"] = df2["race_bango_prev1"].astype(str).str.strip()
        df2["keibajo_code_prev1"] = df2["keibajo_code_prev1"].astype(str).str.strip()

        merged = df2.merge(
            sed,
            left_on=["ketto_toroku_bango", "keibajo_code_prev1",
                     "_prev1_kaisai_nen", "_prev1_kaisai_tsukihi", "race_bango_prev1"],
            right_on=["ketto_toroku_bango", "keibajo_code_prev1",
                      "_sed_kaisai_nen", "_sed_kaisai_tsukihi", "race_bango_prev1"],
            how="left",
        )
        return merged[["ketto_toroku_bango", "keibajo_code_prev1",
                        "_prev1_kaisai_nen", "_prev1_kaisai_tsukihi", "race_bango_prev1",
                        "prev1_race_pace", "prev1_kyakushitsu_sed"]]
    except Exception as e:
        logger.warning("derived_factors: jrd_sed 前走取得エラー: %s", e)
        return pd.DataFrame()


# =============================================================================
# 公開 API
# =============================================================================

def derive_all_factors(df: pd.DataFrame, conn) -> pd.DataFrame:
    """
    前走付き DataFrame に加工ファクターカラムを追加して返す。

    Args:
        df:   prev_race_loader の出力 DataFrame（または full_factor_loader の出力）。
              必須カラム: keibajo_code, kaisai_nen, kaisai_kai, kaisai_nichime,
                           race_bango, umaban, ketto_toroku_bango, race_date
              推奨カラム: kyori, track_code, bataiju_prev1, kyori_prev1,
                           corner_4_prev1, babajotai_code_shiba/dirt
        conn: DB 接続オブジェクト（psycopg2 / SQLAlchemy）

    Returns:
        加工カラムを追加した DataFrame
    """
    df = df.copy()

    # -------------------------------------------------------------------------
    # Phase 1: 既存カラムからの純計算
    # -------------------------------------------------------------------------
    df["bataiju_bin_20kg"] = _bin_bataiju_20kg(df)
    df["kyori_hendo"] = _compute_kyori_hendo(df)
    df["kyori_kubun"] = _compute_kyori_kubun(df)
    df["corner4_group_prev1"] = _compute_corner4_group(df)

    # babajotai が df にない場合は先に jvd_ra から取得してマージ
    if "babajotai_code_shiba" not in df.columns or "babajotai_code_dirt" not in df.columns:
        logger.info("derived_factors: babajotai_code を jvd_ra から取得します")
        ba = _load_babajotai_from_ra(conn, df)
        if not ba.empty:
            merge_on = [c for c in ["keibajo_code", "kaisai_nen", "kaisai_tsukihi",
                                     "kaisai_kai", "kaisai_nichime", "race_bango"]
                        if c in ba.columns and c in df.columns]
            df = _safe_merge(df, ba, on=merge_on)

    df["babajotai_heavy_flag"] = _compute_babajotai_flag(df)

    # -------------------------------------------------------------------------
    # Phase 2: jrd_kyi_fixed から追加カラム取得
    # -------------------------------------------------------------------------
    logger.info("derived_factors: jrd_kyi_fixed から追加カラムを取得します")
    extra_kyi_fixed = _load_extra_from_kyi_fixed(conn, df)
    if not extra_kyi_fixed.empty:
        # synth_key を df 側でも計算してマージ
        df["_synth_key"] = _synth_jrdb_key8_series(df)
        extra_kyi_fixed.rename(columns={"jrdb_race_key8": "_synth_key"}, inplace=True)
        df = _safe_merge(df, extra_kyi_fixed, on=["_synth_key", "umaban"])
        df.drop(columns=["_synth_key"], inplace=True, errors="ignore")

    # -------------------------------------------------------------------------
    # Phase 3: jrd_joa から kijun_odds_tansho, cid 取得
    # -------------------------------------------------------------------------
    logger.info("derived_factors: jrd_joa から kijun_odds / cid を取得します")
    extra_joa = _load_extra_from_joa(conn, df)
    if not extra_joa.empty:
        joa_merge_on = [c for c in ["keibajo_code", "kaisai_nen", "kaisai_kai",
                                     "kaisai_nichime", "race_bango", "umaban"]
                        if c in extra_joa.columns and c in df.columns]
        df = _safe_merge(df, extra_joa, on=joa_merge_on)

    # -------------------------------------------------------------------------
    # Phase 4: jrd_joa_fixed から ls_shisu 取得
    # -------------------------------------------------------------------------
    logger.info("derived_factors: jrd_joa_fixed から ls_shisu を取得します")
    extra_joa_fixed = _load_extra_from_joa_fixed(conn, df)
    if not extra_joa_fixed.empty:
        df["_synth_key"] = _synth_jrdb_key8_series(df)
        extra_joa_fixed.rename(columns={"jrdb_race_key8": "_synth_key"}, inplace=True)
        df = _safe_merge(df, extra_joa_fixed, on=["_synth_key", "umaban"])
        df.drop(columns=["_synth_key"], inplace=True, errors="ignore")

    # -------------------------------------------------------------------------
    # Phase 5: jrd_kyi（raw/sparse）から追加カラム取得
    # -------------------------------------------------------------------------
    logger.info("derived_factors: jrd_kyi（raw）から追加カラムを取得します（sparse）")
    extra_kyi_raw = _load_extra_from_kyi_raw(conn, df)
    if not extra_kyi_raw.empty:
        kyi_merge_on = [c for c in ["keibajo_code", "kaisai_nen", "kaisai_kai",
                                     "kaisai_nichime", "race_bango", "umaban"]
                        if c in extra_kyi_raw.columns and c in df.columns]
        df = _safe_merge(df, extra_kyi_raw, on=kyi_merge_on)
    else:
        # sparse テーブルにデータなし → NULL カラム追加
        for col, reason in [
            ("taikei", "jrd_kyi（raw）にデータなし"),
            ("taikei_sogo_1", "jrd_kyi（raw）にデータなし"),
            ("pace_yoso", "jrd_kyi（raw）にデータなし"),
            ("ichi_shisu_juni", "jrd_kyi（raw）にデータなし"),
            ("yuso_kubun", "jrd_kyi（raw）にデータなし"),
        ]:
            df = _add_null_col(df, col, reason)

    # -------------------------------------------------------------------------
    # Phase 6: jvd_sk から血統・産地情報取得
    # -------------------------------------------------------------------------
    logger.info("derived_factors: jvd_sk から血統・産地情報を取得します")
    extra_sk = _load_extra_from_sk(conn, df)
    if not extra_sk.empty:
        df = _safe_merge(df, extra_sk, on=["ketto_toroku_bango"])
    else:
        for col in ["chichi_name", "hahachichi_name", "sanchimei"]:
            df = _add_null_col(df, col, "jvd_sk 取得不可")

    # -------------------------------------------------------------------------
    # Phase 7: ランク・ビン計算（追加データロード後）
    # -------------------------------------------------------------------------
    df["idm_rank"] = _compute_idm_rank(df)
    df["kijun_odds_bin5"] = _bin_kijun_odds_5(df)
    df["ls_shisu_bin4"] = _bin_ls_shisu_4(df)

    logger.info("derived_factors: 調教師ランクを計算します（2025年通算）")
    trainer_rank_map = _compute_trainer_rank(conn)
    chokyoshi_col = "chokyoshi_code_kyi" if "chokyoshi_code_kyi" in df.columns else "chokyoshi_code"
    if chokyoshi_col in df.columns:
        df["chokyoshi_rank"] = df[chokyoshi_col].astype(str).str.strip().map(trainer_rank_map)
    else:
        df = _add_null_col(df, "chokyoshi_rank", "chokyoshi_code が存在しない")

    logger.info("derived_factors: 騎手ランクを計算します（2025年通算）")
    jockey_rank_map = _compute_jockey_rank(conn)
    kishu_col = "kishu_code_kyi" if "kishu_code_kyi" in df.columns else "kishu_code"
    if kishu_col in df.columns:
        df["kishu_rank"] = df[kishu_col].astype(str).str.strip().map(jockey_rank_map)
    else:
        df = _add_null_col(df, "kishu_rank", "kishu_code が存在しない")

    # -------------------------------------------------------------------------
    # Phase 8: スキーマ未存在カラムを NULL で追加
    # -------------------------------------------------------------------------
    df = _add_null_col(df, "prev_rpci", "ACTUAL_DB_SCHEMA に rpci カラムが存在しない")

    # -------------------------------------------------------------------------
    # Phase 8.5: 休養週数（kyuyou_weeks）
    # race_date_prev1 は prev_race_loader が _PREV_COLS に race_date を追加後に取得
    # -------------------------------------------------------------------------
    df["kyuyou_weeks"] = _compute_kyuyou_weeks(df)

    # -------------------------------------------------------------------------
    # Phase 8.6: 前走 race_pace / kyakushitsu_sed（jrd_sed より取得）
    # -------------------------------------------------------------------------
    logger.info("derived_factors: jrd_sed から前走 race_pace / kyakushitsu_sed を取得します")
    sed_prev = _load_sed_prev(conn, df)
    if not sed_prev.empty:
        # umaban なしで ketto_toroku_bango + prev1 race キーでマージ
        df["_prev1_kaisai_nen"] = df["race_date_prev1"].astype(str).str[:4]
        df["_prev1_kaisai_tsukihi"] = df["race_date_prev1"].astype(str).str[4:]
        rbp = "race_bango_prev1"
        kbp = "keibajo_code_prev1"
        if rbp in df.columns and kbp in df.columns:
            df[rbp] = df[rbp].astype(str).str.strip()
            df[kbp] = df[kbp].astype(str).str.strip()
            df = _safe_merge(
                df,
                sed_prev[["ketto_toroku_bango", "keibajo_code_prev1",
                           "_prev1_kaisai_nen", "_prev1_kaisai_tsukihi",
                           "race_bango_prev1",
                           "prev1_race_pace", "prev1_kyakushitsu_sed"]],
                on=["ketto_toroku_bango", "keibajo_code_prev1",
                    "_prev1_kaisai_nen", "_prev1_kaisai_tsukihi", "race_bango_prev1"],
            )
        df.drop(columns=["_prev1_kaisai_nen", "_prev1_kaisai_tsukihi"],
                inplace=True, errors="ignore")
    else:
        df = _add_null_col(df, "prev1_race_pace", "jrd_sed 前走データ取得不可")
        df = _add_null_col(df, "prev1_kyakushitsu_sed", "jrd_sed 前走データ取得不可")

    logger.info("derived_factors: 全加工ファクター生成完了（行数: %d）", len(df))
    return df

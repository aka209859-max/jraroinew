#!/usr/bin/env python3
"""
factor_screening.py - Factor screening batch (single-factor + CEO combinations)

Usage:
  # Single-factor mode (50 factors)
  py -3.12 -m backend.batch.factor_screening [--limit ROWS] [--factors N]

  # CEO combination mode
  py -3.12 -m backend.batch.factor_screening --ceo-combos [--limit N_COMBOS] [--rows ROWS]
"""

import argparse
import math
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import psycopg2

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------
DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 5432,
    "database": "pckeiba",
    "user": "postgres",
    "password": "postgres123",
}

DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent.parent / "reports" / "screening"
YEAR_MIN = "2016"
YEAR_MAX = "2025"
NUM_BINS = 10
MIN_SAMPLES_PER_BIN = 30
MIN_TOTAL_SAMPLES = NUM_BINS * MIN_SAMPLES_PER_BIN
DEFAULT_CEO_ROWS = 0  # 0 = 無制限（全競馬場カバーのため）

# --------------------------------------------------------------------------
# Single-factor definitions (50 factors)
# --------------------------------------------------------------------------
NUMERIC_FACTORS: List[Tuple[str, str]] = [
    ("idm",                           "IDM指数"),
    ("sogo_shisu",                    "総合指数"),
    ("ten_shisu",                     "テン指数"),
    ("pace_shisu",                    "ペース指数"),
    ("agari_shisu",                   "上がり指数"),
    ("ichi_shisu",                    "位置指数"),
    ("gekiso_shisu",                  "激走指数"),
    ("ninki_shisu",                   "人気指数"),
    ("joho_shisu",                    "情報指数"),
    ("manken_shisu",                  "万券指数"),
    ("kishu_shisu",                   "騎手指数"),
    ("chokyo_shisu",                  "調教指数"),
    ("kyusha_shisu",                  "厩舎指数"),
    ("ls_shisu_juni",                 "LS指数順位"),
    ("ten_shisu_juni",                "テン指数順位"),
    ("pace_shisu_juni",               "ペース指数順位"),
    ("agari_shisu_juni",              "上がり指数順位"),
    ("ichi_shisu_juni",               "位置指数順位"),
    ("gekiso_juni",                   "激走順位"),
    ("kishu_kitai_rentai_ritsu",      "騎手期待連対率"),
    ("kishu_kitai_tansho_ritsu",      "騎手期待単勝率"),
    ("kishu_kitai_sanchakunai_ritsu", "騎手期待3着内率"),
    ("uma_start_shisu",               "馬スタート指数"),
    ("uma_deokure_ritsu",             "馬出遅率"),
    ("rotation",                      "ローテーション"),
    ("bataiju",                       "馬体重"),
    ("bataiju_zogen",                 "馬体重増減"),
    ("kakutoku_shokin_ruikei",        "獲得賞金累計"),
    ("nyukyu_nannichimae",            "入厩何日前"),
    ("kijun_ninkijun_tansho",         "基準人気順単勝"),
]

CODE_FACTORS: List[Tuple[str, str]] = [
    ("keibajo_code",              "競馬場"),
    ("kyakushitsu",               "脚質"),
    ("class_code",                "クラスコード"),
    ("joshodo_code",              "上昇度"),
    ("hizume_code",               "蹄コード"),
    ("blinker",                   "ブリンカー"),
    ("pace_yoso",                 "ペース予想"),
    ("kishu_minarai_code",        "騎手見習"),
    ("kyori_tekisei",             "距離適性"),
    ("kyori_tekisei_2",           "距離適性2"),
    ("shiba_tekisei_code",        "芝適性"),
    ("da_tekisei_code",           "ダ適性"),
    ("omo_tekisei_code",          "重適性"),
    ("tenkai_kigo_code",          "展開記号"),
    ("manken_shirushi",           "万券印"),
    ("kokyu_flag",                "コ休フラグ"),
    ("kyuyo_riyu_bunrui_code",    "休養理由"),
    ("kyusha_hyoka_code",         "厩舎評価"),
    ("umakigo_code",              "馬記号"),
    ("joken_class_code",          "条件クラス"),
]

ALL_FACTORS: List[Tuple[str, str, str]] = (
    [(c, lbl, "numeric") for c, lbl in NUMERIC_FACTORS] +
    [(c, lbl, "code") for c, lbl in CODE_FACTORS]
)

# --------------------------------------------------------------------------
# CEO combination definitions
# --------------------------------------------------------------------------
CEO_COMBINATIONS: List[Dict] = [
    # COURSE_27 segment
    {"segment": "COURSE_27", "factors": ["prev1_chakujun"]},
    {"segment": "COURSE_27", "factors": ["prev2_chakujun"]},
    {"segment": "COURSE_27", "factors": ["prev3_chakujun"]},
    {"segment": "COURSE_27", "factors": ["prev1_corner4"]},
    {"segment": "COURSE_27", "factors": ["prev1_blinker", "blinker"]},
    {"segment": "COURSE_27", "factors": ["prev1_bataiju_bin"]},
    {"segment": "COURSE_27", "factors": ["kyori_change"]},
    {"segment": "COURSE_27", "factors": ["bamei_hahachichi"]},
    {"segment": "COURSE_27", "factors": ["bamei_chichi"]},
    {"segment": "COURSE_27", "factors": ["taikei_dou"]},
    {"segment": "COURSE_27", "factors": ["chokyoshi_rank"]},
    {"segment": "COURSE_27", "factors": ["kishu_rank"]},
    {"segment": "COURSE_27", "factors": ["tozai_shozoku_code"]},
    # SURFACE_2 segment
    {"segment": "SURFACE_2", "factors": ["idm"]},
    {"segment": "SURFACE_2", "factors": ["sogo_shisu"]},
    {"segment": "SURFACE_2", "factors": ["gekiso_shisu"]},
    {"segment": "SURFACE_2", "factors": ["kyusha_shisu"]},
    {"segment": "SURFACE_2", "factors": ["kishu_shisu"]},
    {"segment": "SURFACE_2", "factors": ["chokyo_shisu"]},
    {"segment": "SURFACE_2", "factors": ["manken_shisu"]},
    {"segment": "SURFACE_2", "factors": ["hizume_code"]},
    {"segment": "SURFACE_2", "factors": ["prev1_kyakushitsu", "kyakushitsu"]},
    {"segment": "SURFACE_2", "factors": ["sanchimei"]},
    {"segment": "SURFACE_2", "factors": ["babajotai_heavy", "kishumei"]},
    {"segment": "SURFACE_2", "factors": ["babajotai_heavy", "bamei_chichi"]},
    {"segment": "SURFACE_2", "factors": ["kishumei", "wakuban"]},
    {"segment": "SURFACE_2", "factors": ["prev1_keibajo", "keibajo_code"]},
    {"segment": "SURFACE_2", "factors": ["kyori_kubun", "taikei_tomo"]},
    {"segment": "SURFACE_2", "factors": ["pace_yoso", "prev1_corner4_bin", "barei"]},
    # GLOBAL segment
    {"segment": "GLOBAL", "factors": ["chokyoshi_rank"]},
    {"segment": "GLOBAL", "factors": ["kishu_rank"]},
    {"segment": "GLOBAL", "factors": ["futan_juryo", "pace_yoso"]},
    {"segment": "GLOBAL", "factors": ["chokyo_yajirushi_code"]},
    {"segment": "GLOBAL", "factors": ["yuso_kubun", "chokyoshimei"]},
    # COURSE_27 extra
    {"segment": "COURSE_27", "factors": ["umaban"]},
    {"segment": "COURSE_27", "factors": ["wakuban"]},
    {"segment": "COURSE_27", "factors": ["bataiju_change_bin"]},
]

# --------------------------------------------------------------------------
# SQL: extended query (CEO mode adds jvd_ra, extra jvd_se columns)
# --------------------------------------------------------------------------
_LOAD_QUERY = """
SELECT
    k.keibajo_code, k.race_shikonen, k.kaisai_kai, k.kaisai_nichime,
    k.race_bango, k.umaban,
    v.kaisai_nen, v.kaisai_tsukihi,
    k.kettou_toroku_bango,
    k.jrdb_race_key8,
    v.ketto_toroku_bango AS jvd_ketto_toroku_bango,
    CAST(k.race_shikonen AS INTEGER) AS yy_int,
    -- numeric factors
    k.idm, k.sogo_shisu, k.ten_shisu, k.pace_shisu, k.agari_shisu,
    k.ichi_shisu, k.gekiso_shisu, k.ninki_shisu, k.joho_shisu,
    k.manken_shisu, k.kishu_shisu, k.chokyo_shisu, k.kyusha_shisu,
    k.ls_shisu_juni, k.ten_shisu_juni, k.pace_shisu_juni,
    k.agari_shisu_juni, k.ichi_shisu_juni, k.gekiso_juni,
    k.kishu_kitai_rentai_ritsu, k.kishu_kitai_tansho_ritsu,
    k.kishu_kitai_sanchakunai_ritsu,
    k.uma_start_shisu, k.uma_deokure_ritsu, k.rotation,
    k.bataiju, k.bataiju_zogen, k.kakutoku_shokin_ruikei,
    k.nyukyu_nannichimae, k.kijun_ninkijun_tansho,
    -- code factors
    k.kyakushitsu, k.class_code, k.joshodo_code, k.hizume_code,
    k.blinker, k.pace_yoso, k.kishu_minarai_code,
    k.kyori_tekisei, k.kyori_tekisei_2,
    k.shiba_tekisei_code, k.da_tekisei_code, k.omo_tekisei_code,
    k.tenkai_kigo_code, k.manken_shirushi, k.kokyu_flag,
    k.kyuyo_riyu_bunrui_code, k.kyusha_hyoka_code,
    k.umakigo_code, k.joken_class_code, k.yuso_kubun,
    -- CEO extra from jrd_kyi_fixed
    k.taikei, k.kishumei, k.chokyoshimei, k.chokyo_yajirushi_code,
    k.kishu_code, k.chokyoshi_code,
    -- CEO extra from jvd_se
    v.tozai_shozoku_code,
    v.wakuban AS wakuban_v,
    CAST(NULLIF(TRIM(v.barei), '') AS INTEGER) AS barei,
    CAST(NULLIF(TRIM(v.futan_juryo), '') AS NUMERIC) AS futan_juryo_raw,
    NULLIF(TRIM(v.bataiju), '') AS bataiju_actual,
    v.zogen_fugo,
    NULLIF(TRIM(v.zogen_sa), '') AS zogen_sa,
    NULLIF(TRIM(v.tansho_odds), '') AS tansho_odds,
    -- Extra kyi_fixed columns (full-scan)
    k.seibetsu_code, k.soho,
    k.kijun_odds_tansho, k.kijun_ninkijun_fukusho, k.kijun_odds_fukusho,
    k.shirushi_code_1, k.shirushi_code_2, k.shirushi_code_3,
    k.shirushi_code_4, k.shirushi_code_5, k.shirushi_code_6, k.shirushi_code_7,
    k.dochu_juni, k.dochu_sa, k.kohan_3f_juni, k.kohan_3f_sa,
    k.goal_juni, k.goal_sa, k.hobokusaki_rank,
    k.taikei_sogo_1, k.taikei_sogo_2, k.taikei_sogo_3,
    k.uma_tokki_1, k.uma_tokki_2, k.uma_tokki_3,
    k.gekiso_type, k.kyusha_rank AS kyi_kyusha_rank,
    k.chokyoshi_shozoku, k.shutoku_shokin_ruikei,
    -- Extra jvd_se columns (full-scan)
    v.hinshu_code, v.moshoku_code, v.mining_kubun, v.blinker_shiyo_kubun,
    NULLIF(TRIM(v.yoso_juni), '') AS yoso_juni,
    -- race info from jvd_ra
    CAST(NULLIF(TRIM(r.kyori), '') AS INTEGER) AS kyori,
    NULLIF(TRIM(r.track_code), '') AS track_code,
    NULLIF(TRIM(r.babajotai_code_shiba), '') AS babajotai_code_shiba,
    NULLIF(TRIM(r.babajotai_code_dirt), '') AS babajotai_code_dirt,
    NULLIF(TRIM(r.tenko_code), '') AS tenko_code,
    -- result
    v.kakutei_chakujun,
    CASE
        WHEN h.haraimodoshi_tansho_1a IS NOT NULL
             AND v.umaban = h.haraimodoshi_tansho_1a
             AND NULLIF(TRIM(h.haraimodoshi_tansho_1b), '') IS NOT NULL
        THEN CAST(TRIM(h.haraimodoshi_tansho_1b) AS INTEGER)
        ELSE 0
    END AS haraimodoshi_tansho,
    CASE
        WHEN h.haraimodoshi_fukusho_1a IS NOT NULL
             AND v.umaban = h.haraimodoshi_fukusho_1a
             AND NULLIF(TRIM(h.haraimodoshi_fukusho_1b), '') IS NOT NULL
        THEN CAST(TRIM(h.haraimodoshi_fukusho_1b) AS INTEGER)
        WHEN h.haraimodoshi_fukusho_2a IS NOT NULL
             AND v.umaban = h.haraimodoshi_fukusho_2a
             AND NULLIF(TRIM(h.haraimodoshi_fukusho_2b), '') IS NOT NULL
        THEN CAST(TRIM(h.haraimodoshi_fukusho_2b) AS INTEGER)
        WHEN h.haraimodoshi_fukusho_3a IS NOT NULL
             AND v.umaban = h.haraimodoshi_fukusho_3a
             AND NULLIF(TRIM(h.haraimodoshi_fukusho_3b), '') IS NOT NULL
        THEN CAST(TRIM(h.haraimodoshi_fukusho_3b) AS INTEGER)
        ELSE 0
    END AS haraimodoshi_fukusho
FROM jrd_kyi_fixed k
JOIN jvd_se v ON
    v.keibajo_code = k.keibajo_code
    AND SUBSTRING(v.kaisai_nen, 3, 2) = k.race_shikonen
    AND LTRIM(v.kaisai_kai, '0') = k.kaisai_kai
    AND LTRIM(v.kaisai_nichime, '0') = k.kaisai_nichime
    AND v.race_bango = k.race_bango
    AND v.umaban = k.umaban
LEFT JOIN jvd_hr h ON
    v.kaisai_nen = h.kaisai_nen
    AND v.kaisai_tsukihi = h.kaisai_tsukihi
    AND v.keibajo_code = h.keibajo_code
    AND v.kaisai_kai = h.kaisai_kai
    AND v.kaisai_nichime = h.kaisai_nichime
    AND v.race_bango = h.race_bango
LEFT JOIN jvd_ra r ON
    v.kaisai_nen = r.kaisai_nen
    AND v.kaisai_tsukihi = r.kaisai_tsukihi
    AND v.keibajo_code = r.keibajo_code
    AND v.kaisai_kai = r.kaisai_kai
    AND v.kaisai_nichime = r.kaisai_nichime
    AND v.race_bango = r.race_bango
WHERE v.kaisai_nen >= '{year_min}'
  AND v.kaisai_nen <= '{year_max}'
  AND v.ijo_kubun_code = '0'
  AND v.kakutei_chakujun IS NOT NULL
  AND v.kakutei_chakujun NOT IN ('00', '')
{limit_clause}
"""

# Previous race data via LAG window on jvd_se
# Restricted to JRA venues (keibajo_code '01'-'10') so prev keibajo matches main_df
_PREV_QUERY = """
WITH all_jra AS (
    SELECT
        ketto_toroku_bango,
        kaisai_nen, kaisai_tsukihi, race_bango,
        keibajo_code,
        kakutei_chakujun,
        NULLIF(TRIM(corner_4), '')      AS corner_4_clean,
        NULLIF(TRIM(bataiju), '')       AS bataiju_clean,
        kyakushitsu_hantei,
        blinker_shiyo_kubun
    FROM jvd_se
    WHERE ijo_kubun_code = '0'
      AND kakutei_chakujun NOT IN ('00', '')
      AND kaisai_nen >= '2013'
      AND TRIM(ketto_toroku_bango) NOT IN ('', '0000000000')
),
ranked AS (
    SELECT
        ketto_toroku_bango,
        kaisai_nen, kaisai_tsukihi, race_bango,
        keibajo_code,
        LAG(kakutei_chakujun, 1) OVER w AS prev1_chakujun,
        LAG(kakutei_chakujun, 2) OVER w AS prev2_chakujun,
        LAG(kakutei_chakujun, 3) OVER w AS prev3_chakujun,
        LAG(corner_4_clean,     1) OVER w AS prev1_corner4,
        LAG(bataiju_clean,      1) OVER w AS prev1_bataiju,
        LAG(kyakushitsu_hantei, 1) OVER w AS prev1_kyakushitsu,
        LAG(keibajo_code,       1) OVER w AS prev1_keibajo,
        LAG(blinker_shiyo_kubun,1) OVER w AS prev1_blinker
    FROM all_jra
    WINDOW w AS (
        PARTITION BY ketto_toroku_bango
        ORDER BY kaisai_nen, kaisai_tsukihi, race_bango
    )
)
SELECT * FROM ranked
WHERE kaisai_nen >= '2016'
  AND keibajo_code BETWEEN '01' AND '10'
"""

# Bloodline data from jrd_ukc
_BLOOD_QUERY = """
SELECT
    ketto_toroku_bango,
    TRIM(bamei_chichi)   AS bamei_chichi,
    TRIM(bamei_hahachichi) AS bamei_hahachichi,
    TRIM(sanchimei)      AS sanchimei
FROM jrd_ukc
WHERE bamei_chichi IS NOT NULL
"""


# --------------------------------------------------------------------------
# Data loading
# --------------------------------------------------------------------------
def _get_conn() -> psycopg2.extensions.connection:
    return psycopg2.connect(**DB_CONFIG)


def load_data(limit: Optional[int] = None) -> pd.DataFrame:
    limit_sql = f"LIMIT {int(limit)}" if limit else ""
    query = _LOAD_QUERY.format(
        year_min=YEAR_MIN, year_max=YEAR_MAX, limit_clause=limit_sql
    )
    conn = _get_conn()
    try:
        return pd.read_sql(query, conn)
    finally:
        conn.close()


def load_prev_data() -> pd.DataFrame:
    """Load previous race data (all JRA venues, 2016-present)."""
    conn = _get_conn()
    try:
        return pd.read_sql(_PREV_QUERY, conn)
    finally:
        conn.close()


def load_blood_data() -> pd.DataFrame:
    conn = _get_conn()
    try:
        return pd.read_sql(_BLOOD_QUERY, conn)
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Preprocessing (single-factor mode)
# --------------------------------------------------------------------------
def preprocess(df: pd.DataFrame) -> pd.DataFrame:
    df["year_weight"] = (df["yy_int"] - 15).clip(lower=1, upper=10)
    for col, _, ftype in ALL_FACTORS:
        if col not in df.columns:
            continue
        raw = df[col].astype(str).str.strip()
        if ftype == "numeric":
            df[col] = pd.to_numeric(
                raw.replace({"": None, "nan": None}), errors="coerce"
            )
        else:
            df[col] = raw.replace({"": None, "nan": None, "None": None})
    return df


# --------------------------------------------------------------------------
# Derived factor computation (CEO mode)
# --------------------------------------------------------------------------
def _surface(track_code) -> Optional[str]:
    try:
        n = int(str(track_code).strip())
    except (ValueError, TypeError):
        return None
    if 10 <= n <= 19:
        return "芝"
    if 20 <= n <= 29:
        return "ダ"
    if n >= 50:
        return "障"
    return None


def _kyori_kubun(kyori) -> Optional[str]:
    try:
        k = int(kyori)
    except (ValueError, TypeError):
        return None
    if k < 1400:
        return "短距離"
    if k < 1700:
        return "マイル"
    if k < 2100:
        return "中距離"
    return "長距離"


# ---------------------------------------------------------------------------
# COURSE_27 正式マッピング
# コースの形状・傾斜・回り方に基づく27分類
# (keibajo_code文字列, surface文字列, kyori整数) -> course_type文字列
# ---------------------------------------------------------------------------
_COURSE_27_MAP: dict = {
    # ===== 芝 =====
    # 右回り急坂U字コース: 中山・阪神
    ("06", "芝", 1200): "右回り急坂U字_芝",
    ("09", "芝", 1200): "右回り急坂U字_芝",
    ("09", "芝", 1400): "右回り急坂U字_芝",
    ("09", "芝", 1600): "右回り急坂U字_芝",   # 阪神1600外
    ("09", "芝", 1800): "右回り急坂U字_芝",   # 阪神1800外
    # 右回り急坂O字コース: 中山・阪神
    ("06", "芝", 1800): "右回り急坂O字_芝",
    ("06", "芝", 2000): "右回り急坂O字_芝",
    ("06", "芝", 2200): "右回り急坂O字_芝",
    ("06", "芝", 2500): "右回り急坂O字_芝",
    ("06", "芝", 3600): "右回り急坂O字_芝",
    ("09", "芝", 2000): "右回り急坂O字_芝",
    ("09", "芝", 2200): "右回り急坂O字_芝",
    ("09", "芝", 2400): "右回り急坂O字_芝",   # 阪神2400外
    ("09", "芝", 2600): "右回り急坂O字_芝",   # 阪神2600外
    ("09", "芝", 3000): "右回り急坂O字_芝",
    # 特殊Aコース: 中山芝1600
    ("06", "芝", 1600): "特殊A_芝",
    # 東京U字コース
    ("05", "芝", 1400): "東京U字_芝",
    ("05", "芝", 1600): "東京U字_芝",
    ("05", "芝", 1800): "東京U字_芝",
    ("05", "芝", 2000): "東京U字_芝",
    # 東京O字コース
    ("05", "芝", 2300): "東京O字_芝",
    ("05", "芝", 2400): "東京O字_芝",
    ("05", "芝", 2500): "東京O字_芝",
    ("05", "芝", 3400): "東京O字_芝",
    # 右回り平坦U字コース: 京都・福島・小倉
    ("08", "芝", 1200): "右回り平坦U字_芝",
    ("08", "芝", 1400): "右回り平坦U字_芝",   # 内・外両方
    ("08", "芝", 1600): "右回り平坦U字_芝",   # 内・外両方
    ("08", "芝", 1800): "右回り平坦U字_芝",   # 外
    ("03", "芝", 1200): "右回り平坦U字_芝",
    ("10", "芝", 1200): "右回り平坦U字_芝",
    # 右回り平坦O字コース: 京都・福島・小倉
    ("08", "芝", 2000): "右回り平坦O字_芝",
    ("08", "芝", 2200): "右回り平坦O字_芝",   # 外
    ("08", "芝", 2400): "右回り平坦O字_芝",   # 外
    ("08", "芝", 3000): "右回り平坦O字_芝",   # 外
    ("08", "芝", 3200): "右回り平坦O字_芝",   # 外
    ("03", "芝", 1800): "右回り平坦O字_芝",
    ("03", "芝", 2000): "右回り平坦O字_芝",
    ("03", "芝", 2600): "右回り平坦O字_芝",
    ("10", "芝", 1700): "右回り平坦O字_芝",
    ("10", "芝", 1800): "右回り平坦O字_芝",
    ("10", "芝", 2000): "右回り平坦O字_芝",
    ("10", "芝", 2600): "右回り平坦O字_芝",
    # 左回り平坦U字コース: 新潟（外回り）
    ("04", "芝", 1200): "左回り平坦U字_芝",
    ("04", "芝", 1400): "左回り平坦U字_芝",
    ("04", "芝", 1600): "左回り平坦U字_芝",   # 外
    # 左回り平坦O字コース: 新潟（内回り）
    ("04", "芝", 1800): "左回り平坦O字_芝",   # 外
    ("04", "芝", 2000): "左回り平坦O字_芝",
    ("04", "芝", 2200): "左回り平坦O字_芝",
    ("04", "芝", 2400): "左回り平坦O字_芝",
    # 直線コース: 新潟芝1000
    ("04", "芝", 1000): "直線_芝",
    # 左回り急坂U字コース: 中京
    ("07", "芝", 1200): "左回り急坂U字_芝",
    ("07", "芝", 1400): "左回り急坂U字_芝",
    ("07", "芝", 1600): "左回り急坂U字_芝",
    # 左回り急坂O字コース: 中京
    ("07", "芝", 2000): "左回り急坂O字_芝",
    ("07", "芝", 2200): "左回り急坂O字_芝",
    # 北海道U字コース: 札幌・函館
    ("01", "芝", 1200): "北海道U字_芝",
    ("02", "芝", 1000): "北海道U字_芝",
    ("02", "芝", 1200): "北海道U字_芝",
    # 北海道O字コース: 札幌・函館
    ("01", "芝", 1800): "北海道O字_芝",
    ("01", "芝", 2000): "北海道O字_芝",
    ("01", "芝", 2600): "北海道O字_芝",
    ("02", "芝", 1800): "北海道O字_芝",
    ("02", "芝", 2000): "北海道O字_芝",
    ("02", "芝", 2600): "北海道O字_芝",
    # 特殊Bコース: 札幌芝1500
    ("01", "芝", 1500): "特殊B_芝",

    # ===== ダート =====
    # 右回り急坂U字コース: 中山・阪神
    ("06", "ダ", 1200): "右回り急坂U字_ダ",
    ("09", "ダ", 1200): "右回り急坂U字_ダ",
    ("09", "ダ", 1400): "右回り急坂U字_ダ",
    # 右回り急坂O字コース: 中山・阪神
    ("06", "ダ", 1800): "右回り急坂O字_ダ",
    ("06", "ダ", 2400): "右回り急坂O字_ダ",
    ("06", "ダ", 2500): "右回り急坂O字_ダ",
    ("09", "ダ", 1800): "右回り急坂O字_ダ",
    ("09", "ダ", 2000): "右回り急坂O字_ダ",
    # 東京U字コース: ダート
    ("05", "ダ", 1300): "東京U字_ダ",
    ("05", "ダ", 1400): "東京U字_ダ",
    ("05", "ダ", 1600): "東京U字_ダ",
    # 東京O字コース: ダート
    ("05", "ダ", 2100): "東京O字_ダ",
    ("05", "ダ", 2400): "東京O字_ダ",
    # 右回り平坦U字コース: 京都・福島・小倉
    ("08", "ダ", 1200): "右回り平坦U字_ダ",
    ("08", "ダ", 1400): "右回り平坦U字_ダ",
    ("03", "ダ", 1150): "右回り平坦U字_ダ",
    ("10", "ダ", 1000): "右回り平坦U字_ダ",
    # 右回り平坦O字コース: 京都・福島・小倉
    ("08", "ダ", 1800): "右回り平坦O字_ダ",
    ("08", "ダ", 1900): "右回り平坦O字_ダ",   # 京都ダ1900m
    ("03", "ダ", 1700): "右回り平坦O字_ダ",
    ("03", "ダ", 2400): "右回り平坦O字_ダ",
    ("10", "ダ", 1700): "右回り平坦O字_ダ",
    ("10", "ダ", 2400): "右回り平坦O字_ダ",
    # 左回り平坦U字コース: 新潟
    ("04", "ダ", 1200): "左回り平坦U字_ダ",
    # 左回り平坦O字コース: 新潟
    ("04", "ダ", 1800): "左回り平坦O字_ダ",
    ("04", "ダ", 2500): "左回り平坦O字_ダ",
    # 左回り急坂U字コース: 中京
    ("07", "ダ", 1200): "左回り急坂U字_ダ",
    ("07", "ダ", 1400): "左回り急坂U字_ダ",
    # 左回り急坂O字コース: 中京
    ("07", "ダ", 1800): "左回り急坂O字_ダ",
    ("07", "ダ", 1900): "左回り急坂O字_ダ",
    # 北海道U字コース: 札幌・函館
    ("01", "ダ", 1000): "北海道U字_ダ",
    ("02", "ダ", 1000): "北海道U字_ダ",
    # 北海道O字コース: 札幌・函館
    ("01", "ダ", 1700): "北海道O字_ダ",
    ("01", "ダ", 2400): "北海道O字_ダ",
    ("02", "ダ", 1700): "北海道O字_ダ",
    ("02", "ダ", 2400): "北海道O字_ダ",
}


def _course_27(keibajo: str, surface: Optional[str], kyori) -> Optional[str]:
    """正式COURSE_27分類: コース形状・傾斜・回り方に基づく27カテゴリ"""
    if surface not in ("芝", "ダ"):
        return None
    try:
        k = int(kyori)
    except (ValueError, TypeError):
        return None
    kb = str(keibajo).strip().zfill(2)
    return _COURSE_27_MAP.get((kb, surface, k))  # None = マップ外コース


def _taikei_part(taikei, pos: int) -> Optional[str]:
    """Extract 3-char part from 24-char taikei field (0-indexed part)"""
    if not taikei or pd.isna(taikei):
        return None
    s = str(taikei)
    start = pos * 3
    if len(s) < start + 3:
        return None
    val = s[start:start + 3].strip()
    return val if val else None


def _babajotai_heavy(code) -> Optional[str]:
    """Convert babajotai_code to heavy/normal/良 grouping"""
    if not code or pd.isna(code):
        return None
    v = str(code).strip()
    if v == "1":
        return "良"
    if v == "2":
        return "稍重"
    if v in ("3", "4"):
        return "重以上"
    return None


def _rank_by_winrate(series: pd.Series, wins: pd.Series, total: pd.Series) -> pd.Series:
    """Map series values to S/A/B/C/D rank based on win rate quintiles"""
    stats = pd.DataFrame({"wins": wins, "total": total})
    stats = stats[stats["total"] >= 10].copy()
    stats["win_rate"] = stats["wins"] / stats["total"]
    q = stats["win_rate"].quantile([0.2, 0.4, 0.6, 0.8])

    def to_rank(code):
        if code not in stats.index:
            return None
        wr = stats.loc[code, "win_rate"]
        if wr >= q[0.8]:
            return "S"
        if wr >= q[0.6]:
            return "A"
        if wr >= q[0.4]:
            return "B"
        if wr >= q[0.2]:
            return "C"
        return "D"

    return series.map(to_rank)


def compute_derived_factors(
    df: pd.DataFrame,
    prev_df: Optional[pd.DataFrame],
    blood_df: Optional[pd.DataFrame],
) -> pd.DataFrame:
    df = df.copy()

    # surface / kyori_kubun / course_27
    df["surface"] = df["track_code"].apply(_surface)
    df["kyori_kubun"] = df["kyori"].apply(_kyori_kubun)
    # COURSE_27: コース形状・傾斜・回り方に基づく正式27分類
    df["course_27"] = df.apply(
        lambda r: _course_27(r["keibajo_code"], r["surface"], r["kyori"]),
        axis=1,
    )

    # babajotai_heavy (use shiba field, fallback dirt)
    df["babajotai_heavy"] = df["babajotai_code_shiba"].apply(_babajotai_heavy)
    dirt_heavy = df["babajotai_code_dirt"].apply(_babajotai_heavy)
    df["babajotai_heavy"] = df["babajotai_heavy"].fillna(dirt_heavy)

    # futan_juryo in kg (raw is grams * 10)
    df["futan_juryo"] = pd.to_numeric(df["futan_juryo_raw"], errors="coerce") / 10.0

    # bataiju_actual as numeric
    df["bataiju_actual"] = pd.to_numeric(df["bataiju_actual"], errors="coerce")
    df["zogen_sa"] = pd.to_numeric(df["zogen_sa"], errors="coerce")

    # taikei decomposition (胴=pos0, トモ=pos3)
    df["taikei_dou"] = df["taikei"].apply(lambda x: _taikei_part(x, 0))
    df["taikei_tomo"] = df["taikei"].apply(lambda x: _taikei_part(x, 3))

    # wakuban (use jvd_se's wakuban_v)
    if "wakuban_v" in df.columns:
        df["wakuban"] = df["wakuban_v"].astype(str).str.strip()

    # umaban clean
    df["umaban_clean"] = df["umaban"].astype(str).str.strip()

    # kishu_rank / chokyoshi_rank from win rate on current data
    if "kishu_code" in df.columns:
        is_win = df["haraimodoshi_tansho"] > 0
        k_stats = df.groupby("kishu_code").agg(
            wins=("haraimodoshi_tansho", lambda x: (x > 0).sum()),
            total=("haraimodoshi_tansho", "count"),
        )
        df["kishu_rank"] = _rank_by_winrate(
            df["kishu_code"], k_stats["wins"], k_stats["total"]
        )

    if "chokyoshi_code" in df.columns:
        c_stats = df.groupby("chokyoshi_code").agg(
            wins=("haraimodoshi_tansho", lambda x: (x > 0).sum()),
            total=("haraimodoshi_tansho", "count"),
        )
        df["chokyoshi_rank"] = _rank_by_winrate(
            df["chokyoshi_code"], c_stats["wins"], c_stats["total"]
        )

    # Merge previous race data
    # NOTE: merge key uses keibajo_code + kaisai_nen + kaisai_tsukihi + race_bango
    # (not kaisai_kai/nichime, which differ in format between tables)
    if prev_df is not None and not prev_df.empty:
        prev_cols = [
            "ketto_toroku_bango", "keibajo_code", "kaisai_nen", "kaisai_tsukihi",
            "race_bango",
            "prev1_chakujun", "prev2_chakujun", "prev3_chakujun",
            "prev1_corner4", "prev1_bataiju", "prev1_kyakushitsu",
            "prev1_keibajo", "prev1_blinker",
        ]
        prev_sub = prev_df[[c for c in prev_cols if c in prev_df.columns]].copy()
        # Strip the ketto_toroku_bango to ensure clean match
        prev_sub["ketto_toroku_bango"] = prev_sub["ketto_toroku_bango"].astype(str).str.strip()
        # Use jvd_ketto_toroku_bango (10-char JV-Data format) to match prev_df
        df["_jvd_ketto"] = df["jvd_ketto_toroku_bango"].astype(str).str.strip()

        df = df.merge(
            prev_sub,
            left_on=["_jvd_ketto", "keibajo_code", "kaisai_nen",
                     "kaisai_tsukihi", "race_bango"],
            right_on=["ketto_toroku_bango", "keibajo_code", "kaisai_nen",
                      "kaisai_tsukihi", "race_bango"],
            how="left",
            suffixes=("", "_prev"),
        )
        df.drop(columns=["_jvd_ketto"], errors="ignore", inplace=True)

        # prev1_chakujun as numeric
        df["prev1_chakujun"] = pd.to_numeric(df.get("prev1_chakujun"), errors="coerce")
        df["prev2_chakujun"] = pd.to_numeric(df.get("prev2_chakujun"), errors="coerce")
        df["prev3_chakujun"] = pd.to_numeric(df.get("prev3_chakujun"), errors="coerce")

        # prev1_bataiju_bin (20kg buckets)
        prev_bataiju = pd.to_numeric(df.get("prev1_bataiju"), errors="coerce")
        df["prev1_bataiju_bin"] = (prev_bataiju // 20 * 20).astype("Int64").astype(str)
        df["prev1_bataiju_bin"] = df["prev1_bataiju_bin"].replace({"<NA>": None})

        # bataiju_change_bin: actual change from previous, binned ±10kg
        cur_bw = df["bataiju_actual"]
        df["bataiju_change_bin"] = (
            ((cur_bw - prev_bataiju) // 10 * 10)
            .astype("Int64").astype(str)
            .replace({"<NA>": None})
        )

        # prev1_corner4 as numeric bin (groups: 1-3, 4-6, 7-9, 10+)
        p_c4 = pd.to_numeric(
            df.get("prev1_corner4", pd.Series(dtype=str)).astype(str).str.strip(),
            errors="coerce",
        )

        def _c4_bin(v):
            if pd.isna(v):
                return None
            v = int(v)
            if v <= 3:
                return "1-3"
            if v <= 6:
                return "4-6"
            if v <= 9:
                return "7-9"
            return "10+"

        df["prev1_corner4_bin"] = p_c4.apply(_c4_bin)

        # kyori_change (increase/decrease/same vs previous race)
        # Need prev1 kyori - not available directly in prev_df (no race info)
        # Approximation: leave as None if prev kyori not available
        df["kyori_change"] = None  # placeholder

    # Merge bloodline data
    if blood_df is not None and not blood_df.empty:
        df = df.merge(
            blood_df,
            left_on="kettou_toroku_bango",
            right_on="ketto_toroku_bango",
            how="left",
            suffixes=("", "_blood"),
        )

    return df


# --------------------------------------------------------------------------
# Bin statistics
# --------------------------------------------------------------------------
def _bin_stats(grp: pd.DataFrame) -> Dict:
    n = len(grp)
    w = grp["year_weight"]
    w_sum = float(w.sum())
    win_count = int((grp["haraimodoshi_tansho"] > 0).sum())
    win_rate = round(win_count / n * 100, 1) if n > 0 else 0.0
    win_roi = (
        float((grp["haraimodoshi_tansho"] * w).sum()) / (w_sum * 100) * 100
        if w_sum > 0 else 0.0
    )
    place_roi = (
        float((grp["haraimodoshi_fukusho"] * w).sum()) / (w_sum * 100) * 100
        if w_sum > 0 else 0.0
    )
    confidence = math.sqrt(n / (n + 400))
    return {
        "n": n,
        "win_count": win_count,
        "win_rate": win_rate,
        "win_roi": round(win_roi, 1),
        "place_roi": round(place_roi, 1),
        "confidence": round(confidence, 3),
    }


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------
def _score_std(win_rois: List[float]) -> float:
    return float(np.std([(r - 80.0) / 10.0 for r in win_rois]))


def _grade(score_std: float) -> str:
    if score_std >= 5.0:
        return "S"
    if score_std >= 3.0:
        return "A"
    if score_std >= 2.0:
        return "B"
    return "C"


def _mark(grade: str) -> str:
    return {"S": "★★★", "A": "★★", "B": "★", "C": ""}.get(grade, "")


# --------------------------------------------------------------------------
# Single-factor analysis
# --------------------------------------------------------------------------
def analyze_numeric(df: pd.DataFrame, col: str, label: str) -> Optional[Dict]:
    valid = df[df[col].notna()].copy()
    if len(valid) < MIN_TOTAL_SAMPLES:
        return None
    try:
        labels_arr, bin_edges = pd.qcut(
            valid[col], q=NUM_BINS, retbins=True, labels=False, duplicates="drop"
        )
    except Exception:
        return None
    valid = valid.copy()
    valid["_bin"] = labels_arr
    bins, win_rois = [], []
    for b in sorted(valid["_bin"].dropna().unique()):
        grp = valid[valid["_bin"] == b]
        if len(grp) < MIN_SAMPLES_PER_BIN:
            continue
        b = int(b)
        lo, hi = bin_edges[b], bin_edges[b + 1]
        stats = _bin_stats(grp)
        bins.append({"bin_label": f"{lo:.1f}~{hi:.1f}", **stats})
        win_rois.append(stats["win_roi"])
    if len(win_rois) < 3:
        return None
    ss = _score_std(win_rois)
    return {
        "factor": col, "label": label, "type": "numeric",
        "score_std": round(ss, 3), "grade": _grade(ss), "bins": bins,
    }


def analyze_code(df: pd.DataFrame, col: str, label: str) -> Optional[Dict]:
    valid = df[df[col].notna()].copy()
    if len(valid) < MIN_SAMPLES_PER_BIN:
        return None
    groups, win_rois = [], []
    for code, grp in valid.groupby(col, sort=True):
        if len(grp) < MIN_SAMPLES_PER_BIN:
            continue
        stats = _bin_stats(grp)
        groups.append({"bin_label": str(code), **stats})
        win_rois.append(stats["win_roi"])
    if len(win_rois) < 2:
        return None
    ss = _score_std(win_rois)
    return {
        "factor": col, "label": label, "type": "code",
        "score_std": round(ss, 3), "grade": _grade(ss), "bins": groups,
    }


# --------------------------------------------------------------------------
# CEO combination analysis
# --------------------------------------------------------------------------

# Factor families: pairs within the same family are skipped in Phase 2 cross.
# Lists of frozensets — each frozenset is one "family".
_FACTOR_FAMILIES: List[frozenset] = [
    frozenset({"uma_tokki_1", "uma_tokki_2", "uma_tokki_3"}),
    frozenset({"shirushi_code_1", "shirushi_code_2", "shirushi_code_3",
               "shirushi_code_4", "shirushi_code_5", "shirushi_code_6", "shirushi_code_7"}),
    frozenset({"taikei_sogo_1", "taikei_sogo_2", "taikei_sogo_3"}),
    frozenset({"kijun_odds_tansho", "kijun_ninkijun_tansho",
               "kijun_odds_fukusho", "kijun_ninkijun_fukusho"}),
    frozenset({"kijun_odds_tansho", "joa_odds_shisu"}),   # same concept, different tables
    frozenset({"prev1_bataiju", "prev1_bataiju_bin"}),     # raw + binned duplicate
    frozenset({"kishu_kitai_rentai_ritsu", "kishu_kitai_tansho_ritsu",
               "kishu_kitai_sanchakunai_ritsu"}),
    frozenset({"kakutoku_shokin_ruikei", "shutoku_shokin_ruikei"}),
]


def _same_family(c1: str, c2: str) -> bool:
    """Return True if c1 and c2 belong to the same factor family."""
    for fam in _FACTOR_FAMILIES:
        if c1 in fam and c2 in fam:
            return True
    return False


def _build_combo_col(df: pd.DataFrame, factors: List[str]) -> pd.Series:
    """Build composite key column vectorized (much faster than row-wise apply).

    Returns a Series of pipe-joined strings, with pd.NA where any factor is null.
    """
    null_mask = pd.Series(False, index=df.index)
    str_parts = []
    for f in factors:
        col = df[f]
        is_null = col.isna()
        if col.dtype == object:
            stripped = col.astype(str).str.strip()
            is_null = is_null | stripped.isin(["", "nan", "None", "NaN"])
        null_mask = null_mask | is_null
        str_parts.append(col.fillna("__NULL__").astype(str).str.strip())

    combo = str_parts[0]
    for p in str_parts[1:]:
        combo = combo + "|" + p
    # Null-out rows where any factor was missing
    combo = combo.where(~null_mask, other=None)
    return combo


def analyze_combination(
    df: pd.DataFrame,
    factors: List[str],
    segment: str,
    max_bins: Optional[int] = None,
) -> Optional[Dict]:
    """Analyze a factor combination on the given dataframe.

    Parameters
    ----------
    df        : filtered dataframe (full or surface-filtered)
    factors   : list of column names forming the composite bin key
    segment   : segment label (e.g. "GLOBAL", "COURSE_27", "SURFACE_2_芝")
    max_bins  : skip if unique combo keys exceed this (None = no limit, default)
                Set to 1000 for Phase-2 auto-cross to avoid combinatorial explosion.
    """
    # Check all factor columns exist
    missing = [f for f in factors if f not in df.columns]
    if missing:
        return None

    # Build composite key (vectorized)
    combo_col = _build_combo_col(df, factors)
    valid_mask = combo_col.notna()
    total_samples = int(valid_mask.sum())
    if total_samples < MIN_SAMPLES_PER_BIN:
        return None

    # Guard: too many bins → skip (only when max_bins is set)
    if max_bins is not None:
        n_unique = combo_col[valid_mask].nunique()
        if n_unique > max_bins:
            return None

    # Attach to a view for groupby
    df2 = df.loc[valid_mask].copy()
    df2["_combo"] = combo_col[valid_mask]

    groups, win_rois, place_rois = [], [], []
    for combo_val, grp in df2.groupby("_combo", sort=True):
        if len(grp) < MIN_SAMPLES_PER_BIN:
            continue
        stats = _bin_stats(grp)
        groups.append({"bin_label": str(combo_val), **stats})
        win_rois.append(stats["win_roi"])
        place_rois.append(stats["place_roi"])

    if len(win_rois) < 2:
        return None

    ss = _score_std(win_rois)
    edge_bins = sum(1 for r in win_rois if r > 100)
    avg_win_roi = round(float(np.mean(win_rois)), 1)
    avg_place_roi = round(float(np.mean(place_rois)), 1)
    best_bin_win_roi = round(max(win_rois), 1)
    best_bin_place_roi = round(max(place_rois), 1)

    return {
        "segment": segment,
        "factors": factors,
        "factors_str": "+".join(factors),
        "score_std": round(ss, 3),
        "grade": _grade(ss),
        "mark": _mark(_grade(ss)),
        "n_bins": len(groups),
        "edge_bins": edge_bins,
        "total_samples": total_samples,
        "avg_win_roi": avg_win_roi,
        "avg_place_roi": avg_place_roi,
        "best_bin_win_roi": best_bin_win_roi,
        "best_bin_place_roi": best_bin_place_roi,
        "bins": groups,
    }


def run_ceo_screening(
    df: pd.DataFrame,
    combos: List[Dict],
) -> List[Dict]:
    """Run CEO combination screening.

    Segment semantics:
      GLOBAL    - all data, 1 result row
      COURSE_27 - all data (no per-course split), 1 result row
      SURFACE_2 - split by 芝/ダ, up to 2 result rows (SURFACE_2_芝 / SURFACE_2_ダ)
    """
    results = []

    for i, combo in enumerate(combos):
        segment = combo["segment"]
        factors = combo["factors"]
        factors_str = "+".join(factors)
        prefix = f"[{i+1}/{len(combos)}] [{segment}] {factors_str}"

        if segment in ("GLOBAL", "COURSE_27"):
            # Analyze all data — no sub-segmenting
            result = analyze_combination(df, factors, segment)
            if result is None:
                print(f"{prefix} ... SKIP")
            else:
                print(
                    f"{prefix} ... score_std={result['score_std']:.3f} "
                    f"{result['mark'] or result['grade']} "
                    f"best_win={result['best_bin_win_roi']:.1f}%"
                )
                results.append(result)

        elif segment == "SURFACE_2":
            for surf in ("芝", "ダ"):
                seg_name = f"SURFACE_2_{surf}"
                seg_df = df[df["surface"] == surf]
                if len(seg_df) < MIN_SAMPLES_PER_BIN:
                    continue
                result = analyze_combination(seg_df, factors, seg_name)
                if result is None:
                    print(f"{prefix} [{surf}] ... SKIP")
                else:
                    print(
                        f"{prefix} [{surf}] ... score_std={result['score_std']:.3f} "
                        f"{result['mark'] or result['grade']} "
                        f"best_win={result['best_bin_win_roi']:.1f}%"
                    )
                    results.append(result)

    return results


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------
def save_results(results: List[Dict], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    detail_dir = output_dir / "single_factor_detail"
    detail_dir.mkdir(parents=True, exist_ok=True)

    ranking = pd.DataFrame([
        {
            "rank": i + 1,
            "factor": r["factor"],
            "label": r["label"],
            "type": r["type"],
            "score_std": r["score_std"],
            "grade": r["grade"],
            "n_bins": len(r["bins"]),
        }
        for i, r in enumerate(sorted(results, key=lambda x: -x["score_std"]))
    ])
    rank_path = output_dir / "single_factor_ranking.csv"
    ranking.to_csv(rank_path, index=False, encoding="utf-8-sig")
    print(f"[OK] {rank_path}")

    for r in results:
        rows = [
            {
                "factor": r["factor"],
                "label": r["label"],
                "bin_label": b["bin_label"],
                "n": b["n"],
                "win_roi": b["win_roi"],
                "place_roi": b["place_roi"],
                "confidence": b["confidence"],
            }
            for b in r["bins"]
        ]
        pd.DataFrame(rows).to_csv(
            detail_dir / f"{r['factor']}.csv",
            index=False, encoding="utf-8-sig",
        )
    print(f"[OK] {detail_dir}/ ({len(results)} files)")


def save_ceo_results(results: List[Dict], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    detail_dir = output_dir / "ceo_combination_detail"
    detail_dir.mkdir(parents=True, exist_ok=True)

    sorted_results = sorted(results, key=lambda x: -x["score_std"])

    ranking_rows = []
    for i, r in enumerate(sorted_results):
        ranking_rows.append({
            "rank": i + 1,
            "segment": r["segment"],
            "factors": r["factors_str"],
            "grade": r["grade"],
            "mark": r["mark"],
            "score_std": r["score_std"],
            "n_bins": r["n_bins"],
            "edge_bins": r["edge_bins"],
            "avg_win_roi": r["avg_win_roi"],
            "avg_place_roi": r["avg_place_roi"],
            "best_bin_win_roi": r["best_bin_win_roi"],
            "best_bin_place_roi": r["best_bin_place_roi"],
            "total_samples": r["total_samples"],
        })

    rank_path = output_dir / "ceo_combination_ranking.csv"
    try:
        pd.DataFrame(ranking_rows).to_csv(rank_path, index=False, encoding="utf-8-sig")
        print(f"[OK] {rank_path}")
    except PermissionError:
        # File may be open in Excel — write to a timestamped backup
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        rank_path = output_dir / f"ceo_combination_ranking_{ts}.csv"
        pd.DataFrame(ranking_rows).to_csv(rank_path, index=False, encoding="utf-8-sig")
        print(f"[WARN] ranking.csv locked -- written to {rank_path}")

    # Detail per combination (filename: segment_factors)
    for r in sorted_results:
        fname = f"{r['segment']}_{r['factors_str']}".replace("/", "-")[:80]
        rows = [
            {
                "segment": r["segment"],
                "factors": r["factors_str"],
                "bin_label": b["bin_label"],
                "n": b["n"],
                "win_roi": b["win_roi"],
                "place_roi": b["place_roi"],
                "confidence": b["confidence"],
            }
            for b in r["bins"]
        ]
        pd.DataFrame(rows).to_csv(
            detail_dir / f"{fname}.csv",
            index=False, encoding="utf-8-sig",
        )

    print(f"[OK] {detail_dir}/ ({len(sorted_results)} files)")

    # Console TOP 20
    print("\n=== CEO COMBINATION RANKING TOP 20 ===")
    print(f"{'Rank':>4} {'Segment':<20} {'Factors':<35} {'Grade':>5} {'Score':>6} {'AvgWin%':>8} {'BestWin%':>9}")
    print("-" * 95)
    for row in ranking_rows[:20]:
        print(
            f"{row['rank']:>4} {row['segment'][:19]:<20} "
            f"{row['factors'][:34]:<35} {row['mark'] or row['grade']:>5} "
            f"{row['score_std']:>6.3f} {row['avg_win_roi']:>8.1f}% {row['best_bin_win_roi']:>9.1f}%"
        )


# --------------------------------------------------------------------------
# Full-scan SQL (jrd_joa_fixed, jrd_bac_fixed)
# --------------------------------------------------------------------------
_JOA_QUERY = """
SELECT
    jrdb_race_key8,
    umaban,
    NULLIF(TRIM(ls_shisu),   '') AS joa_ls_shisu,
    NULLIF(TRIM(ls_hyoka),   '') AS joa_ls_hyoka,
    NULLIF(TRIM(odds_shisu), '') AS joa_odds_shisu
FROM jrd_joa_fixed
"""

_BAC_QUERY = """
SELECT
    jrdb_race_key8,
    NULLIF(TRIM(shiba_da_shogai_code), '') AS bac_shiba_da,
    NULLIF(TRIM(migi_hidari),          '') AS bac_migi_hidari,
    NULLIF(TRIM(uchi_soto),            '') AS bac_uchi_soto,
    NULLIF(TRIM(shubetsu),             '') AS bac_shubetsu,
    NULLIF(TRIM(jouken),               '') AS bac_jouken,
    NULLIF(TRIM(juryo_shubetsu_code),  '') AS bac_juryo_shubetsu_code,
    NULLIF(TRIM(grade),                '') AS bac_grade,
    NULLIF(TRIM(tosu),                 '') AS bac_tosu,
    NULLIF(TRIM(course),               '') AS bac_course,
    NULLIF(TRIM(kaisai_kubun),         '') AS bac_kaisai_kubun
FROM jrd_bac_fixed
"""

# Columns always skipped in full-scan auto-discovery
_FS_SKIP_COLS: frozenset = frozenset({
    # Keys / IDs
    "jrdb_race_key8", "keibajo_code", "race_shikonen", "kaisai_kai",
    "kaisai_nichime", "kaisai_nen_2", "race_bango", "umaban",
    "basho_code", "year", "kai", "nichi", "race_num",
    "kettou_toroku_bango", "ketto_toroku_bango", "jvd_ketto_toroku_bango",
    "ketto_toroku_bango_prev",
    # Time / date
    "kaisai_nen", "kaisai_tsukihi", "nyukyu_nengappi",
    "data_sakusei_nengappi",
    # Free-text names
    "bamei", "kishumei", "chokyoshimei", "chokyoshimei_ryakusho",
    "kishumei_ryakusho", "kishumei_ryakusho_henkomae",
    "banushimei", "chokyoshi_shozoku", "hobokusaki",
    # Post-race results
    "kakutei_chakujun", "nyusen_juni",
    "haraimodoshi_tansho", "haraimodoshi_fukusho",
    "dochaku_kubun", "dochaku_tosu",
    # Raw / internal / derived
    "year_weight", "surface", "kyori_kubun", "course_27",
    "wakuban_v", "futan_juryo_raw", "bataiju_actual", "zogen_sa",
    "tansho_odds",      # used for odds-filter, not a predictor itself
    "jvd_ketto_toroku_bango",
    # Filler / system
    "yobi_1", "yobi_2", "yobi_3", "yobi_4", "yobi_5",
    "torikeshi_flag", "flag", "record_id", "data_kubun",
    # Past-race reference keys
    "kako1_race_key", "kako2_race_key", "kako3_race_key",
    "kako4_race_key", "kako5_race_key",
    "kako1_kyoso_seiseki_key", "kako2_kyoso_seiseki_key",
    "kako3_kyoso_seiseki_key", "kako4_kyoso_seiseki_key",
    "kako5_kyoso_seiseki_key",
    # Sanko / internal ref
    "sanko_zenso", "sanko_zenso_kishu_code", "nyukyu_nansome",
    # Code IDs handled separately (rank versions are already computed)
    "kishu_code", "chokyoshi_code",
    "banushi_code", "banushikai_code",
    "kishu_code_henkomae",
})

# Substring patterns → always skip
_FS_SKIP_PATTERNS: List[str] = [
    "_nengappi",
    "_bango",
    "henkomae",  # previous-jockey/trainer flags
]


# --------------------------------------------------------------------------
# Full-scan helpers
# --------------------------------------------------------------------------

def load_extra_tables_for_full_scan(main_df: pd.DataFrame) -> pd.DataFrame:
    """Merge jrd_joa_fixed and jrd_bac_fixed columns into main_df."""
    conn = _get_conn()
    try:
        joa_df = pd.read_sql(_JOA_QUERY, conn)
        bac_df = pd.read_sql(_BAC_QUERY, conn)
    finally:
        conn.close()

    print(f"[INFO] jrd_joa_fixed: {len(joa_df):,} rows, "
          f"jrd_bac_fixed: {len(bac_df):,} rows")

    # Ensure key columns are stripped strings
    for df_ in (joa_df, bac_df):
        df_["jrdb_race_key8"] = df_["jrdb_race_key8"].astype(str).str.strip()
    joa_df["umaban"] = joa_df["umaban"].astype(str).str.strip()

    if "jrdb_race_key8" not in main_df.columns:
        print("[WARN] jrdb_race_key8 not in main_df — skipping extra-table merge")
        return main_df

    main_df = main_df.copy()
    main_df["jrdb_race_key8"] = main_df["jrdb_race_key8"].astype(str).str.strip()
    main_df["umaban"] = main_df["umaban"].astype(str).str.strip()

    before = len(main_df)
    main_df = main_df.merge(joa_df, on=["jrdb_race_key8", "umaban"], how="left")
    main_df = main_df.merge(bac_df, on="jrdb_race_key8", how="left")
    assert len(main_df) == before, "Row count changed after extra-table merge!"
    return main_df


def detect_col_type(
    series: pd.Series,
    max_unique_code: int = 200,
    min_fill_ratio: float = 0.10,
) -> Optional[str]:
    """Return 'numeric', 'code', or None (skip this column)."""
    non_null = series.dropna()
    if len(non_null) == 0:
        return None
    if len(non_null) / len(series) < min_fill_ratio:
        return None  # too sparse

    cleaned = non_null.astype(str).str.strip().replace({"": None, "nan": None})
    cleaned = cleaned.dropna()
    if len(cleaned) == 0:
        return None

    numeric = pd.to_numeric(cleaned, errors="coerce")
    numeric_ratio = numeric.notna().sum() / len(cleaned)

    if numeric_ratio >= 0.80:
        if numeric.nunique() < 3:
            return None  # no real variation
        return "numeric"
    else:
        n_unique = cleaned.nunique()
        if n_unique > max_unique_code or n_unique < 2:
            return None
        return "code"


def get_scan_columns(df: pd.DataFrame) -> List[Tuple[str, str]]:
    """Return list of (col_name, col_type) for full-scan analysis."""
    cols = []
    for col in df.columns:
        if col in _FS_SKIP_COLS:
            continue
        if any(pat in col for pat in _FS_SKIP_PATTERNS):
            continue
        ctype = detect_col_type(df[col])
        if ctype is not None:
            cols.append((col, ctype))
    return cols


def _result_from_analyze(
    result: Optional[Dict],
    segment: str,
    col: str,
    col_type: str,
) -> Optional[Dict]:
    """Wrap the output of analyze_numeric/analyze_code into unified full-scan format."""
    if result is None:
        return None
    bins = result["bins"]
    win_rois = [b["win_roi"] for b in bins]
    place_rois = [b["place_roi"] for b in bins]
    return {
        "segment": segment,
        "factor": col,
        "factor_type": col_type,
        "factors_str": col,
        "score_std": result["score_std"],
        "grade": result["grade"],
        "mark": _mark(result["grade"]),
        "n_bins": len(bins),
        "edge_bins": sum(1 for r in win_rois if r > 100),
        "avg_win_roi": round(float(np.mean(win_rois)), 1),
        "avg_place_roi": round(float(np.mean(place_rois)), 1),
        "best_bin_win_roi": round(max(win_rois), 1),
        "best_bin_place_roi": round(max(place_rois), 1),
        "total_samples": len(df_[col].dropna()) if False else result.get("total_samples", 0),
        "bins": bins,
    }


def _analyze_on(df: pd.DataFrame, col: str, col_type: str) -> Optional[Dict]:
    """Run analyze_numeric or analyze_code and return result dict."""
    if col not in df.columns or len(df) < MIN_TOTAL_SAMPLES:
        return None
    # Preprocess column
    raw = df[col].astype(str).str.strip()
    df = df.copy()
    if col_type == "numeric":
        df[col] = pd.to_numeric(raw.replace({"": None, "nan": None}), errors="coerce")
        return analyze_numeric(df, col, col)
    else:
        df[col] = raw.replace({"": None, "nan": None, "None": None})
        return analyze_code(df, col, col)


def _make_fs_result(
    raw: Optional[Dict],
    segment: str,
    col: str,
    col_type: str,
    n_total: int,
) -> Optional[Dict]:
    if raw is None:
        return None
    bins = raw["bins"]
    if len(bins) < 3:
        return None  # require at least 3 bins for full-scan
    win_rois = [b["win_roi"] for b in bins]
    place_rois = [b["place_roi"] for b in bins]
    return {
        "segment": segment,
        "factor": col,
        "factor_type": col_type,
        "score_std": raw["score_std"],
        "grade": raw["grade"],
        "mark": _mark(raw["grade"]),
        "n_bins": len(bins),
        "edge_bins": sum(1 for r in win_rois if r > 100),
        "avg_win_roi": round(float(np.mean(win_rois)), 1),
        "avg_place_roi": round(float(np.mean(place_rois)), 1),
        "best_bin_win_roi": round(max(win_rois), 1),
        "best_bin_place_roi": round(max(place_rois), 1),
        "total_samples": n_total,
        "bins": bins,
    }


def run_phase1_scan(
    df: pd.DataFrame,
    scan_cols: List[Tuple[str, str]],
    include_keibajo_surface: bool = True,
    col_limit: Optional[int] = None,
) -> List[Dict]:
    """
    Phase 1: analyze each column across multiple segments.
    Segments: GLOBAL, SURFACE_2_芝, SURFACE_2_ダ, and optionally KEIBAJO_SURFACE.
    Returns list of result dicts (one per column-segment combination).
    """
    if col_limit:
        scan_cols = scan_cols[:col_limit]

    results: List[Dict] = []
    df_shiba = df[df["surface"] == "芝"] if "surface" in df.columns else pd.DataFrame()
    df_dirt  = df[df["surface"] == "ダ"] if "surface" in df.columns else pd.DataFrame()

    # Precompute keibajo_surface subsets once
    ks_subsets: List[Tuple[str, pd.DataFrame]] = []
    if include_keibajo_surface and "surface" in df.columns:
        for (kb, surf), sub in df.groupby(["keibajo_code", "surface"]):
            if len(sub) >= MIN_TOTAL_SAMPLES:
                ks_subsets.append((f"KEIBAJO_SURFACE_{kb}_{surf}", sub))

    total = len(scan_cols)
    for i, (col, ctype) in enumerate(scan_cols):
        print(f"  [{i+1}/{total}] {col} ({ctype})", end="", flush=True)
        found = 0

        # GLOBAL
        r = _analyze_on(df, col, ctype)
        res = _make_fs_result(r, "GLOBAL", col, ctype, len(df[col].dropna()))
        if res:
            results.append(res); found += 1

        # SURFACE_2_芝
        if len(df_shiba) >= MIN_TOTAL_SAMPLES:
            r = _analyze_on(df_shiba, col, ctype)
            res = _make_fs_result(r, "SURFACE_2_芝", col, ctype,
                                  int(df_shiba[col].dropna().__len__()) if col in df_shiba.columns else 0)
            if res:
                results.append(res); found += 1

        # SURFACE_2_ダ
        if len(df_dirt) >= MIN_TOTAL_SAMPLES:
            r = _analyze_on(df_dirt, col, ctype)
            res = _make_fs_result(r, "SURFACE_2_ダ", col, ctype,
                                  int(df_dirt[col].dropna().__len__()) if col in df_dirt.columns else 0)
            if res:
                results.append(res); found += 1

        # KEIBAJO_SURFACE
        ks_count = 0
        if include_keibajo_surface:
            for seg_name, sub in ks_subsets:
                r = _analyze_on(sub, col, ctype)
                res = _make_fs_result(r, seg_name, col, ctype,
                                      int(sub[col].dropna().__len__()) if col in sub.columns else 0)
                if res:
                    results.append(res); ks_count += 1

        print(f" → {found} global/surf, {ks_count} keibajo-surf results")

    return results


def run_phase2_cross(
    df: pd.DataFrame,
    p1_results: List[Dict],
    cross_segments: Optional[List[str]] = None,
    grade_filter: Tuple[str, ...] = ("S", "A"),
    max_bins: int = 1000,
) -> List[Dict]:
    """
    Phase 2: cross-analysis of A+ factor pairs from Phase 1.

    Factors are drawn from ALL Phase 1 segments (including KEIBAJO_SURFACE).
    Cross analysis runs on GLOBAL / SURFACE_2_芝 / SURFACE_2_ダ only.

    Exclusions:
      - Same-family pairs (see _FACTOR_FAMILIES)
      - Estimated unique combo bins > max_bins
      - Factors not present in df.columns
    """
    from itertools import combinations as _combinations

    if cross_segments is None:
        cross_segments = ["GLOBAL", "SURFACE_2_芝", "SURFACE_2_ダ"]

    # ---- Collect A+ unique factor names from ALL Phase 1 segments ----
    a_plus_factors = sorted({
        r["factor"] for r in p1_results
        if r.get("grade") in grade_filter
        and r.get("factor", "") in df.columns
    })

    if len(a_plus_factors) < 2:
        print(f"[INFO] Phase 2: fewer than 2 {grade_filter} factors — skipping.")
        return []

    print(f"[INFO] Phase 2: {len(a_plus_factors)} unique {grade_filter} factors")

    # ---- Build factor → best score_std (for pair ranking) ----
    factor_score: Dict[str, float] = {}
    for r in p1_results:
        f = r.get("factor", "")
        if f:
            factor_score[f] = max(factor_score.get(f, 0.0), r["score_std"])

    # ---- Generate valid pairs ----
    skipped_family = skipped_bins = 0
    pairs: List[Tuple[str, str]] = []
    for f1, f2 in _combinations(a_plus_factors, 2):
        if _same_family(f1, f2):
            skipped_family += 1
            continue
        # Pre-estimate unique combo count (product of unique values)
        n1 = df[f1].dropna().nunique()
        n2 = df[f2].dropna().nunique()
        if n1 * n2 > max_bins:
            skipped_bins += 1
            continue
        pairs.append((f1, f2))

    print(f"[INFO] Phase 2: {len(pairs)} valid pairs "
          f"(skipped {skipped_family} same-family, {skipped_bins} bin-explosion) "
          f"× {len(cross_segments)} segments → {len(pairs) * len(cross_segments)} analyses")

    if not pairs:
        return []

    # ---- Segment dataframes ----
    seg_dfs: Dict[str, pd.DataFrame] = {"GLOBAL": df}
    if "surface" in df.columns:
        seg_dfs["SURFACE_2_芝"] = df[df["surface"] == "芝"]
        seg_dfs["SURFACE_2_ダ"] = df[df["surface"] == "ダ"]

    # ---- Run cross analysis ----
    results: List[Dict] = []
    total = len(pairs) * len(cross_segments)
    done = 0
    for f1, f2 in pairs:
        for seg_name in cross_segments:
            seg_df = seg_dfs.get(seg_name)
            if seg_df is None or len(seg_df) < MIN_SAMPLES_PER_BIN:
                done += 1
                continue
            r = analyze_combination(seg_df, [f1, f2], seg_name, max_bins=max_bins)
            if r is not None:
                results.append(r)
            done += 1
            if done % 200 == 0:
                pct = done / total * 100
                print(f"  Phase 2: {done}/{total} ({pct:.0f}%), {len(results)} hits")

    return results


def _safe_csv(df_: pd.DataFrame, path: Path) -> Path:
    """Write CSV, falling back to timestamped filename if file is locked."""
    try:
        df_.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"[OK] {path}  ({len(df_):,} rows)")
        return path
    except PermissionError:
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = path.with_stem(path.stem + f"_{ts}")
        df_.to_csv(backup, index=False, encoding="utf-8-sig")
        print(f"[WARN] locked -- written to {backup}")
        return backup


def _unified_row(r: Dict, rank: int) -> Dict:
    """Convert any result dict (phase1 / phase2 / CEO) into a unified row."""
    factor = r.get("factor") or r.get("factors_str", "")
    source = r.get("source", "phase1" if "factor_type" in r else "combo")
    return {
        "rank": rank,
        "source": source,
        "segment": r["segment"],
        "factor": factor,
        "factor_type": r.get("factor_type", "combo"),
        "grade": r["grade"],
        "mark": r["mark"],
        "score_std": r["score_std"],
        "n_bins": r["n_bins"],
        "edge_bins": r["edge_bins"],
        "avg_win_roi": r["avg_win_roi"],
        "avg_place_roi": r["avg_place_roi"],
        "best_bin_win_roi": r["best_bin_win_roi"],
        "best_bin_place_roi": r["best_bin_place_roi"],
        "total_samples": r["total_samples"],
    }


def save_full_scan_results(
    p1_results: List[Dict],
    p2_results: List[Dict],
    ceo_results: List[Dict],
    output_dir: Path,
) -> None:
    """Save full-scan phase1, phase2, CEO results and combined ranking to CSV."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # ---- Tag each result with source ----
    for r in p1_results:
        r.setdefault("source", "phase1")
    for r in p2_results:
        r.setdefault("source", "phase2")
        r.setdefault("factor", r.get("factors_str", ""))
    for r in ceo_results:
        r.setdefault("source", "ceo")
        r.setdefault("factor", r.get("factors_str", ""))
        r.setdefault("factor_type", "combo")

    # ---- Phase 1 CSV (re-write even if already exists from the scan run) ----
    if p1_results:
        sorted_p1 = sorted(p1_results, key=lambda x: -x["score_std"])
        rows1 = [_unified_row(r, i + 1) for i, r in enumerate(sorted_p1)]
        _safe_csv(pd.DataFrame(rows1), output_dir / "phase1_single_all.csv")

    # ---- Phase 2 CSV ----
    if p2_results:
        sorted_p2 = sorted(p2_results, key=lambda x: -x["score_std"])
        rows2 = [_unified_row(r, i + 1) for i, r in enumerate(sorted_p2)]
        _safe_csv(pd.DataFrame(rows2), output_dir / "phase2_cross_top.csv")

    # ---- CEO CSV (reuses existing save function but also writes a standalone) ----
    if ceo_results:
        sorted_ceo = sorted(ceo_results, key=lambda x: -x["score_std"])
        rows_ceo = [_unified_row(r, i + 1) for i, r in enumerate(sorted_ceo)]
        _safe_csv(pd.DataFrame(rows_ceo), output_dir / "ceo_combination_ranking.csv")

    # ---- Combined all_combined_ranking.csv ----
    all_results = p1_results + p2_results + ceo_results
    if all_results:
        sorted_all = sorted(all_results, key=lambda x: -x["score_std"])
        rows_all = [_unified_row(r, i + 1) for i, r in enumerate(sorted_all)]
        _safe_csv(pd.DataFrame(rows_all), output_dir / "all_combined_ranking.csv")

        # ---- Grade distribution ----
        grade_counts: Dict[str, int] = {}
        for r in all_results:
            g = r["grade"]
            grade_counts[g] = grade_counts.get(g, 0) + 1
        total = len(all_results)
        print(f"\n[SUMMARY] Total results: {total:,}")
        for g in ("S", "A", "B", "C"):
            cnt = grade_counts.get(g, 0)
            print(f"  Grade {g}: {cnt:,} ({cnt/total*100:.1f}%)")

        # ---- Console TOP 30 ----
        print(f"\n=== FULL-SCAN + CEO COMBINED TOP 30 ===")
        print(f"{'Rank':>4} {'Src':>5} {'Segment':<22} {'Factor':<30} "
              f"{'Gr':>2} {'Score':>6} {'AvgW%':>6} {'BestW%':>8}")
        print("-" * 92)
        for row in rows_all[:30]:
            print(
                f"{row['rank']:>4} {row['source']:>5} "
                f"{row['segment'][:21]:<22} "
                f"{row['factor'][:29]:<30} "
                f"{(row['mark'] or row['grade']):>2} "
                f"{row['score_std']:>6.3f} "
                f"{row['avg_win_roi']:>6.1f}% "
                f"{row['best_bin_win_roi']:>7.1f}%"
            )

        # ---- S grade full list ----
        s_rows = [r for r in sorted_all if r["grade"] == "S"]
        if s_rows:
            print(f"\n=== ALL S-GRADE RESULTS ({len(s_rows)}) ===")
            print(f"{'Rank':>4} {'Src':>5} {'Segment':<22} {'Factor':<30} "
                  f"{'Score':>6} {'BestW%':>8}")
            print("-" * 80)
            for r in s_rows:
                row = _unified_row(r, sorted_all.index(r) + 1)
                print(
                    f"{row['rank']:>4} {row['source']:>5} "
                    f"{row['segment'][:21]:<22} "
                    f"{row['factor'][:29]:<30} "
                    f"{row['score_std']:>6.3f} "
                    f"{row['best_bin_win_roi']:>7.1f}%"
                )


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Factor screening batch")
    parser.add_argument("--limit", type=int, default=None,
                        help="In single-factor mode: limit rows. In CEO mode: limit combos.")
    parser.add_argument("--rows", type=int, default=None,
                        help="Limit rows loaded in CEO/full-scan mode (default 100k)")
    parser.add_argument("--factors", type=int, default=None,
                        help="(Single-factor mode) Analyze first N factors only")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--ceo-combos", action="store_true",
                        help="Run CEO combination screening mode")
    parser.add_argument("--full-scan", action="store_true",
                        help="Run full auto-discovery scan across all columns")
    parser.add_argument("--cross", action="store_true",
                        help="(full-scan) Also run Phase 2 cross-pair analysis")
    parser.add_argument("--col-limit", type=int, default=None,
                        help="(full-scan) Limit columns analyzed (for trial runs)")
    parser.add_argument("--cross-limit", type=int, default=200,
                        help="(full-scan --cross) Max factor pairs to cross-analyze (default 200)")
    parser.add_argument("--no-ks", action="store_true",
                        help="(full-scan) Skip KEIBAJO_SURFACE segment analysis")
    parser.add_argument("--skip-phase1", action="store_true",
                        help="(full-scan) Skip Phase 1 — load existing phase1_single_all.csv instead")
    args = parser.parse_args()

    output_dir = Path(args.output)

    if args.ceo_combos and not args.full_scan:
        # ----- CEO combination mode (standalone) -----
        n_combos = args.limit  # --limit = max combinations to process
        row_limit = args.rows or DEFAULT_CEO_ROWS

        print(f"[INFO] CEO mode: loading {row_limit:,} rows...")
        df = load_data(limit=row_limit)
        print(f"[INFO] Main data: {len(df):,} rows")

        if df.empty:
            print("[ERROR] No data.")
            sys.exit(1)

        df["year_weight"] = (df["yy_int"] - 15).clip(lower=1, upper=10)

        # Preprocess single-factor columns too
        for col, _, ftype in ALL_FACTORS:
            if col not in df.columns:
                continue
            raw = df[col].astype(str).str.strip()
            if ftype == "numeric":
                df[col] = pd.to_numeric(
                    raw.replace({"": None, "nan": None}), errors="coerce"
                )
            else:
                df[col] = raw.replace({"": None, "nan": None, "None": None})

        # Load previous race data (all JRA, no row limit)
        print("[INFO] Loading previous race data (JRA only, 2016+)...")
        try:
            prev_df = load_prev_data()
            print(f"[INFO] Prev data: {len(prev_df):,} rows")
        except Exception as e:
            print(f"[WARN] Could not load prev data: {e}")
            prev_df = None

        # Load bloodline data
        print("[INFO] Loading bloodline data...")
        try:
            blood_df = load_blood_data()
            print(f"[INFO] Bloodline data: {len(blood_df):,} rows")
        except Exception as e:
            print(f"[WARN] Could not load bloodline data: {e}")
            blood_df = None

        # Compute derived factors
        print("[INFO] Computing derived factors...")
        df = compute_derived_factors(df, prev_df, blood_df)

        # ------------------------------------------------------------------
        # Odds filter: tansho_odds 1.0~100.0 (jvd_se stores as 4-char string
        # in tenths: "0120" = 12.0x → filter: 10 <= int(tansho_odds) <= 1000)
        # ------------------------------------------------------------------
        if "tansho_odds" in df.columns:
            odds_int = pd.to_numeric(df["tansho_odds"].astype(str).str.strip(), errors="coerce")
            before = len(df)
            df = df[(odds_int >= 10) & (odds_int <= 1000)].copy()
            print(f"[INFO] Odds filter (単勝1.0~100.0倍): {before:,} → {len(df):,} rows")
        else:
            print("[WARN] tansho_odds column not found — odds filter skipped")
        print("[WARN] 複勝オッズフィルター: jvd_seに複勝個別オッズ列なし。単勝フィルターのみ適用。")

        combos = CEO_COMBINATIONS[:n_combos] if n_combos else CEO_COMBINATIONS
        print(f"[INFO] Processing {len(combos)} CEO combinations...\n")

        results = run_ceo_screening(df, combos)

        if not results:
            print("[WARN] No results.")
            return

        save_ceo_results(results, output_dir)
        print(f"\n[DONE] {len(results)} combination-segments analyzed.")

    elif args.full_scan:  # --full-scan takes priority; --ceo-combos handled inside
        # ----- Full auto-scan mode -----
        row_limit = args.rows or DEFAULT_CEO_ROWS
        print(f"[INFO] Full-scan mode: loading {row_limit:,} rows...")
        df = load_data(limit=row_limit)
        print(f"[INFO] Main data: {len(df):,} rows")

        if df.empty:
            print("[ERROR] No data.")
            sys.exit(1)

        df["year_weight"] = (df["yy_int"] - 15).clip(lower=1, upper=10)

        # Preprocess known numeric/code columns
        for col, _, ftype in ALL_FACTORS:
            if col not in df.columns:
                continue
            raw = df[col].astype(str).str.strip()
            if ftype == "numeric":
                df[col] = pd.to_numeric(raw.replace({"": None, "nan": None}), errors="coerce")
            else:
                df[col] = raw.replace({"": None, "nan": None, "None": None})

        # Load prev / blood data (same as CEO mode)
        print("[INFO] Loading previous race data (JRA only, 2016+)...")
        try:
            prev_df = load_prev_data()
            print(f"[INFO] Prev data: {len(prev_df):,} rows")
        except Exception as e:
            print(f"[WARN] Could not load prev data: {e}")
            prev_df = None

        print("[INFO] Loading bloodline data...")
        try:
            blood_df = load_blood_data()
            print(f"[INFO] Bloodline data: {len(blood_df):,} rows")
        except Exception as e:
            print(f"[WARN] Could not load bloodline data: {e}")
            blood_df = None

        print("[INFO] Computing derived factors...")
        df = compute_derived_factors(df, prev_df, blood_df)

        # Odds filter
        if "tansho_odds" in df.columns:
            odds_int = pd.to_numeric(df["tansho_odds"].astype(str).str.strip(), errors="coerce")
            before = len(df)
            df = df[(odds_int >= 10) & (odds_int <= 1000)].copy()
            print(f"[INFO] Odds filter (単勝1.0~100.0倍): {before:,} → {len(df):,} rows")
        else:
            print("[WARN] tansho_odds column not found -- odds filter skipped")

        # Load and merge extra tables (jrd_joa_fixed, jrd_bac_fixed)
        print("[INFO] Loading extra tables (jrd_joa_fixed, jrd_bac_fixed)...")
        try:
            df = load_extra_tables_for_full_scan(df)
            print(f"[INFO] After extra-table merge: {len(df):,} rows, {len(df.columns)} cols")
        except Exception as e:
            print(f"[WARN] Extra-table merge failed: {e}")

        # Auto-discover columns to scan
        scan_cols = get_scan_columns(df)
        print(f"[INFO] Auto-discovered {len(scan_cols)} columns to scan "
              f"({sum(1 for _, t in scan_cols if t=='numeric')} numeric, "
              f"{sum(1 for _, t in scan_cols if t=='code')} code)")

        if args.col_limit:
            print(f"[INFO] Column limit: {args.col_limit} (trial run)")

        # Phase 1
        if args.skip_phase1:
            p1_csv = output_dir / "phase1_single_all.csv"
            if not p1_csv.exists():
                print(f"[ERROR] --skip-phase1: {p1_csv} not found. Run Phase 1 first.")
                sys.exit(1)
            p1_df = pd.read_csv(p1_csv)
            p1_results = p1_df.to_dict(orient="records")
            # rename 'factor' field if CSV uses different key
            for r in p1_results:
                if "factor" not in r and "factors" in r:
                    r["factor"] = r["factors"]
            print(f"[INFO] Phase 1 skipped -- loaded {len(p1_results)} results from {p1_csv}")
        else:
            print(f"\n[INFO] Phase 1: single-factor scan "
                  f"({'no KEIBAJO_SURFACE' if args.no_ks else 'with KEIBAJO_SURFACE'})...")
            p1_results = run_phase1_scan(
                df,
                scan_cols,
                include_keibajo_surface=not args.no_ks,
                col_limit=args.col_limit,
            )
            print(f"[INFO] Phase 1 complete: {len(p1_results)} results")

        # Phase 2 cross (optional)
        p2_results: List[Dict] = []
        if args.cross:
            print(f"\n[INFO] Phase 2: cross-pair analysis (A+ factors, all valid pairs)...")
            p2_results = run_phase2_cross(
                df,
                p1_results,
                grade_filter=("S", "A"),
                max_bins=1000,
            )
            print(f"[INFO] Phase 2 complete: {len(p2_results)} results")

        # CEO combinations (optional, reuses same df with derived factors)
        ceo_results: List[Dict] = []
        if args.ceo_combos:
            n_combos = args.limit
            combos = CEO_COMBINATIONS[:n_combos] if n_combos else CEO_COMBINATIONS
            print(f"\n[INFO] CEO combinations: running {len(combos)} combos on same df...")
            ceo_results = run_ceo_screening(df, combos)
            print(f"[INFO] CEO complete: {len(ceo_results)} results")

        save_full_scan_results(p1_results, p2_results, ceo_results, output_dir)
        total = len(p1_results) + len(p2_results) + len(ceo_results)
        print(f"\n[DONE] {total} total results "
              f"({len(p1_results)} phase1"
              f"{f', {len(p2_results)} phase2' if args.cross else ''}"
              f"{f', {len(ceo_results)} CEO' if args.ceo_combos else ''}).")

    else:
        # ----- Single-factor mode -----
        row_limit = args.limit
        factors = ALL_FACTORS[: args.factors] if args.factors else ALL_FACTORS

        print(f"[INFO] Loading data (year {YEAR_MIN}-{YEAR_MAX}, limit={row_limit})...")
        df = load_data(limit=row_limit)
        print(f"[INFO] Loaded {len(df):,} rows")

        if df.empty:
            print("[ERROR] No data loaded.")
            sys.exit(1)

        df = preprocess(df)

        results: List[Dict] = []
        for i, (col, label, ftype) in enumerate(factors):
            prefix = f"[{i+1}/{len(factors)}] {col}"
            if col not in df.columns:
                print(f"{prefix} ... SKIP (column missing)")
                continue
            result = (
                analyze_numeric(df, col, label)
                if ftype == "numeric"
                else analyze_code(df, col, label)
            )
            if result is None:
                print(f"{prefix} ... SKIP (insufficient data)")
            else:
                print(f"{prefix} ... score_std={result['score_std']:.3f} {result['grade']}")
                results.append(result)

        if not results:
            print("[WARN] No factors had sufficient data.")
            return

        save_results(results, output_dir)
        print(f"\n[DONE] {len(results)}/{len(factors)} factors analyzed.")


if __name__ == "__main__":
    main()

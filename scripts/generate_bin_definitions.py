#!/usr/bin/env python3
"""
generate_bin_definitions.py
============================
各ファクターの現在のビン定義をCSVとMDに出力する。
ユーザーがビン変更指示を出せる粒度で整理。

出力:
  reports/source_of_truth/current_factor_bin_definitions.csv
  reports/source_of_truth/current_factor_bin_definitions.md

Usage:
  py -3.12 scripts/generate_bin_definitions.py
"""

import sys, re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

# --------------------------------------------------------------------------
# Output paths
# --------------------------------------------------------------------------
OUT_DIR = Path("reports/source_of_truth")
OUT_DIR.mkdir(parents=True, exist_ok=True)
CSV_OUT = OUT_DIR / "current_factor_bin_definitions.csv"
MD_OUT  = OUT_DIR / "current_factor_bin_definitions.md"

# --------------------------------------------------------------------------
# Factor Japanese name lookup
# --------------------------------------------------------------------------
FACTOR_JA: Dict[str, str] = {
    # NUMERIC_FACTORS (from factor_screening.py)
    "idm":                           "IDM指数",
    "sogo_shisu":                    "総合指数",
    "ten_shisu":                     "テン指数",
    "pace_shisu":                    "ペース指数",
    "agari_shisu":                   "上がり指数",
    "ichi_shisu":                    "位置指数",
    "gekiso_shisu":                  "激走指数",
    "ninki_shisu":                   "人気指数",
    "joho_shisu":                    "情報指数",
    "manken_shisu":                  "万券指数",
    "kishu_shisu":                   "騎手指数",
    "chokyo_shisu":                  "調教指数",
    "kyusha_shisu":                  "厩舎指数",
    "ls_shisu_juni":                 "LS指数順位",
    "ten_shisu_juni":                "テン指数順位",
    "pace_shisu_juni":               "ペース指数順位",
    "agari_shisu_juni":              "上がり指数順位",
    "ichi_shisu_juni":               "位置指数順位",
    "gekiso_juni":                   "激走順位",
    "kishu_kitai_rentai_ritsu":      "騎手期待連対率",
    "kishu_kitai_tansho_ritsu":      "騎手期待単勝率",
    "kishu_kitai_sanchakunai_ritsu": "騎手期待3着内率",
    "uma_start_shisu":               "馬スタート指数",
    "uma_deokure_ritsu":             "馬出遅率",
    "rotation":                      "ローテーション",
    "bataiju":                       "馬体重",
    "bataiju_zogen":                 "馬体重増減",
    "kakutoku_shokin_ruikei":        "獲得賞金累計",
    "nyukyu_nannichimae":            "入厩何日前",
    "kijun_ninkijun_tansho":         "基準人気順単勝",
    # CODE_FACTORS
    "keibajo_code":              "競馬場",
    "kyakushitsu":               "脚質",
    "class_code":                "クラスコード",
    "joshodo_code":              "上昇度",
    "hizume_code":               "蹄コード",
    "blinker":                   "ブリンカー",
    "pace_yoso":                 "ペース予想",
    "kishu_minarai_code":        "騎手見習",
    "kyori_tekisei":             "距離適性",
    "kyori_tekisei_2":           "距離適性2",
    "shiba_tekisei_code":        "芝適性",
    "da_tekisei_code":           "ダ適性",
    "omo_tekisei_code":          "重適性",
    "tenkai_kigo_code":          "展開記号",
    "manken_shirushi":           "万券印",
    "kokyu_flag":                "コ休フラグ",
    "kyuyo_riyu_bunrui_code":    "休養理由",
    "kyusha_hyoka_code":         "厩舎評価",
    "umakigo_code":              "馬記号",
    "joken_class_code":          "条件クラス",
    # Derived / CEO factors
    "prev1_chakujun":            "前走着順",
    "prev2_chakujun":            "前々走着順",
    "prev3_chakujun":            "3走前着順",
    "prev1_corner4":             "前走4角通過順",
    "prev1_corner4_bin":         "前走4角通過順ビン",
    "prev1_blinker":             "前走ブリンカー",
    "prev1_kyakushitsu":         "前走脚質",
    "prev1_keibajo":             "前走競馬場",
    "prev1_bataiju_bin":         "前走馬体重ビン",
    "bataiju_change_bin":        "馬体重変化ビン",
    "kyori_change":              "距離変化",
    "futan_juryo":               "負担重量",
    "kishu_rank":                "騎手勝率ランク",
    "chokyoshi_rank":            "調教師勝率ランク",
    "wakuban":                   "枠番",
    "umaban":                    "馬番",
    "barei":                     "馬齢",
    "babajotai_heavy":           "馬場状態(重)",
    "sanchimei":                 "産地名",
    "taikei_dou":                "体型(胴)",
    "taikei_tomo":               "体型(トモ)",
    "bamei_hahachichi":          "母父馬名",
    "bamei_chichi":              "父馬名",
    "kishumei":                  "騎手名",
    "chokyoshimei":              "調教師名",
    "tozai_shozoku_code":        "東西所属",
    "chokyo_yajirushi_code":     "調教矢印コード",
    "yuso_kubun":                "輸送区分",
    "course_27":                 "コース27分類",
    "surface":                   "馬場種別",
    "kyori_kubun":               "距離区分",
    "joa_odds_shisu":            "JOA基準オッズ指数",
    "kijun_odds_tansho":         "基準単勝オッズ",
    "kijun_odds_fukusho":        "基準複勝オッズ",
    "kijun_ninkijun_fukusho":    "基準複勝人気順",
    "shutoku_shokin_ruikei":     "取得賞金累計",
    "jrdb_race_key8":            "JRDBレースキー",
}

# --------------------------------------------------------------------------
# NUMERIC factors (bin via pd.qcut q=10 in screening, raw groupby in audit)
# --------------------------------------------------------------------------
NUMERIC_FACTORS = {
    "idm","sogo_shisu","ten_shisu","pace_shisu","agari_shisu","ichi_shisu",
    "gekiso_shisu","ninki_shisu","joho_shisu","manken_shisu","kishu_shisu",
    "chokyo_shisu","kyusha_shisu","ls_shisu_juni","ten_shisu_juni",
    "pace_shisu_juni","agari_shisu_juni","ichi_shisu_juni","gekiso_juni",
    "kishu_kitai_rentai_ritsu","kishu_kitai_tansho_ritsu",
    "kishu_kitai_sanchakunai_ritsu","uma_start_shisu","uma_deokure_ritsu",
    "rotation","bataiju","bataiju_zogen","kakutoku_shokin_ruikei",
    "nyukyu_nannichimae","kijun_ninkijun_tansho","futan_juryo",
    "joa_odds_shisu","kijun_odds_tansho","kijun_odds_fukusho",
    "kijun_ninkijun_fukusho","shutoku_shokin_ruikei",
}

# --------------------------------------------------------------------------
# CODE (categorical) factors
# --------------------------------------------------------------------------
CODE_FACTORS = {
    "keibajo_code","kyakushitsu","class_code","joshodo_code","hizume_code",
    "blinker","pace_yoso","kishu_minarai_code","kyori_tekisei","kyori_tekisei_2",
    "shiba_tekisei_code","da_tekisei_code","omo_tekisei_code","tenkai_kigo_code",
    "manken_shirushi","kokyu_flag","kyuyo_riyu_bunrui_code","kyusha_hyoka_code",
    "umakigo_code","joken_class_code",
}

# Rank-type numeric factors (index/rank values, integer-meaning)
RANK_FACTORS = {
    "ls_shisu_juni","ten_shisu_juni","pace_shisu_juni","agari_shisu_juni",
    "ichi_shisu_juni","gekiso_juni",
    "prev1_chakujun","prev2_chakujun","prev3_chakujun","prev1_corner4",
    "kishu_rank","chokyoshi_rank",
}

# --------------------------------------------------------------------------
# Bin type determination
# --------------------------------------------------------------------------
def get_bin_type(factor: str, bin_keys: List) -> str:
    if factor in {"prev1_bataiju_bin"}:
        return "manual_bucket"   # 20kg刻み
    if factor in {"bataiju_change_bin"}:
        return "derived_bucket"  # ±10kg刻み
    if factor in {"prev1_corner4_bin"}:
        return "derived_bucket"  # 1-3/4-6/7-9/10+
    if factor in RANK_FACTORS:
        return "rank_bucket"
    if factor in CODE_FACTORS:
        return "categorical"
    if factor in {"wakuban","umaban","barei","tozai_shozoku_code","prev1_keibajo",
                  "prev1_kyakushitsu","prev1_blinker","kyori_change","course_27",
                  "surface","kyori_kubun","babajotai_heavy","sanchimei","taikei_dou",
                  "taikei_tomo","bamei_hahachichi","bamei_chichi","kishumei",
                  "chokyoshimei","chokyo_yajirushi_code","yuso_kubun","keibajo_code",
                  "joken_class_code","kokyu_flag","kyusha_hyoka_code","joa_odds_shisu"}:
        return "categorical"
    if factor in NUMERIC_FACTORS:
        return "numeric_range"
    return "categorical"


# --------------------------------------------------------------------------
# Current bin rule description
# --------------------------------------------------------------------------
BIN_RULE_MAP: Dict[str, str] = {
    "prev1_bataiju_bin":   "前走馬体重を20kg刻みでバケット化 (// 20 * 20)",
    "bataiju_change_bin":  "今走馬体重 - 前走馬体重 を ±10kg刻みでバケット化 (// 10 * 10)",
    "prev1_corner4_bin":   "前走4角通過順を4グループに集約 (1-3 / 4-6 / 7-9 / 10+)",
    "kishu_rank":          "騎手コード別勝率でデータ全体をランク付け (_rank_by_winrate)",
    "chokyoshi_rank":      "調教師コード別勝率でデータ全体をランク付け (_rank_by_winrate)",
    "bataiju":             "馬体重(kg)をそのままビン化 (JVD: v.bataiju, CAST NUMERIC)",
    "bataiju_zogen":       "馬体重増減を符号付きでそのままビン化 (zogen_fugo + zogen_sa)",
    "futan_juryo":         "負担重量(kg)をそのままビン化 (v.futan_juryo_raw / 10.0)",
    "rotation":            "ローテーション日数(整数)をそのままビン化",
    "prev1_chakujun":      "前走着順(整数)をそのままビン化",
    "prev2_chakujun":      "前々走着順(整数)をそのままビン化",
    "prev3_chakujun":      "3走前着順(整数)をそのままビン化",
    "prev1_corner4":       "前走4角通過順(整数)をそのままビン化",
    "wakuban":             "枠番(1-8)をそのままビン化",
    "umaban":              "馬番をそのままビン化",
    "barei":               "馬齢(歳)をそのままビン化",
    "keibajo_code":        "競馬場コード(01-10)をそのままビン化",
    "kishu_minarai_code":  "騎手見習コード(0-9)をそのままビン化",
    "manken_shirushi":     "万券印コード(1-8)をそのままビン化",
    "kyakushitsu":         "脚質コード(1逃/2先/3差/4追)をそのままビン化",
    "joken_class_code":    "条件クラスコード(0新馬/1-3勝クラス/9OP)をそのままビン化",
    "class_code":          "クラスコードをそのままビン化",
    "pace_yoso":           "ペース予想コードをそのままビン化",
    "kyori_tekisei":       "距離適性コード(A-E)をそのままビン化",
    "kyori_tekisei_2":     "距離適性2コード(A-E)をそのままビン化",
    "joshodo_code":        "上昇度コードをそのままビン化",
    "hizume_code":         "蹄コードをそのままビン化",
    "blinker":             "ブリンカーコードをそのままビン化",
    "shiba_tekisei_code":  "芝適性コードをそのままビン化",
    "da_tekisei_code":     "ダ適性コードをそのままビン化",
    "omo_tekisei_code":    "重適性コードをそのままビン化",
    "tenkai_kigo_code":    "展開記号コードをそのままビン化",
    "kokyu_flag":          "コ休フラグをそのままビン化",
    "kyuyo_riyu_bunrui_code": "休養理由コードをそのままビン化",
    "kyusha_hyoka_code":   "厩舎評価コードをそのままビン化",
    "umakigo_code":        "馬記号コードをそのままビン化",
    "prev1_keibajo":       "前走競馬場コードをそのままビン化",
    "prev1_kyakushitsu":   "前走脚質コードをそのままビン化",
    "prev1_blinker":       "前走ブリンカーコードをそのままビン化",
    "tozai_shozoku_code":  "東西所属コード(東/西/地)をそのままビン化",
    "chokyo_yajirushi_code": "調教矢印コードをそのままビン化",
    "yuso_kubun":          "輸送区分コードをそのままビン化",
    "babajotai_heavy":     "重馬場フラグ(0/1)をそのままビン化",
    "sanchimei":           "産地名(文字列)をそのままビン化",
    "taikei_dou":          "体型コード(胴部分)をそのままビン化",
    "taikei_tomo":         "体型コード(トモ部分)をそのままビン化",
    "bamei_hahachichi":    "母父馬名(文字列)をそのままビン化",
    "bamei_chichi":        "父馬名(文字列)をそのままビン化",
    "kishumei":            "騎手名(文字列)をそのままビン化",
    "chokyoshimei":        "調教師名(文字列)をそのままビン化",
    "course_27":           "コース27分類(競馬場×馬場×距離)をそのままビン化",
    "surface":             "馬場種別(芝/ダ/障)をそのままビン化",
    "kyori_kubun":         "距離区分(短距離/マイル/中距離/長距離)をそのままビン化",
    "kyori_change":        "距離変化(未実装・全NULL)",
    "joa_odds_shisu":      "JOA基準オッズ指数をそのままビン化",
}

def get_bin_rule(factor: str) -> str:
    if factor in BIN_RULE_MAP:
        return BIN_RULE_MAP[factor]
    if factor in NUMERIC_FACTORS:
        return "数値をそのままビン化（監査: groupby raw value / スクリーニング: 10分位クォンタイル）"
    return "値をそのままビン化"


# --------------------------------------------------------------------------
# bin_label_ja: human-readable Japanese label for a bin_key
# --------------------------------------------------------------------------
MANKEN_SHIRUSHI_MAP = {
    "0.0": "印なし(0)", "1.0": "万券×(1)", "2.0": "万券△(2)", "3.0": "万券▲(3)",
    "4.0": "万券◎(4)", "5.0": "万券◇(5)", "6.0": "万券○(6)",
    "7.0": "万券☆(7)", "8.0": "万券★(8)",
}
KISHU_MINARAI_MAP = {
    "0.0": "見習なし(0)", "1.0": "★15%(1)", "2.0": "▲10%(2)",
    "3.0": "△5%(3)", "4.0": "△3%(4)", "9.0": "地方等(9)",
}
KYAKUSHITSU_MAP = {
    "1": "逃げ(1)", "2": "先行(2)", "3": "差し(3)", "4": "追込(4)",
    "1.0": "逃げ(1)", "2.0": "先行(2)", "3.0": "差し(3)", "4.0": "追込(4)",
}
JOKEN_CLASS_MAP = {
    "0": "新馬(0)", "1": "1勝クラス(1)", "2": "2勝クラス(2)",
    "3": "3勝クラス(3)", "9": "OP重賞(9)",
    "0.0": "新馬(0)", "1.0": "1勝クラス(1)", "2.0": "2勝クラス(2)",
    "3.0": "3勝クラス(3)", "9.0": "OP重賞(9)",
}
WAKUBAN_MAP = {str(i)+".0": f"{i}枠" for i in range(1, 9)}
WAKUBAN_MAP.update({str(i): f"{i}枠" for i in range(1, 9)})
TOZAI_MAP = {"1": "東(1)", "2": "西(2)", "3": "地方(3)",
             "1.0": "東(1)", "2.0": "西(2)", "3.0": "地方(3)"}
BABAJOTAI_MAP = {"0": "良・稍重", "1": "重・不良", "0.0": "良・稍重", "1.0": "重・不良"}
KEIBAJO_MAP = {
    "01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "05": "東京",
    "06": "中山", "07": "京都", "08": "阪神", "09": "小倉", "10": "中京",
    "1.0": "札幌", "2.0": "函館", "3.0": "福島", "4.0": "新潟", "5.0": "東京",
    "6.0": "中山", "7.0": "京都", "8.0": "阪神", "9.0": "小倉", "10.0": "中京",
}
CORNER4_BIN_MAP = {"1-3": "1〜3番手", "4-6": "4〜6番手", "7-9": "7〜9番手", "10+": "10番手以降"}
PACE_YOSO_MAP = {
    "1": "超スロー(1)", "2": "スロー(2)", "3": "平均(3)", "4": "ハイ(4)", "5": "超ハイ(5)",
    "1.0":"超スロー(1)","2.0":"スロー(2)","3.0":"平均(3)","4.0":"ハイ(4)","5.0":"超ハイ(5)",
}
KYORI_TEKISEI_MAP = {
    "A": "最適(A)", "B": "適(B)", "C": "普通(C)", "D": "やや不向き(D)", "E": "不向き(E)",
    "1": "最適(A)", "2": "適(B)", "3": "普通(C)", "4": "やや不向き(D)", "5": "不向き(E)",
}
CHOKYO_YAJIRUSHI_MAP = {
    "0": "矢印なし(0)", "1": "↑(1)", "2": "↑↑(2)", "3": "↓(3)", "4": "↓↓(4)", "5": "→(5)",
    "0.0":"矢印なし(0)","1.0":"↑(1)","2.0":"↑↑(2)","3.0":"↓(3)","4.0":"↓↓(4)","5.0":"→(5)",
}

CODE_LABEL_MAPS: Dict[str, Dict[str, str]] = {
    "manken_shirushi":     MANKEN_SHIRUSHI_MAP,
    "kishu_minarai_code":  KISHU_MINARAI_MAP,
    "kyakushitsu":         KYAKUSHITSU_MAP,
    "prev1_kyakushitsu":   KYAKUSHITSU_MAP,
    "joken_class_code":    JOKEN_CLASS_MAP,
    "wakuban":             WAKUBAN_MAP,
    "babajotai_heavy":     BABAJOTAI_MAP,
    "keibajo_code":        KEIBAJO_MAP,
    "prev1_keibajo":       KEIBAJO_MAP,
    "tozai_shozoku_code":  TOZAI_MAP,
    "prev1_corner4_bin":   CORNER4_BIN_MAP,
    "pace_yoso":           PACE_YOSO_MAP,
    "kyori_tekisei":       KYORI_TEKISEI_MAP,
    "kyori_tekisei_2":     KYORI_TEKISEI_MAP,
    "chokyo_yajirushi_code": CHOKYO_YAJIRUSHI_MAP,
}

def make_bin_label(factor: str, bin_key_str: str) -> str:
    """Generate human-readable Japanese label for a bin_key."""
    # composite key (pipe-separated)
    if "|" in bin_key_str:
        parts = bin_key_str.split("|")
        # can't determine sub-factor labels without factor list; return as-is
        return bin_key_str

    # use code label map if available
    if factor in CODE_LABEL_MAPS:
        lbl = CODE_LABEL_MAPS[factor].get(bin_key_str)
        if lbl:
            return lbl

    # manken_shirushi special float -> int check
    try:
        v = float(bin_key_str)
    except (ValueError, TypeError):
        return bin_key_str

    # rank/position factors
    if factor in {"prev1_chakujun","prev2_chakujun","prev3_chakujun"}:
        return f"{int(v)}着"
    if factor in {"prev1_corner4"}:
        return f"4角{int(v)}番手通過"
    if factor in {"kishu_rank","chokyoshi_rank"}:
        return f"勝率ランク{int(v)}位"
    if factor in {"ls_shisu_juni","ten_shisu_juni","pace_shisu_juni",
                  "agari_shisu_juni","ichi_shisu_juni","gekiso_juni"}:
        return f"順位{int(v)}番"
    if factor in {"wakuban"}:
        return f"{int(v)}枠"
    if factor in {"umaban"}:
        return f"{int(v)}番"
    if factor in {"barei"}:
        return f"{int(v)}歳"
    if factor in {"rotation"}:
        if int(v) == 0:
            return "当日(0日)"
        return f"{int(v)}日"
    if factor in {"futan_juryo"}:
        return f"{v:.1f}kg"
    if factor in {"bataiju"}:
        return f"{int(v)}kg"
    if factor in {"bataiju_zogen"}:
        return f"{int(v):+d}kg"
    if factor in {"prev1_bataiju_bin"}:
        return f"前走{int(v)}〜{int(v)+19}kg"
    if factor in {"bataiju_change_bin"}:
        d = int(v)
        return f"体重変化{d:+d}〜{d+9:+d}kg"
    if factor in {"nyukyu_nannichimae"}:
        return f"入厩{int(v)}日前"
    if factor in {"kijun_ninkijun_tansho","kijun_ninkijun_fukusho"}:
        return f"人気{int(v)}番"
    # Rate factors (0-1 or 0-100 scale)
    if factor in {"kishu_kitai_rentai_ritsu","kishu_kitai_tansho_ritsu","kishu_kitai_sanchakunai_ritsu"}:
        return f"{v*100:.1f}%"
    if factor in {"uma_deokure_ritsu"}:
        return f"出遅{int(v)}%"
    if factor in {"uma_start_shisu"}:
        return f"スタート{v:.1f}"
    # Generic numeric → just return as value
    return f"値={bin_key_str}"


def make_bin_contents(factor: str, bin_key_str: str) -> str:
    """bin_contentsを生成する。"""
    if "|" in bin_key_str:
        return bin_key_str
    if factor in {"prev1_bataiju_bin"}:
        try:
            v = int(float(bin_key_str))
            return f"{v}以上{v+20}未満"
        except (ValueError, TypeError):
            return bin_key_str
    if factor in {"bataiju_change_bin"}:
        try:
            v = int(float(bin_key_str))
            return f"{v:+d}以上{v+10:+d}未満"
        except (ValueError, TypeError):
            return bin_key_str
    if factor in {"prev1_corner4_bin"}:
        return CORNER4_BIN_MAP.get(bin_key_str, bin_key_str)
    if factor in CODE_FACTORS or factor in CODE_LABEL_MAPS:
        return f"コード={bin_key_str}"
    try:
        v = float(bin_key_str)
        return f"値={v}"
    except (ValueError, TypeError):
        return bin_key_str


def sample_size_bucket(n: int) -> str:
    if n < 10:   return "1-9"
    if n < 50:   return "10-49"
    if n < 100:  return "50-99"
    if n < 150:  return "100-149"
    if n < 300:  return "150-299"
    if n < 500:  return "300-499"
    return "500+"


def get_bin_min_max(factor: str, bin_key_str: str) -> Tuple[Optional[float], Optional[float]]:
    """数値ビンの最小・最大値を返す。"""
    if "|" in bin_key_str:
        return None, None
    if factor in {"prev1_bataiju_bin"}:
        try:
            v = float(bin_key_str)
            return v, v + 20
        except (ValueError, TypeError):
            return None, None
    if factor in {"bataiju_change_bin"}:
        try:
            v = float(bin_key_str)
            return v, v + 10
        except (ValueError, TypeError):
            return None, None
    if factor in CODE_FACTORS or factor in {
        "keibajo_code","wakuban","umaban","barei","tozai_shozoku_code",
        "prev1_keibajo","prev1_kyakushitsu","prev1_blinker","babajotai_heavy",
        "kishumei","chokyoshimei","sanchimei","taikei_dou","taikei_tomo",
        "bamei_chichi","bamei_hahachichi","course_27","surface","kyori_kubun",
        "chokyo_yajirushi_code","yuso_kubun","joken_class_code",
        "prev1_corner4_bin","kyori_change",
    }:
        return None, None
    try:
        v = float(bin_key_str)
        return v, v
    except (ValueError, TypeError):
        return None, None


def make_note(factor: str, bin_key_str: str, n: int) -> str:
    notes = []
    if factor in {"kyori_change"}:
        notes.append("未実装・全NULL（placeholder）")
    if n < 10:
        notes.append("サンプル極小(<10)")
    if factor in {"kishumei","chokyoshimei","bamei_chichi","bamei_hahachichi","sanchimei"}:
        notes.append("文字列ビン・高カーディナリティ・要再設計")
    if factor in {"kishu_kitai_tansho_ritsu","kishu_kitai_rentai_ritsu","kishu_kitai_sanchakunai_ritsu"}:
        notes.append("率の細かい値ごとビン・高カーディナリティ・要10分位化")
    if factor in {"kakutoku_shokin_ruikei","shutoku_shokin_ruikei"}:
        notes.append("賞金累計・値幅大・要対数変換or分位化")
    if factor in RANK_FACTORS and factor.endswith("_juni"):
        notes.append("少頭数レースでは上位ランクのみ出現")
    return " / ".join(notes) if notes else ""


# --------------------------------------------------------------------------
# Main: read phase CSVs and build output
# --------------------------------------------------------------------------
def main():
    print("=== generate_bin_definitions ===")

    # 1. Read all phase bin detail CSVs
    all_dfs = []
    for p in [1, 2, 3, 4]:
        path = Path(f"reports/production_search/phase{p}_bin_detail_for_adoption_review.csv")
        if path.exists():
            df = pd.read_csv(path)
            all_dfs.append(df)
            print(f"  Phase{p}: {len(df)} rows loaded")

    df_all = pd.concat(all_dfs, ignore_index=True)
    df_all["bin_key"] = df_all["bin_key"].astype(str).str.strip()
    print(f"  Total: {len(df_all)} rows, {df_all['combo'].nunique()} unique combos")

    # 2. Aggregate to combo × bin_key level (sum n_horses across segments)
    #    Keep all phase+segment rows for CSV detail, but add metadata
    rows = []

    for (phase, segment, combo), grp in df_all.groupby(["phase", "segment", "combo"], sort=True):
        # Parse factors from combo name
        if "+" in combo:
            factors = combo.split("+")
        else:
            factors = [combo]

        combo_ja_parts = [FACTOR_JA.get(f, f"【要確認】{f}") for f in factors]
        combo_ja = "＋".join(combo_ja_parts)

        # Sort bins
        bin_grp = grp.groupby("bin_key")["n_horses"].sum().reset_index()
        # Attempt numeric sort
        bin_grp["_sort"] = pd.to_numeric(
            bin_grp["bin_key"].str.split("|").str[0], errors="coerce"
        )
        bin_grp = bin_grp.sort_values(
            ["_sort", "bin_key"], na_position="last"
        ).reset_index(drop=True)

        for bin_order, row in enumerate(bin_grp.itertuples(), start=1):
            bk = str(row.bin_key)
            n  = int(row.n_horses)

            for factor in factors:
                factor_ja = FACTOR_JA.get(factor, f"【要確認】{factor}")
                btype     = get_bin_type(factor, [bk])
                brule     = get_bin_rule(factor)
                blabel    = make_bin_label(factor, bk) if "|" not in bk else bk
                bcontents = make_bin_contents(factor, bk)
                bmin, bmax = get_bin_min_max(factor, bk)
                ssb       = sample_size_bucket(n)
                note      = make_note(factor, bk, n)

                rows.append({
                    "phase":            phase,
                    "segment":          segment,
                    "combo":            combo,
                    "combo_ja":         combo_ja,
                    "factor_name":      factor,
                    "factor_name_ja":   factor_ja,
                    "bin_order":        bin_order,
                    "bin_key":          bk,
                    "bin_label_ja":     blabel,
                    "bin_type":         btype,
                    "current_bin_rule": brule,
                    "bin_contents":     bcontents,
                    "bin_min_value":    bmin,
                    "bin_max_value":    bmax,
                    "n_horses":         n,
                    "sample_size_bucket": ssb,
                    "note":             note,
                })

    out_df = pd.DataFrame(rows)
    print(f"  Output rows: {len(out_df)}")

    # 3. Write CSV
    out_df.to_csv(CSV_OUT, index=False, encoding="utf-8-sig")
    print(f"  [OK] {CSV_OUT}  ({len(out_df)} rows)")

    # -----------------------------------------------------------------------
    # 4. Write MD (per-factor summary, aggregated across all segments)
    # -----------------------------------------------------------------------
    # Aggregate n_horses per combo × bin_key (sum across phases and segments)
    agg = (
        df_all
        .groupby(["combo", "bin_key"])["n_horses"]
        .sum()
        .reset_index()
        .rename(columns={"n_horses": "total_n"})
    )
    agg["bin_key"] = agg["bin_key"].astype(str).str.strip()

    # Per-combo phase+segment info
    combo_phases = (
        df_all
        .groupby("combo")[["phase","segment"]]
        .apply(lambda x: (sorted(x["phase"].unique()), sorted(x["segment"].unique())))
    )

    md_lines = [
        "# 現在のファクターごとビン定義一覧",
        "",
        f"生成日: 2026-05-04",
        f"対象combo数: {df_all['combo'].nunique()} / 対象ファクター数(ユニーク): 要確認",
        "",
        "---",
        "",
        "## 凡例",
        "- **bin_type**: categorical=コード値そのまま / numeric_range=数値そのままビン化 /",
        "  rank_bucket=順位そのままビン化 / manual_bucket=手動設計バケット /",
        "  derived_bucket=派生計算後バケット",
        "- **n(合計)**: 全フェーズ×全セグメント合算の頭数",
        "- ビン変更指示はこのMDのcombo名と`bin_key`を参照して行ってください",
        "",
        "---",
        "",
    ]

    # Group combos: first by primary factor for readability
    all_combos = sorted(df_all["combo"].unique())

    no_ja_count = 0
    missing_note_count = 0

    for combo in all_combos:
        if "+" in combo:
            factors = combo.split("+")
        else:
            factors = [combo]

        combo_ja_parts = [FACTOR_JA.get(f, f"【要確認】{f}") for f in factors]
        combo_ja = "＋".join(combo_ja_parts)

        # detect missing JA
        for f in factors:
            if f not in FACTOR_JA:
                no_ja_count += 1

        phases_segs = combo_phases.get(combo, ([], []))
        phases_list = phases_segs[0]
        segs_list   = phases_segs[1]

        combo_bins = agg[agg["combo"] == combo].copy()
        # Sort bins numerically
        combo_bins["_sort"] = pd.to_numeric(
            combo_bins["bin_key"].str.split("|").str[0], errors="coerce"
        )
        combo_bins = combo_bins.sort_values(["_sort","bin_key"], na_position="last")

        primary_factor = factors[0]
        btype = get_bin_type(primary_factor, combo_bins["bin_key"].tolist())
        brule = get_bin_rule(primary_factor)
        if len(factors) > 1:
            brule2 = get_bin_rule(factors[1])
        else:
            brule2 = None

        md_lines.append(f"## combo: `{combo}`")
        md_lines.append(f"- **日本語名**: {combo_ja}")
        md_lines.append(f"- **Phase**: {', '.join(map(str, phases_list))}")
        md_lines.append(f"- **Segment例**: {', '.join(segs_list[:3])}{' ...' if len(segs_list)>3 else ''}")
        md_lines.append(f"- **ビン数**: {len(combo_bins)} bins")
        md_lines.append(f"- **最大n_horses(合算)**: {int(combo_bins['total_n'].max()):,}")
        md_lines.append(f"")
        md_lines.append(f"### ビン分けルール")
        for fi, factor in enumerate(factors):
            factor_ja = FACTOR_JA.get(factor, f"【要確認】{factor}")
            rule = get_bin_rule(factor)
            btype_f = get_bin_type(factor, combo_bins["bin_key"].tolist())
            md_lines.append(f"- **{factor}**（{factor_ja}）")
            md_lines.append(f"  - bin_type: `{btype_f}`")
            md_lines.append(f"  - rule: {rule}")

        md_lines.append(f"")
        md_lines.append(f"### ビン一覧")
        md_lines.append(f"| bin_order | bin_key | bin_label_ja | n(合算) | sample_size_bucket |")
        md_lines.append(f"|-----------|---------|--------------|---------|-------------------|")

        for bo, brow in enumerate(combo_bins.itertuples(), start=1):
            bk  = str(brow.bin_key)
            n   = int(brow.total_n)
            lbl = make_bin_label(primary_factor, bk) if "|" not in bk else bk
            ssb = sample_size_bucket(n)
            note = make_note(primary_factor, bk, n)
            note_str = f" ⚠{note}" if note else ""
            md_lines.append(f"| {bo} | `{bk}` | {lbl} | {n:,} | {ssb}{note_str} |")

        # Issues / notes
        issue_notes = []
        if len(combo_bins) > 50:
            issue_notes.append(f"ビン数多すぎ({len(combo_bins)})・要集約")
        if any(f not in FACTOR_JA for f in factors):
            issue_notes.append("日本語名不明ファクターあり(要コード確認)")
        if primary_factor in {"kyori_change"}:
            issue_notes.append("kyori_changeは全NULL（未実装）・ビン不成立")
        if (combo_bins["total_n"] < 10).all():
            issue_notes.append("全ビンサンプル10件未満")

        if issue_notes:
            md_lines.append(f"")
            md_lines.append(f"### 注意点")
            for note in issue_notes:
                md_lines.append(f"- {note}")
            missing_note_count += 1

        md_lines.append("")
        md_lines.append("---")
        md_lines.append("")

    # Write MD
    MD_OUT.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"  [OK] {MD_OUT}")

    # -----------------------------------------------------------------------
    # 5. Summary
    # -----------------------------------------------------------------------
    unique_factors = set()
    for combo in all_combos:
        for f in combo.split("+"):
            unique_factors.add(f)

    no_ja_factors = [f for f in unique_factors if f not in FACTOR_JA]
    req_code_check = len([r for r in rows if "要コード確認" in str(r.get("note",""))])

    print()
    print("=== 最終サマリー ===")
    print(f"  出力CSV: {CSV_OUT}  ({len(out_df)} rows)")
    print(f"  出力MD:  {MD_OUT}")
    print(f"  対象ファクター数(ユニーク): {len(unique_factors)}")
    print(f"  combo数: {len(all_combos)}")
    print(f"  日本語名なしファクター: {len(no_ja_factors)}")
    if no_ja_factors:
        print(f"    → {no_ja_factors}")
    print(f"  要コード確認件数: {req_code_check}")

    return {
        "csv_rows": len(out_df),
        "combos": len(all_combos),
        "unique_factors": len(unique_factors),
        "no_ja": no_ja_factors,
        "req_code_check": req_code_check,
    }


if __name__ == "__main__":
    main()

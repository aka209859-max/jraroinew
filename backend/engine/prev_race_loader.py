"""
前走データ取得エンジン

直近3走分の着順・通過順位・ブリンカー・馬体重・タイム差・競馬場コード・
距離・track_code を、現在のレースレコードに横付けする。

2種類のモードを提供する:
  - GLOBAL前走:  同一馬の直近3走（コース不問）
  - COURSE_27前走: 同一馬 × 同一コースカテゴリの直近3走

■ ターゲットリーク防止
  LAG/shift は「前の行」のみを参照するため、当日データは使用されない。
  ただし lookback 用に 2014 年以降のデータを全てロードし、
  start_date〜end_date の範囲のみを最後にフィルタして返す。

■ 注意
  - 複数頭が同一馬番で同一レースに重複登録されるケースは原則存在しないが、
    仮に存在した場合は race_date / race_bango / umaban の昇順で先着を優先。
  - track_code が NULL の行（廃止コースなど）は GLOBAL 前走には含めるが
    course27_category は "unknown" になるため COURSE_27 前走には含まれない。

Usage:
    from backend.engine.prev_race_loader import (
        load_global_prev_races,
        load_course27_prev_races,
    )
    df = load_global_prev_races(conn, "20240101", "20241231")
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from backend.config.course_categories import get_category

# =============================================================================
# 取得カラム定義
# =============================================================================

# jvd_se から取得するカラム
_SE_COLS = [
    "ketto_toroku_bango",
    "keibajo_code",
    "kaisai_nen",
    "kaisai_tsukihi",   # MMDD 形式
    "kaisai_kai",
    "kaisai_nichime",
    "race_bango",
    "umaban",
    "kakutei_chakujun",   # 確定着順
    "corner_4",            # 4角通過順位
    "blinker_shiyo_kubun", # ブリンカー使用区分
    "bataiju",             # 馬体重
    "time_sa",             # タイム差（1着との差, 単位は 0.1 秒）
]

# jvd_ra から取得するカラム
_RA_COLS = [
    "keibajo_code",
    "kaisai_nen",
    "kaisai_tsukihi",
    "kaisai_kai",
    "kaisai_nichime",
    "race_bango",
    "track_code",   # 芝/ダート判定に使用
    "kyori",        # 距離（m）
]

# 前走列として付与する項目（前走1・2・3走で繰り返す）
_PREV_COLS = [
    "kakutei_chakujun",
    "corner_4",
    "blinker_shiyo_kubun",
    "bataiju",
    "time_sa",
    "keibajo_code",
    "kyori",
    "track_code",
    "race_date",   # 休養週数計算に使用（YYYYMMDD 文字列）
    "race_bango",  # jrd_sed との前走 JOIN キー
]

# JRA競馬場コード（NARデータを除外）
_JRA_CODES = ("01", "02", "03", "04", "05", "06", "07", "08", "09", "10")


# =============================================================================
# ヘルパー関数
# =============================================================================

def _assign_surface(track_code_series: pd.Series) -> pd.Series:
    """
    track_code から馬場種別文字列（'芝' or 'ダ'）を返す。

    JRA-VAN track_code:
      1x = 芝
      2x = ダート
      その他 = NaN
    """
    s = track_code_series.astype(str).str.strip()
    surface = pd.Series("unknown", index=track_code_series.index, dtype=str)
    surface[s.str.startswith("1")] = "芝"
    surface[s.str.startswith("2")] = "ダ"
    return surface


def _assign_course27(df: pd.DataFrame) -> pd.Series:
    """
    keibajo_code / track_code / kyori から 27 コースカテゴリを付与する。

    Args:
        df: keibajo_code, track_code, kyori カラムを持つ DataFrame

    Returns:
        コースカテゴリ名の Series（該当なしは "unknown"）
    """
    surface_ser = _assign_surface(df["track_code"])
    result = pd.Series("unknown", index=df.index, dtype=str)
    for idx in df.index:
        code = str(df.at[idx, "keibajo_code"]).strip()
        surf = surface_ser.at[idx]
        if surf == "unknown":
            continue
        try:
            dist = int(df.at[idx, "kyori"])
        except (ValueError, TypeError):
            continue
        result.at[idx] = get_category(code, surf, dist)
    return result


def _load_raw(conn, lookback_start: str, end_date: str) -> pd.DataFrame:
    """
    jvd_se + jvd_ra を JOIN して生データを取得する。

    Args:
        conn: psycopg2 / SQLAlchemy 接続オブジェクト
        lookback_start: ロードを開始する日付（YYYYMMDD、通常 "20140101"）
        end_date:       ロードを終了する日付（YYYYMMDD）

    Returns:
        カラム: _SE_COLS + ['track_code', 'kyori', 'race_date']
    """
    se_cols_sql = ", ".join(f"se.{c}" for c in _SE_COLS)

    query = f"""
    SELECT
        {se_cols_sql},
        ra.track_code,
        ra.kyori,
        (se.kaisai_nen || se.kaisai_tsukihi) AS race_date
    FROM jvd_se AS se
    LEFT JOIN jvd_ra AS ra
        ON  se.keibajo_code   = ra.keibajo_code
        AND se.kaisai_nen     = ra.kaisai_nen
        AND se.kaisai_tsukihi = ra.kaisai_tsukihi
        AND se.kaisai_kai     = ra.kaisai_kai
        AND se.kaisai_nichime = ra.kaisai_nichime
        AND se.race_bango     = ra.race_bango
    WHERE
        se.keibajo_code IN {str(_JRA_CODES)}
        AND (se.kaisai_nen || se.kaisai_tsukihi) >= '{lookback_start}'
        AND (se.kaisai_nen || se.kaisai_tsukihi) <= '{end_date}'
    """

    df = pd.read_sql_query(query, conn)
    return df


def _clean_raw(df: pd.DataFrame) -> pd.DataFrame:
    """
    生データを整形・型変換する。

    - 文字列カラムのトリム
    - 数値カラムの型変換
    - 重複除去（race_date + race_bango + umaban が同一の場合、先着行を保持）
    - 並び替え（ketto_toroku_bango → race_date → race_bango → umaban）
    """
    str_cols = [
        "ketto_toroku_bango", "keibajo_code", "kaisai_nen", "kaisai_tsukihi",
        "kaisai_kai", "kaisai_nichime", "race_bango", "umaban",
        "blinker_shiyo_kubun", "track_code",
    ]
    for col in str_cols:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    num_cols = [
        "kakutei_chakujun", "corner_4", "bataiju", "time_sa", "kyori",
    ]
    for col in num_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # 着順 0 は競走除外・失格等 → NaN 化
    if "kakutei_chakujun" in df.columns:
        df["kakutei_chakujun"] = df["kakutei_chakujun"].where(
            df["kakutei_chakujun"] > 0, other=float("nan")
        )

    # 重複除去
    df = df.drop_duplicates(
        subset=["ketto_toroku_bango", "race_date", "race_bango", "umaban"],
        keep="first",
    )

    # ソート（LAG 計算の前提）
    df = df.sort_values(
        ["ketto_toroku_bango", "race_date", "race_bango", "umaban"],
        ignore_index=True,
    )
    return df


def _append_prev_columns(
    df: pd.DataFrame,
    group_keys: list[str],
    lag_n: int,
    suffix: str,
) -> pd.DataFrame:
    """
    group_keys でグループ化し、_PREV_COLS を lag_n だけシフトして
    f"{col}_prev{suffix}" カラムとして df に追加する。

    Args:
        df:         ソート済みの DataFrame
        group_keys: groupby に使うカラム名リスト
        lag_n:      シフト量（1=直前走, 2=2走前, 3=3走前）
        suffix:     カラム名サフィックス（"1", "2", "3" など）

    Returns:
        前走カラムを追加した DataFrame（コピー）
    """
    df = df.copy()
    grp = df.groupby(group_keys, sort=False)
    for col in _PREV_COLS:
        if col not in df.columns:
            continue
        df[f"{col}_prev{suffix}"] = grp[col].shift(lag_n)
    return df


# =============================================================================
# 公開 API
# =============================================================================

def load_global_prev_races(
    conn,
    start_date: str,
    end_date: str,
    lookback_start: str = "20140101",
) -> pd.DataFrame:
    """
    GLOBAL前走データを取得する（コース不問、直近3走）。

    各レースレコードに対して、同一馬の直前1〜3走の情報を横付けする。
    コース種別（芝/ダート）・競馬場は問わない。

    返り値のカラム:
      - 元レコードの全カラム（ketto_toroku_bango, race_date 等）
      - kakutei_chakujun_prev1〜3  : 着順
      - corner_4_prev1〜3          : 4角通過順位
      - blinker_shiyo_kubun_prev1〜3: ブリンカー使用区分
      - bataiju_prev1〜3           : 馬体重
      - time_sa_prev1〜3           : タイム差
      - keibajo_code_prev1〜3      : 競馬場コード
      - kyori_prev1〜3             : 距離
      - track_code_prev1〜3        : track_code

    Args:
        conn:           DB接続オブジェクト（psycopg2 / SQLAlchemy）
        start_date:     分析対象開始日（YYYYMMDD）
        end_date:       分析対象終了日（YYYYMMDD）
        lookback_start: 前走ルックバック用データのロード開始日（デフォルト 20140101）

    Returns:
        start_date〜end_date のレコードのみを含む DataFrame

    Note:
        初出走馬・ルックバック期間外の最初のレースは prev カラムが NaN になる。
        ターゲットリーク防止のため、当日以前のデータのみが prev として使われる。
    """
    df = _load_raw(conn, lookback_start, end_date)
    df = _clean_raw(df)

    # GLOBAL: 馬 ID のみでグループ化
    for lag in range(1, 4):
        df = _append_prev_columns(df, ["ketto_toroku_bango"], lag, str(lag))

    # 分析対象期間のみ返す
    mask = (df["race_date"] >= start_date) & (df["race_date"] <= end_date)
    return df[mask].reset_index(drop=True)


def load_course27_prev_races(
    conn,
    start_date: str,
    end_date: str,
    lookback_start: str = "20140101",
) -> pd.DataFrame:
    """
    COURSE_27前走データを取得する（同一コースカテゴリ内の直近3走）。

    各レースレコードに対して、同一馬 × 同一 27 コースカテゴリの
    直前1〜3走の情報を横付けする。

    例: 東京芝1600 を走る馬には、過去の「東京U字_芝」カテゴリのレースのみが
        prev として使われる。異コースの成績は含まれない。

    返り値のカラム:
      - 元レコードの全カラム + course27_category
      - kakutei_chakujun_c27_prev1〜3  : 着順
      - corner_4_c27_prev1〜3          : 4角通過順位
      - blinker_shiyo_kubun_c27_prev1〜3: ブリンカー使用区分
      - bataiju_c27_prev1〜3           : 馬体重
      - time_sa_c27_prev1〜3           : タイム差
      - keibajo_code_c27_prev1〜3      : 競馬場コード
      - kyori_c27_prev1〜3             : 距離
      - track_code_c27_prev1〜3        : track_code

    Args:
        conn:           DB接続オブジェクト（psycopg2 / SQLAlchemy）
        start_date:     分析対象開始日（YYYYMMDD）
        end_date:       分析対象終了日（YYYYMMDD）
        lookback_start: 前走ルックバック用データのロード開始日（デフォルト 20140101）

    Returns:
        start_date〜end_date のレコードのみを含む DataFrame

    Note:
        course27_category = "unknown" の行（未対応コース）は
        COURSE_27前走には使われない（prev は NaN のまま）。
        GLOBAL前走には影響しない。
    """
    df = _load_raw(conn, lookback_start, end_date)
    df = _clean_raw(df)

    # コースカテゴリを付与
    df["course27_category"] = _assign_course27(df)

    # unknown のレコードは COURSE_27 グループに含めない
    # → shift 時に unknown 行は別グループ扱いされ prev が NaN になる（正しい挙動）

    # COURSE_27: 馬 ID × コースカテゴリでグループ化
    # unknown は単独グループになり、直前 unknown も prev として使われてしまうため
    # ここでは unknown 行の course27_category を一時的に馬 ID ごとのユニーク値に変換して
    # グループが交差しないようにする。
    # 簡便のため: unknown 行の prev は NaN として扱う（index を suffix として付与）
    unknown_mask = df["course27_category"] == "unknown"
    # unknown 行をユニーク値にすることでグループが孤立し shift=NaN になる
    df.loc[unknown_mask, "course27_category"] = (
        "unknown_" + df.loc[unknown_mask].index.astype(str)
    )

    for lag in range(1, 4):
        df = _append_prev_columns(
            df,
            ["ketto_toroku_bango", "course27_category"],
            lag,
            f"_c27_{lag}",
        )

    # unknown を元に戻す（可読性のため）
    unknown_mask2 = df["course27_category"].str.startswith("unknown_")
    df.loc[unknown_mask2, "course27_category"] = "unknown"

    # カラム名のエイリアス: _PREV_COLS は "_prev{suffix}" で付与されるが
    # suffix が "_c27_1" 等になっているのでそのまま返す

    # 分析対象期間のみ返す
    mask = (df["race_date"] >= start_date) & (df["race_date"] <= end_date)
    return df[mask].reset_index(drop=True)

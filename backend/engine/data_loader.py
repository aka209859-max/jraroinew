"""
PostgreSQLデータ取得・型変換モジュール

全カラムがcharacter varying（文字列型）であるため、
数値演算前に必ず型変換を実施する。空文字・異常値のエラーハンドリング必須。

重要:
    - 当日データ（直前オッズ、当日馬体重、パドック評価、当日馬場状態速報）は使用禁止
    - ターゲットリーク防止のため、全集計は予測対象日の前日以前のデータのみ使用
"""
from typing import Optional

import pandas as pd

from backend.config.db import DBConfig, get_connection


def safe_to_numeric(series: pd.Series, errors: str = "coerce") -> pd.Series:
    """
    文字列Seriesを安全に数値変換する。

    Args:
        series: 変換対象のSeries（character varying由来）
        errors: エラー時の処理（"coerce"=NaN, "raise"=例外, "ignore"=そのまま）

    Returns:
        数値変換後のSeries。変換失敗はNaN。
    """
    # 空文字列・空白のみをNaNに変換してからpd.to_numeric
    cleaned = series.replace(r"^\s*$", pd.NA, regex=True)
    return pd.to_numeric(cleaned, errors=errors)


def load_base_race_data(
    date_from: str,
    date_to: str,
    config: Optional[DBConfig] = None,
) -> pd.DataFrame:
    """
    jvd_se（成績）を基準に、jvd_ra・jrd_kyi・jrd_cyb・jrd_bac・jrd_joaを結合した
    ベースデータを取得する。

    Args:
        date_from: 開始日（YYYYMMDD形式、例: "20161101"）
        date_to: 終了日（YYYYMMDD形式、例: "20251231"）
        config: DB接続設定

    Returns:
        結合済みDataFrame

    Note:
        ■ race_shikonenのフォーマット（2026-04-01確定）:
          - JRA-VAN (jvd_se): kaisai_nen='2024', kaisai_tsukihi='0307' → YYMMDD
          - JRDB (jrd_kyi等): race_shikonen='241104' → YY(2)+回(2)+日目(2)
          - race_shikonenはYYMMDDではない！ YY+開催回+日目 の識別子。
          - したがってrace_shikonenとYYMMDDを直接比較してはならない。

        ■ JOINキー設計（race_shikonen非依存）:
          1. keibajo_code: 場コード（TRIM比較）
          2. 年: SUBSTRING(se.kaisai_nen, 3, 2) = SUBSTRING(jrdb.race_shikonen, 1, 2)
          3. kaisai_kai: 開催回（CAST INTEGER — パディング差吸収）
          4. kaisai_nichime: 日目（CAST INTEGER）
          5. race_bango: レース番号（CAST INTEGER）
          6. umaban: 馬番（CAST INTEGER, bac以外）

        ■ パディング差異:
          JRA-VAN: kaisai_kai='02'(2桁ゼロパディング), kaisai_nichime='05'(2桁)
          JRDB:    kaisai_kai='2'(パディングなし1桁),   kaisai_nichime='5'(1桁)
          → CAST(TRIM(...) AS INTEGER)で吸収

        ■ bacテーブル注意:
          bacはレース単位（馬番なし）のため、umaban条件を除外。
          またbacのkaisai_nen/kaisai_tsukihiは固定長パースずれの可能性あり。
    """
    # -----------------------------------------------------------------------
    # JOINキー設計（2026-04-01 根本修正）
    #
    # 旧: race_shikonen = YYMMDD として結合 → 0%マッチ（フォーマット不一致）
    # 新: race_shikonenの先頭2桁(YY)で年を絞り、
    #     kaisai_kai + kaisai_nichime + race_bango + umaban で結合
    #
    # race_shikonen = YY(2) + 開催回(2) + 日目(2) であることが診断で確定。
    # PC-KEIBAがJRDB固定長ファイルをパースした結果。
    # -----------------------------------------------------------------------
    query = """
    SELECT
        se.*,
        ra.babajotai_code_shiba,
        ra.babajotai_code_dirt,
        ra.tenko_code,
        ra.kyori,
        ra.track_code,
        kyi.idm,
        kyi.sogo_shisu,
        kyi.agari_shisu,
        kyi.pace_shisu,
        kyi.kyori_tekisei_code,
        kyi.tekisei_code_shiba AS course_tekisei,
        kyi.tekisei_code_omo AS baba_tekisei,
        kyi.chokyo_yajirushi_code,
        kyi.soho,
        kyi.kishu_shisu,
        kyi.chokyo_shisu,
        kyi.kyusha_shisu,
        cyb.chokyo_hyoka,
        joa.ls_shisu,
        bac.juryo_shubetsu_code,
        -- 日付を統一フォーマットで算出
        (se.kaisai_nen || se.kaisai_tsukihi) AS race_date
    FROM jvd_se AS se
    LEFT JOIN jvd_ra AS ra
        ON se.keibajo_code = ra.keibajo_code
        AND se.kaisai_nen = ra.kaisai_nen
        AND se.kaisai_tsukihi = ra.kaisai_tsukihi
        AND se.kaisai_kai = ra.kaisai_kai
        AND se.kaisai_nichime = ra.kaisai_nichime
        AND se.race_bango = ra.race_bango
    -- =====================================================================
    -- JRDB JOIN: race_shikonenの先頭2桁(YY)で年を絞り、
    --   kaisai_kai + kaisai_nichime + race_bango + umaban で結合
    -- race_shikonen = YY(2) + 開催回(2) + 日目(2) ≠ YYMMDD
    -- =====================================================================
    LEFT JOIN jrd_kyi AS kyi
        ON TRIM(se.keibajo_code) = TRIM(kyi.keibajo_code)
        AND SUBSTRING(se.kaisai_nen, 3, 2) = SUBSTRING(kyi.race_shikonen, 1, 2)
        AND CAST(NULLIF(TRIM(se.kaisai_kai), '') AS INTEGER)
            = CAST(NULLIF(TRIM(kyi.kaisai_kai), '') AS INTEGER)
        AND CAST(NULLIF(TRIM(se.kaisai_nichime), '') AS INTEGER)
            = CAST(NULLIF(TRIM(kyi.kaisai_nichime), '') AS INTEGER)
        AND CAST(NULLIF(TRIM(se.race_bango), '') AS INTEGER)
            = CAST(NULLIF(TRIM(kyi.race_bango), '') AS INTEGER)
        AND CAST(NULLIF(TRIM(se.umaban), '') AS INTEGER)
            = CAST(NULLIF(TRIM(kyi.umaban), '') AS INTEGER)
    LEFT JOIN jrd_cyb AS cyb
        ON TRIM(se.keibajo_code) = TRIM(cyb.keibajo_code)
        AND SUBSTRING(se.kaisai_nen, 3, 2) = SUBSTRING(cyb.race_shikonen, 1, 2)
        AND CAST(NULLIF(TRIM(se.kaisai_kai), '') AS INTEGER)
            = CAST(NULLIF(TRIM(cyb.kaisai_kai), '') AS INTEGER)
        AND CAST(NULLIF(TRIM(se.kaisai_nichime), '') AS INTEGER)
            = CAST(NULLIF(TRIM(cyb.kaisai_nichime), '') AS INTEGER)
        AND CAST(NULLIF(TRIM(se.race_bango), '') AS INTEGER)
            = CAST(NULLIF(TRIM(cyb.race_bango), '') AS INTEGER)
        AND CAST(NULLIF(TRIM(se.umaban), '') AS INTEGER)
            = CAST(NULLIF(TRIM(cyb.umaban), '') AS INTEGER)
    LEFT JOIN jrd_joa AS joa
        ON TRIM(se.keibajo_code) = TRIM(joa.keibajo_code)
        AND SUBSTRING(se.kaisai_nen, 3, 2) = SUBSTRING(joa.race_shikonen, 1, 2)
        AND CAST(NULLIF(TRIM(se.kaisai_kai), '') AS INTEGER)
            = CAST(NULLIF(TRIM(joa.kaisai_kai), '') AS INTEGER)
        AND CAST(NULLIF(TRIM(se.kaisai_nichime), '') AS INTEGER)
            = CAST(NULLIF(TRIM(joa.kaisai_nichime), '') AS INTEGER)
        AND CAST(NULLIF(TRIM(se.race_bango), '') AS INTEGER)
            = CAST(NULLIF(TRIM(joa.race_bango), '') AS INTEGER)
        AND CAST(NULLIF(TRIM(se.umaban), '') AS INTEGER)
            = CAST(NULLIF(TRIM(joa.umaban), '') AS INTEGER)
    LEFT JOIN jrd_bac AS bac
        ON TRIM(se.keibajo_code) = TRIM(bac.keibajo_code)
        AND SUBSTRING(se.kaisai_nen, 3, 2) = SUBSTRING(bac.race_shikonen, 1, 2)
        AND CAST(NULLIF(TRIM(se.kaisai_kai), '') AS INTEGER)
            = CAST(NULLIF(TRIM(bac.kaisai_kai), '') AS INTEGER)
        AND CAST(NULLIF(TRIM(se.kaisai_nichime), '') AS INTEGER)
            = CAST(NULLIF(TRIM(bac.kaisai_nichime), '') AS INTEGER)
        AND CAST(NULLIF(TRIM(se.race_bango), '') AS INTEGER)
            = CAST(NULLIF(TRIM(bac.race_bango), '') AS INTEGER)
    WHERE
        (se.kaisai_nen || se.kaisai_tsukihi) >= %(date_from)s
        AND (se.kaisai_nen || se.kaisai_tsukihi) <= %(date_to)s
    ORDER BY race_date, se.keibajo_code, se.race_bango, se.umaban
    """

    conn = get_connection(config)
    try:
        df = pd.read_sql_query(query, conn, params={"date_from": date_from, "date_to": date_to})
    finally:
        conn.close()

    return df


def diagnose_join_keys(config: Optional[DBConfig] = None) -> str:
    """
    JRA-VAN (jvd_se) と JRDB (jrd_kyi) のJOINキーフォーマットを診断する。

    Returns:
        診断結果の文字列レポート
    """
    query = """
    SELECT
        '=== jvd_se (JRA-VAN) サンプル ===' AS section,
        se.keibajo_code,
        se.kaisai_nen,
        se.kaisai_tsukihi,
        se.kaisai_kai,
        se.kaisai_nichime,
        se.race_bango,
        se.umaban,
        LENGTH(se.keibajo_code) AS len_keibajo,
        LENGTH(se.kaisai_kai) AS len_kai,
        LENGTH(se.kaisai_nichime) AS len_nichime,
        LENGTH(se.race_bango) AS len_race,
        LENGTH(se.umaban) AS len_umaban,
        (SUBSTRING(se.kaisai_nen, 3, 2) || se.kaisai_tsukihi) AS computed_shikonen
    FROM jvd_se AS se
    WHERE (se.kaisai_nen || se.kaisai_tsukihi) >= '20240101'
    LIMIT 5
    """
    query_kyi = """
    SELECT
        '=== jrd_kyi (JRDB) サンプル ===' AS section,
        kyi.keibajo_code,
        kyi.race_shikonen,
        kyi.kaisai_kai,
        kyi.kaisai_nichime,
        kyi.race_bango,
        kyi.umaban,
        LENGTH(kyi.keibajo_code) AS len_keibajo,
        LENGTH(kyi.kaisai_kai) AS len_kai,
        LENGTH(kyi.kaisai_nichime) AS len_nichime,
        LENGTH(kyi.race_bango) AS len_race,
        LENGTH(kyi.umaban) AS len_umaban
    FROM jrd_kyi AS kyi
    LIMIT 5
    """
    query_count = """
    SELECT
        (SELECT COUNT(*) FROM jvd_se) AS se_count,
        (SELECT COUNT(*) FROM jrd_kyi) AS kyi_count,
        (SELECT COUNT(*) FROM jrd_cyb) AS cyb_count,
        (SELECT COUNT(*) FROM jrd_joa) AS joa_count,
        (SELECT COUNT(*) FROM jrd_bac) AS bac_count
    """

    conn = get_connection(config)
    lines = []
    try:
        # テーブル行数
        df_count = pd.read_sql_query(query_count, conn)
        lines.append("  --- テーブル行数 ---")
        for col in df_count.columns:
            lines.append(f"    {col}: {int(df_count[col].iloc[0]):,}")

        # JRA-VAN サンプル
        df_se = pd.read_sql_query(query, conn)
        lines.append("")
        lines.append("  --- jvd_se JOINキーサンプル ---")
        for _, row in df_se.iterrows():
            lines.append(
                f"    keibajo={row['keibajo_code']!r}(len={row['len_keibajo']}), "
                f"nen={row['kaisai_nen']!r}, tsukihi={row['kaisai_tsukihi']!r}, "
                f"kai={row['kaisai_kai']!r}(len={row['len_kai']}), "
                f"nichime={row['kaisai_nichime']!r}(len={row['len_nichime']}), "
                f"race={row['race_bango']!r}(len={row['len_race']}), "
                f"uma={row['umaban']!r}(len={row['len_umaban']}), "
                f"computed_shikonen={row['computed_shikonen']!r}"
            )

        # JRDB サンプル
        df_kyi = pd.read_sql_query(query_kyi, conn)
        lines.append("")
        lines.append("  --- jrd_kyi JOINキーサンプル ---")
        for _, row in df_kyi.iterrows():
            lines.append(
                f"    keibajo={row['keibajo_code']!r}(len={row['len_keibajo']}), "
                f"shikonen={row['race_shikonen']!r}, "
                f"kai={row['kaisai_kai']!r}(len={row['len_kai']}), "
                f"nichime={row['kaisai_nichime']!r}(len={row['len_nichime']}), "
                f"race={row['race_bango']!r}(len={row['len_race']}), "
                f"uma={row['umaban']!r}(len={row['len_umaban']})"
            )

        # --- JRDBテーブルの日付範囲 ---
        lines.append("")
        lines.append("  --- JRDBテーブル日付範囲 ---")
        for tbl in ["jrd_kyi", "jrd_cyb", "jrd_joa", "jrd_bac"]:
            try:
                df_range = pd.read_sql_query(
                    f"SELECT MIN(race_shikonen) AS min_date, MAX(race_shikonen) AS max_date FROM {tbl}",
                    conn,
                )
                lines.append(
                    f"    {tbl}: {df_range['min_date'].iloc[0]} 〜 {df_range['max_date'].iloc[0]}"
                )
            except Exception as e:
                lines.append(f"    {tbl}: エラー ({e})")

        # --- 新JOINキーテスト: YY年一致 + kaisai_kai + kaisai_nichime ---
        # race_shikonen = YY(2)+回(2)+日目(2) なので、
        # 先頭2桁のYYをse.kaisai_nen(3,2)と一致させ、残りはCAST(INTEGER)で結合
        lines.append("")
        lines.append("  --- 新JOINキーテスト (race_shikonen非依存) ---")

        # kyi テスト
        query_new_kyi = """
        SELECT COUNT(*) AS match_count
        FROM jvd_se AS se
        INNER JOIN jrd_kyi AS kyi
            ON TRIM(se.keibajo_code) = TRIM(kyi.keibajo_code)
            AND SUBSTRING(se.kaisai_nen, 3, 2) = SUBSTRING(kyi.race_shikonen, 1, 2)
            AND CAST(NULLIF(TRIM(se.kaisai_kai), '') AS INTEGER)
                = CAST(NULLIF(TRIM(kyi.kaisai_kai), '') AS INTEGER)
            AND CAST(NULLIF(TRIM(se.kaisai_nichime), '') AS INTEGER)
                = CAST(NULLIF(TRIM(kyi.kaisai_nichime), '') AS INTEGER)
            AND CAST(NULLIF(TRIM(se.race_bango), '') AS INTEGER)
                = CAST(NULLIF(TRIM(kyi.race_bango), '') AS INTEGER)
            AND CAST(NULLIF(TRIM(se.umaban), '') AS INTEGER)
                = CAST(NULLIF(TRIM(kyi.umaban), '') AS INTEGER)
        """
        df_new_kyi = pd.read_sql_query(query_new_kyi, conn)
        kyi_new = int(df_new_kyi["match_count"].iloc[0])
        lines.append(f"    kyi 新JOIN全期間マッチ: {kyi_new:,}")

        # cyb テスト（2024年1月）
        query_new_cyb = """
        SELECT COUNT(*) AS match_count
        FROM jvd_se AS se
        INNER JOIN jrd_cyb AS cyb
            ON TRIM(se.keibajo_code) = TRIM(cyb.keibajo_code)
            AND SUBSTRING(se.kaisai_nen, 3, 2) = SUBSTRING(cyb.race_shikonen, 1, 2)
            AND CAST(NULLIF(TRIM(se.kaisai_kai), '') AS INTEGER)
                = CAST(NULLIF(TRIM(cyb.kaisai_kai), '') AS INTEGER)
            AND CAST(NULLIF(TRIM(se.kaisai_nichime), '') AS INTEGER)
                = CAST(NULLIF(TRIM(cyb.kaisai_nichime), '') AS INTEGER)
            AND CAST(NULLIF(TRIM(se.race_bango), '') AS INTEGER)
                = CAST(NULLIF(TRIM(cyb.race_bango), '') AS INTEGER)
            AND CAST(NULLIF(TRIM(se.umaban), '') AS INTEGER)
                = CAST(NULLIF(TRIM(cyb.umaban), '') AS INTEGER)
        WHERE (se.kaisai_nen || se.kaisai_tsukihi) >= '20240101'
            AND (se.kaisai_nen || se.kaisai_tsukihi) <= '20240131'
        """
        df_new_cyb = pd.read_sql_query(query_new_cyb, conn)
        cyb_new = int(df_new_cyb["match_count"].iloc[0])
        lines.append(f"    cyb 新JOIN 2024年1月マッチ: {cyb_new:,}")

        # cyb テスト（全期間）
        query_new_cyb_all = """
        SELECT COUNT(*) AS match_count
        FROM jvd_se AS se
        INNER JOIN jrd_cyb AS cyb
            ON TRIM(se.keibajo_code) = TRIM(cyb.keibajo_code)
            AND SUBSTRING(se.kaisai_nen, 3, 2) = SUBSTRING(cyb.race_shikonen, 1, 2)
            AND CAST(NULLIF(TRIM(se.kaisai_kai), '') AS INTEGER)
                = CAST(NULLIF(TRIM(cyb.kaisai_kai), '') AS INTEGER)
            AND CAST(NULLIF(TRIM(se.kaisai_nichime), '') AS INTEGER)
                = CAST(NULLIF(TRIM(cyb.kaisai_nichime), '') AS INTEGER)
            AND CAST(NULLIF(TRIM(se.race_bango), '') AS INTEGER)
                = CAST(NULLIF(TRIM(cyb.race_bango), '') AS INTEGER)
            AND CAST(NULLIF(TRIM(se.umaban), '') AS INTEGER)
                = CAST(NULLIF(TRIM(cyb.umaban), '') AS INTEGER)
        """
        df_new_cyb_all = pd.read_sql_query(query_new_cyb_all, conn)
        cyb_new_all = int(df_new_cyb_all["match_count"].iloc[0])
        lines.append(f"    cyb 新JOIN全期間マッチ: {cyb_new_all:,}")

        # bac テスト（レース単位 — umabanなし）
        query_new_bac = """
        SELECT COUNT(*) AS match_count
        FROM jvd_se AS se
        INNER JOIN jrd_bac AS bac
            ON TRIM(se.keibajo_code) = TRIM(bac.keibajo_code)
            AND SUBSTRING(se.kaisai_nen, 3, 2) = SUBSTRING(bac.race_shikonen, 1, 2)
            AND CAST(NULLIF(TRIM(se.kaisai_kai), '') AS INTEGER)
                = CAST(NULLIF(TRIM(bac.kaisai_kai), '') AS INTEGER)
            AND CAST(NULLIF(TRIM(se.kaisai_nichime), '') AS INTEGER)
                = CAST(NULLIF(TRIM(bac.kaisai_nichime), '') AS INTEGER)
            AND CAST(NULLIF(TRIM(se.race_bango), '') AS INTEGER)
                = CAST(NULLIF(TRIM(bac.race_bango), '') AS INTEGER)
        WHERE (se.kaisai_nen || se.kaisai_tsukihi) >= '20240101'
            AND (se.kaisai_nen || se.kaisai_tsukihi) <= '20240131'
        """
        df_new_bac = pd.read_sql_query(query_new_bac, conn)
        bac_new = int(df_new_bac["match_count"].iloc[0])
        lines.append(f"    bac 新JOIN 2024年1月マッチ: {bac_new:,}")

        # 期待値の表示
        lines.append("")
        lines.append("  --- 期待値 ---")
        lines.append("    kyi: 491,176行 → 全マッチなら ~491,176")
        lines.append("    cyb: 491,741行 → 全マッチなら ~491,741")
        lines.append("    bac: 35,229行 → レース数 x 出走数 なら ~280万の一部")

    except Exception as e:
        lines.append(f"  診断エラー: {e}")
    finally:
        conn.close()

    return "\n".join(lines)


def convert_numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    文字列型カラムのうち数値系を安全に変換する。

    Args:
        df: load_base_race_data()の出力DataFrame

    Returns:
        数値変換済みDataFrame（変換失敗はNaN）
    """
    numeric_cols = [
        "umaban", "kakutei_chakujun", "tansho_odds", "tansho_ninkijun",
        "fukusho_odds", "bataiju", "barei",
        "idm", "sogo_shisu", "agari_shisu", "pace_shisu",
        "kishu_shisu", "chokyo_shisu", "kyusha_shisu", "ls_shisu",
        "kyori",
    ]

    for col in numeric_cols:
        if col in df.columns:
            df[col] = safe_to_numeric(df[col])

    return df

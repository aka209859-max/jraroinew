"""
data_loader v2: jrd_*_fixed テーブルを使用する新JOIN方式

PC-KEIBAのパースずれ問題を回避した jrd_kyi_fixed / jrd_cyb_fixed /
jrd_bac_fixed / jrd_joa_fixed テーブルを使い、8byte JRDBレースキー
ベースの確定的JOINを実行する。

非fixedテーブル (jrd_sed / jrd_tyb / jrd_kab / jrd_skb / jrd_kka / jrd_ukc) は
YYMMDD形式の race_shikonen をJOINキーとして使用する。

複勝オッズ: jvd_hr（払戻テーブル）から馬番ベースで逆算取得。
  jvd_se には fukusho_odds カラムが存在しないため、
  jvd_hr.haraimodoshi_fukusho_{1-5}{a,b} を UNPIVOT して
  馬番マッチングで結合する。

期待マッチ率: 95-100%（旧方式の42%から劇的改善）

使い分け:
  - load_base_race_data_v2(): jrd_*_fixed テーブル使用（推奨）
  - load_base_race_data():    旧 jrd_* テーブル使用（フォールバック）
"""
from typing import Optional

import pandas as pd

from backend.config.db import DBConfig, get_connection
from backend.engine.data_loader import safe_to_numeric, convert_numeric_columns


# =============================================================================
# JRA場コード（01-10）フィルタ
# jvd_seにはNAR（地方競馬）データが混在しているが、JRDBはJRAのみ
# =============================================================================
JRA_KEIBAJO_CODES = "('01','02','03','04','05','06','07','08','09','10')"

# =============================================================================
# jvd_hr（払戻テーブル）から複勝オッズをUNPIVOTするSQL
# haraimodoshi_fukusho_Xa = 馬番, _Xb = 払戻金額(100円あたり), _Xc = 人気
# 例: 馬番 '14', 金額 '000000230' → オッズ 2.3 (= 230 / 100)
# 最大5着分 (X=1..5) を UNION ALL で1テーブルに展開
# =============================================================================
_FUKUSHO_UNPIVOT_TEMPLATE = """
    SELECT
        hr.keibajo_code,
        hr.kaisai_nen,
        hr.kaisai_tsukihi,
        hr.kaisai_kai,
        hr.kaisai_nichime,
        hr.race_bango,
        TRIM(hr.haraimodoshi_fukusho_{n}a) AS umaban,
        CAST(
            NULLIF(TRIM(hr.haraimodoshi_fukusho_{n}b), '') AS NUMERIC
        ) / 100.0 AS fukusho_odds
    FROM jvd_hr AS hr
    WHERE TRIM(hr.haraimodoshi_fukusho_{n}a) != ''
      AND TRIM(hr.haraimodoshi_fukusho_{n}a) != '00'
      AND TRIM(hr.haraimodoshi_fukusho_{n}b) != ''
      AND TRIM(hr.haraimodoshi_fukusho_{n}b) != '000000000'
"""


def _build_fukusho_unpivot_cte() -> str:
    """jvd_hr から複勝オッズを UNPIVOT する CTE SQL を生成する。"""
    unions = []
    for i in range(1, 6):  # 1着〜5着分
        unions.append(_FUKUSHO_UNPIVOT_TEMPLATE.format(n=i))
    return "    UNION ALL\n".join(unions)


# =============================================================================
# JRA-VAN → JRDB 8byte レースキー合成SQL式
# =============================================================================
JVAN_TO_JRDB_RACE_KEY8 = """
    TRIM(se.keibajo_code)
    || SUBSTRING(se.kaisai_nen, 3, 2)
    || CAST(CAST(NULLIF(TRIM(se.kaisai_kai), '') AS INTEGER) AS TEXT)
    || CASE
        WHEN CAST(NULLIF(TRIM(se.kaisai_nichime), '') AS INTEGER) <= 9
            THEN CAST(CAST(NULLIF(TRIM(se.kaisai_nichime), '') AS INTEGER) AS TEXT)
        WHEN CAST(NULLIF(TRIM(se.kaisai_nichime), '') AS INTEGER) = 10 THEN 'a'
        WHEN CAST(NULLIF(TRIM(se.kaisai_nichime), '') AS INTEGER) = 11 THEN 'b'
        WHEN CAST(NULLIF(TRIM(se.kaisai_nichime), '') AS INTEGER) = 12 THEN 'c'
        ELSE CAST(CAST(NULLIF(TRIM(se.kaisai_nichime), '') AS INTEGER) AS TEXT)
       END
    || LPAD(CAST(CAST(NULLIF(TRIM(se.race_bango), '') AS INTEGER) AS TEXT), 2, '0')
"""

# =============================================================================
# JRA-VAN → JRDB race_shikonen (YYMMDD, 6文字) 合成式
# 非fixedテーブル (jrd_sed / jrd_tyb / jrd_skb / jrd_kka / jrd_kab) のJOINに使用
# =============================================================================
JVAN_TO_JRDB_RACE_SHIKONEN = "SUBSTRING(se.kaisai_nen, 3, 2) || se.kaisai_tsukihi"

# race_bango を 2桁0パディングに変換（jrd_sed等のJOINキー用）
JVAN_RACE_BANGO_PADDED = (
    "LPAD(CAST(CAST(NULLIF(TRIM(se.race_bango), '') AS INTEGER) AS TEXT), 2, '0')"
)


def _check_fixed_tables_exist(conn) -> bool:
    """jrd_*_fixed テーブルが存在するか確認する。"""
    query = """
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_name IN ('jrd_kyi_fixed', 'jrd_cyb_fixed', 'jrd_bac_fixed', 'jrd_joa_fixed')
    """
    try:
        df = pd.read_sql_query(query, conn)
        count = int(df.iloc[0, 0])
        return count >= 4
    except Exception:
        return False


def load_base_race_data_v2(
    date_from: str,
    date_to: str,
    config: Optional[DBConfig] = None,
) -> pd.DataFrame:
    """
    jrd_*_fixed テーブルを使用してベースデータを取得する（v2）。

    JOINキー:
      - jrd_kyi_fixed / jrd_cyb_fixed / jrd_bac_fixed / jrd_joa_fixed:
            JRA-VAN側から8byte JRDBレースキーを合成し、jrdb_race_key8 と直接マッチング
      - jrd_sed / jrd_tyb / jrd_skb / jrd_kka:
            YYMMDD形式の race_shikonen + keibajo_code + race_bango + umaban でマッチング
      - jrd_kab:
            YYMMDD形式の race_shikonen + keibajo_code でマッチング（レースデー単位）
      - jrd_ukc:
            ketto_toroku_bango（馬個体番号）でマッチング

    複勝オッズ: jvd_hr（払戻テーブル）から UNPIVOT して取得。

    ■ 期待マッチ率: 95-100%
    """
    # 複勝オッズ UNPIVOT CTE
    fukusho_cte = _build_fukusho_unpivot_cte()

    query = f"""
    WITH fukusho_pay AS (
        {fukusho_cte}
    )
    SELECT
        se.*,
        -- RA（天候・馬場）
        ra.babajotai_code_shiba,
        ra.babajotai_code_dirt,
        ra.tenko_code,
        ra.kyori AS ra_kyori,
        ra.track_code,
        -- =====================================================================
        -- KYI_FIXED（前日指数・予測データ）
        -- =====================================================================
        kyi.idm,
        kyi.sogo_shisu,
        kyi.kishu_shisu,
        kyi.agari_shisu,
        kyi.pace_shisu,
        kyi.ten_shisu,
        kyi.ichi_shisu,
        kyi.kyakushitsu,
        kyi.kyori_tekisei,
        kyi.kyori_tekisei_2,
        kyi.shiba_tekisei_code,
        kyi.da_tekisei_code,
        kyi.omo_tekisei_code,
        kyi.chokyo_yajirushi_code,
        kyi.soho,
        kyi.chokyo_shisu,
        kyi.kyusha_shisu,
        kyi.blinker,
        kyi.kyusha_rank,
        -- =====================================================================
        -- CYB_FIXED（調教データ）
        -- =====================================================================
        cyb.chokyo_hyoka,
        cyb.chokyo_type,
        cyb.oikiri_shisu,
        cyb.shiage_shisu,
        cyb.chokyo_ryo_hyoka,
        cyb.shiage_shisu_henka,
        -- =====================================================================
        -- JOA_FIXED（LS・CID指数）
        -- =====================================================================
        joa.ls_shisu,
        joa.ls_hyoka,
        joa.odds_shisu AS joa_odds_shisu,
        -- =====================================================================
        -- BAC_FIXED（レース基本情報）
        -- =====================================================================
        bac.juryo_shubetsu_code,
        bac.kyori AS bac_kyori,
        bac.shiba_da_shogai_code,
        bac.migi_hidari,
        bac.uchi_soto,
        bac.shubetsu,
        bac.jouken,
        bac.grade,
        bac.tosu,
        bac.course,
        bac.kaisai_kubun AS bac_kaisai_kubun,
        -- =====================================================================
        -- JRD_SED（確定成績データ）
        -- =====================================================================
        sed.idm         AS sed_idm,
        sed.soten,
        sed.babasa,
        sed.pace,
        sed.deokure,
        sed.ichidori,
        sed.furi,
        sed.ten_shisu   AS sed_ten_shisu,
        sed.agari_shisu AS sed_agari_shisu,
        sed.pace_shisu  AS sed_pace_shisu,
        sed.race_p_shisu,
        sed.race_pace,
        sed.uma_pace,
        sed.kyakushitsu_code,
        sed.course_dori_code,
        sed.joshodo_code,
        sed.class_code,
        sed.batai_code  AS sed_batai_code,
        sed.kehai_code  AS sed_kehai_code,
        sed.kohan_3f    AS sed_kohan_3f,
        sed.zenhan_3f_taimu,
        sed.haraimodoshi_tansho,
        sed.haraimodoshi_fukusho,
        sed.bataiju_zogen AS sed_bataiju_zogen,
        sed.odds_fukusho  AS sed_odds_fukusho,
        -- =====================================================================
        -- JRD_TYB（直前情報）
        -- =====================================================================
        tyb.idm              AS tyb_idm,
        tyb.kishu_shisu      AS tyb_kishu_shisu,
        tyb.joho_shisu,
        tyb.odds_shisu       AS tyb_odds_shisu,
        tyb.paddock_shisu,
        tyb.sogo_shisu       AS tyb_sogo_shisu,
        tyb.batai_code       AS tyb_batai_code,
        tyb.kehai_code       AS tyb_kehai_code,
        tyb.odds_fukusho     AS tyb_odds_fukusho,
        tyb.odds_shirushi,
        tyb.paddock_shirushi,
        tyb.chokuzen_sogo_shirushi,
        -- =====================================================================
        -- JRD_KAB（競馬場・馬場状態 レースデー単位）
        -- =====================================================================
        kab.babasa_shiba,
        kab.babasa_dirt,
        kab.renzoku_nannichime,
        kab.shiba_shurui,
        kab.chukan_kosuiryo,
        -- =====================================================================
        -- JRD_SKB（馬体・馬具）
        -- =====================================================================
        skb.tokki_code,
        skb.bagu_code,
        skb.sogo            AS skb_sogo,
        skb.hidarimae,
        skb.migimae,
        skb.hidariushiro,
        skb.migiushiro,
        skb.hami,
        skb.bandage,
        skb.teitetsu,
        skb.hizume_jotai,
        skb.soe,
        skb.kotsuryu,
        -- =====================================================================
        -- JRD_KKA（過去成績参照）
        -- =====================================================================
        kka.jra,
        kka.koryu,
        kka.shiba_dirt,
        kka.shiba_dirt_kyori,
        kka.torakku_kyori,
        kka.rotation,
        kka.mawari,
        kka.kishu,
        kka.ryo,
        kka.yayaomo,
        kka.omo,
        kka.pace_s,
        kka.pace_m,
        kka.pace_h,
        kka.kisetsu,
        kka.waku,
        kka.kishu_kyori,
        kka.kishu_track,
        kka.kishu_chokyoshi,
        kka.kishu_banushi,
        kka.kishu_blinker,
        kka.chokyoshi_banushi,
        -- =====================================================================
        -- JRD_UKC（馬個体・血統）
        -- =====================================================================
        ukc.bamei_chichi,
        ukc.bamei_haha,
        ukc.bamei_hahachichi,
        ukc.keito_code_chichi,
        ukc.keito_code_hahachichi,
        ukc.moshoku_code    AS ukc_moshoku_code,
        -- =====================================================================
        -- 複勝オッズ: jvd_hr（払戻テーブル）からUNPIVOT結合
        -- =====================================================================
        fp.fukusho_odds,
        -- 日付
        (se.kaisai_nen || se.kaisai_tsukihi) AS race_date,
        -- 合成レースキー（デバッグ用）
        ({JVAN_TO_JRDB_RACE_KEY8}) AS synth_race_key8
    FROM jvd_se AS se
    -- JRA-VAN内JOIN（問題なし）
    LEFT JOIN jvd_ra AS ra
        ON se.keibajo_code = ra.keibajo_code
        AND se.kaisai_nen = ra.kaisai_nen
        AND se.kaisai_tsukihi = ra.kaisai_tsukihi
        AND se.kaisai_kai = ra.kaisai_kai
        AND se.kaisai_nichime = ra.kaisai_nichime
        AND se.race_bango = ra.race_bango
    -- =================================================================
    -- 複勝オッズJOIN: jvd_hr UNPIVOT → レース×馬番で結合
    -- =================================================================
    LEFT JOIN fukusho_pay AS fp
        ON se.keibajo_code = fp.keibajo_code
        AND se.kaisai_nen = fp.kaisai_nen
        AND se.kaisai_tsukihi = fp.kaisai_tsukihi
        AND se.kaisai_kai = fp.kaisai_kai
        AND se.kaisai_nichime = fp.kaisai_nichime
        AND se.race_bango = fp.race_bango
        AND TRIM(se.umaban) = fp.umaban
    -- =====================================================================
    -- JRDB JOIN v2: 8byte race_key ベース（PC-KEIBAバイパス）
    -- =====================================================================
    LEFT JOIN jrd_kyi_fixed AS kyi
        ON ({JVAN_TO_JRDB_RACE_KEY8}) = kyi.jrdb_race_key8
        AND TRIM(se.umaban) = TRIM(kyi.umaban)
    LEFT JOIN jrd_cyb_fixed AS cyb
        ON ({JVAN_TO_JRDB_RACE_KEY8}) = cyb.jrdb_race_key8
        AND TRIM(se.umaban) = TRIM(cyb.umaban)
    LEFT JOIN jrd_joa_fixed AS joa
        ON ({JVAN_TO_JRDB_RACE_KEY8}) = joa.jrdb_race_key8
        AND TRIM(se.umaban) = TRIM(joa.umaban)
    LEFT JOIN jrd_bac_fixed AS bac
        ON ({JVAN_TO_JRDB_RACE_KEY8}) = bac.jrdb_race_key8
    -- =====================================================================
    -- JRDB JOIN: race_shikonen (YYMMDD) ベース（非fixedテーブル）
    -- =====================================================================
    LEFT JOIN jrd_sed AS sed
        ON ({JVAN_TO_JRDB_RACE_SHIKONEN}) = TRIM(sed.race_shikonen)
        AND TRIM(se.keibajo_code) = TRIM(sed.keibajo_code)
        AND ({JVAN_RACE_BANGO_PADDED}) = TRIM(sed.race_bango)
        AND TRIM(se.umaban) = TRIM(sed.umaban)
    LEFT JOIN jrd_tyb AS tyb
        ON ({JVAN_TO_JRDB_RACE_SHIKONEN}) = TRIM(tyb.race_shikonen)
        AND TRIM(se.keibajo_code) = TRIM(tyb.keibajo_code)
        AND ({JVAN_RACE_BANGO_PADDED}) = TRIM(tyb.race_bango)
        AND TRIM(se.umaban) = TRIM(tyb.umaban)
    LEFT JOIN jrd_skb AS skb
        ON ({JVAN_TO_JRDB_RACE_SHIKONEN}) = TRIM(skb.race_shikonen)
        AND TRIM(se.keibajo_code) = TRIM(skb.keibajo_code)
        AND ({JVAN_RACE_BANGO_PADDED}) = TRIM(skb.race_bango)
        AND TRIM(se.umaban) = TRIM(skb.umaban)
    LEFT JOIN jrd_kka AS kka
        ON ({JVAN_TO_JRDB_RACE_SHIKONEN}) = TRIM(kka.race_shikonen)
        AND TRIM(se.keibajo_code) = TRIM(kka.keibajo_code)
        AND ({JVAN_RACE_BANGO_PADDED}) = TRIM(kka.race_bango)
        AND TRIM(se.umaban) = TRIM(kka.umaban)
    -- kab はレースデー単位（umaban/race_bango なし）
    LEFT JOIN jrd_kab AS kab
        ON ({JVAN_TO_JRDB_RACE_SHIKONEN}) = TRIM(kab.race_shikonen)
        AND TRIM(se.keibajo_code) = TRIM(kab.keibajo_code)
    -- ukc は馬個体単位（ketto_toroku_bango でJOIN）
    LEFT JOIN jrd_ukc AS ukc
        ON TRIM(se.ketto_toroku_bango) = TRIM(ukc.ketto_toroku_bango)
    WHERE
        (se.kaisai_nen || se.kaisai_tsukihi) >= '{date_from}'
        AND (se.kaisai_nen || se.kaisai_tsukihi) <= '{date_to}'
        AND TRIM(se.keibajo_code) IN {JRA_KEIBAJO_CODES}
    ORDER BY race_date, se.keibajo_code, se.race_bango, se.umaban
    """

    conn = get_connection(config)
    try:
        # fixedテーブルの存在確認
        if not _check_fixed_tables_exist(conn):
            raise RuntimeError(
                "jrd_*_fixed テーブルが存在しません。\n"
                "先にJRDBファイルをパース・インポートしてください:\n"
                "  py -3.12 -m roi_pipeline.ingest.jrdb_importer --import <JRDB_DIR>"
            )

        df = pd.read_sql_query(query, conn)
    finally:
        conn.close()

    return df


def diagnose_v2_join(
    date_from: str = "20240101",
    date_to: str = "20240131",
    config: Optional[DBConfig] = None,
) -> str:
    """
    v2 JOINの品質を診断する。

    Returns:
        診断レポート文字列
    """
    conn = get_connection(config)
    lines = []

    try:
        # テーブル存在確認
        if not _check_fixed_tables_exist(conn):
            return "ERROR: jrd_*_fixed テーブルが存在しません。"

        lines.append("=" * 60)
        lines.append("  v2 JOIN診断レポート")
        lines.append(f"  期間: {date_from} 〜 {date_to}")
        lines.append("=" * 60)

        # fixedテーブル（8byte race_key）
        fixed_tables = {
            "jrd_kyi_fixed": ("idm", True),
            "jrd_cyb_fixed": ("chokyo_hyoka", True),
            "jrd_joa_fixed": ("ls_shisu", True),
            "jrd_bac_fixed": ("juryo_shubetsu_code", False),
        }

        lines.append("\n  --- fixed テーブル (8byte race_key JOIN) ---")
        for table, (check_col, has_umaban) in fixed_tables.items():
            uma_join = f"AND TRIM(se.umaban) = TRIM(t.umaban)" if has_umaban else ""

            query = f"""
                SELECT
                    COUNT(*) AS total,
                    COUNT(t.{check_col}) AS matched,
                    ROUND(COUNT(t.{check_col})::NUMERIC / NULLIF(COUNT(*), 0) * 100, 2) AS pct
                FROM jvd_se se
                LEFT JOIN {table} t
                    ON ({JVAN_TO_JRDB_RACE_KEY8}) = t.jrdb_race_key8
                    {uma_join}
                WHERE (se.kaisai_nen || se.kaisai_tsukihi) >= '{date_from}'
                    AND (se.kaisai_nen || se.kaisai_tsukihi) <= '{date_to}'
                    AND TRIM(se.keibajo_code) IN {JRA_KEIBAJO_CODES}
            """

            try:
                df = pd.read_sql_query(query, conn)
                total = int(df["total"].iloc[0])
                matched = int(df["matched"].iloc[0])
                pct = float(df["pct"].iloc[0])

                status = "✅" if pct >= 90 else "⚠️" if pct >= 50 else "❌"
                lines.append(f"  {status} {table}: {matched:,}/{total:,} ({pct}%)")

            except Exception as e:
                lines.append(f"  ❌ {table}: ERROR - {e}")

        # race_shikonenベーステーブル
        shikonen_tables = {
            "jrd_sed": ("idm", True),
            "jrd_tyb": ("idm", True),
            "jrd_skb": ("tokki_code", True),
            "jrd_kka": ("jra", True),
        }

        lines.append("\n  --- race_shikonen テーブル (YYMMDD JOIN) ---")
        for table, (check_col, has_uma) in shikonen_tables.items():
            uma_cond = f"AND ({JVAN_RACE_BANGO_PADDED}) = TRIM(t.race_bango) AND TRIM(se.umaban) = TRIM(t.umaban)" if has_uma else ""

            query = f"""
                SELECT
                    COUNT(*) AS total,
                    COUNT(t.{check_col}) AS matched,
                    ROUND(COUNT(t.{check_col})::NUMERIC / NULLIF(COUNT(*), 0) * 100, 2) AS pct
                FROM jvd_se se
                LEFT JOIN {table} t
                    ON ({JVAN_TO_JRDB_RACE_SHIKONEN}) = TRIM(t.race_shikonen)
                    AND TRIM(se.keibajo_code) = TRIM(t.keibajo_code)
                    {uma_cond}
                WHERE (se.kaisai_nen || se.kaisai_tsukihi) >= '{date_from}'
                    AND (se.kaisai_nen || se.kaisai_tsukihi) <= '{date_to}'
                    AND TRIM(se.keibajo_code) IN {JRA_KEIBAJO_CODES}
            """

            try:
                df = pd.read_sql_query(query, conn)
                total = int(df["total"].iloc[0])
                matched = int(df["matched"].iloc[0])
                pct = float(df["pct"].iloc[0])

                status = "✅" if pct >= 90 else "⚠️" if pct >= 50 else "❌"
                lines.append(f"  {status} {table}: {matched:,}/{total:,} ({pct}%)")

            except Exception as e:
                lines.append(f"  ❌ {table}: ERROR - {e}")

        # kab (race-day level)
        lines.append("\n  --- kab (レースデー単位) ---")
        try:
            q = f"""
                SELECT
                    COUNT(*) AS total,
                    COUNT(kab.tenko_code) AS matched,
                    ROUND(COUNT(kab.tenko_code)::NUMERIC / NULLIF(COUNT(*), 0) * 100, 2) AS pct
                FROM jvd_se se
                LEFT JOIN jrd_kab kab
                    ON ({JVAN_TO_JRDB_RACE_SHIKONEN}) = TRIM(kab.race_shikonen)
                    AND TRIM(se.keibajo_code) = TRIM(kab.keibajo_code)
                WHERE (se.kaisai_nen || se.kaisai_tsukihi) >= '{date_from}'
                    AND (se.kaisai_nen || se.kaisai_tsukihi) <= '{date_to}'
                    AND TRIM(se.keibajo_code) IN {JRA_KEIBAJO_CODES}
            """
            df = pd.read_sql_query(q, conn)
            total = int(df["total"].iloc[0])
            matched = int(df["matched"].iloc[0])
            pct = float(df["pct"].iloc[0])
            status = "✅" if pct >= 90 else "⚠️" if pct >= 50 else "❌"
            lines.append(f"  {status} jrd_kab: {matched:,}/{total:,} ({pct}%)")
        except Exception as e:
            lines.append(f"  ❌ jrd_kab: ERROR - {e}")

        # --- 複勝オッズJOIN診断 ---
        lines.append("\n  --- 複勝オッズ (jvd_hr UNPIVOT) ---")
        try:
            fukusho_cte = _build_fukusho_unpivot_cte()
            fq = f"""
                WITH fukusho_pay AS (
                    {fukusho_cte}
                )
                SELECT
                    COUNT(*) AS total,
                    COUNT(fp.fukusho_odds) AS matched,
                    ROUND(COUNT(fp.fukusho_odds)::NUMERIC / NULLIF(COUNT(*), 0) * 100, 2) AS pct
                FROM jvd_se se
                LEFT JOIN fukusho_pay fp
                    ON se.keibajo_code = fp.keibajo_code
                    AND se.kaisai_nen = fp.kaisai_nen
                    AND se.kaisai_tsukihi = fp.kaisai_tsukihi
                    AND se.kaisai_kai = fp.kaisai_kai
                    AND se.kaisai_nichime = fp.kaisai_nichime
                    AND se.race_bango = fp.race_bango
                    AND TRIM(se.umaban) = fp.umaban
                WHERE (se.kaisai_nen || se.kaisai_tsukihi) >= '{date_from}'
                    AND (se.kaisai_nen || se.kaisai_tsukihi) <= '{date_to}'
                    AND TRIM(se.keibajo_code) IN {JRA_KEIBAJO_CODES}
            """
            df_f = pd.read_sql_query(fq, conn)
            total = int(df_f["total"].iloc[0])
            matched = int(df_f["matched"].iloc[0])
            pct = float(df_f["pct"].iloc[0])
            status = "✅" if pct >= 15 else "⚠️" if pct >= 5 else "❌"
            lines.append(f"  {status} fukusho_odds (jvd_hr): {matched:,}/{total:,} ({pct}%)")
            lines.append(f"      → 期待値: 約20-25% (3着以内の馬のみ値あり)")
        except Exception as e:
            lines.append(f"  ❌ fukusho_odds: ERROR - {e}")

        # fixedテーブル行数
        lines.append("\n  --- テーブル行数 ---")
        all_tables = list(fixed_tables.keys()) + list(shikonen_tables.keys()) + ["jrd_kab", "jrd_ukc", "jvd_hr"]
        for table in all_tables:
            try:
                df = pd.read_sql_query(f"SELECT COUNT(*) AS cnt FROM {table}", conn)
                cnt = int(df["cnt"].iloc[0])
                lines.append(f"    {table}: {cnt:,}")
            except Exception as e:
                lines.append(f"    {table}: ERROR - {e}")

    finally:
        conn.close()

    return "\n".join(lines)

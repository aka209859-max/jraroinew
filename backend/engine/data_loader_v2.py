"""
data_loader v2: jrd_*_fixed テーブルを使用する新JOIN方式

PC-KEIBAのパースずれ問題を回避した jrd_kyi_fixed / jrd_cyb_fixed /
jrd_bac_fixed / jrd_joa_fixed テーブルを使い、8byte JRDBレースキー
ベースの確定的JOINを実行する。

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
    
    JOINキー: JRA-VAN側から8byte JRDBレースキーを合成し、
    jrd_*_fixed.jrdb_race_key8 と直接マッチング。
    
    複勝オッズ: jvd_hr（払戻テーブル）から UNPIVOT して取得。
    jvd_se には fukusho_odds カラムが存在しないため、
    jvd_hr.haraimodoshi_fukusho_{1-5}b / 100.0 でオッズに変換し、
    馬番ベースで結合する。
    
    ■ JOIN方式（v2 — 8byte race_key ベース）:
      JRA-VAN: keibajo_code(2) + year_last2(2) + kai(1) + hex(nichime)(1) + race(2)
      JRDB:    jrdb_race_key8 カラム（パーサーが正確に生成）
    
      馬番: TRIM比較（KYI/CYB/JOA） or 不要（BAC）
    
    ■ 期待マッチ率: 95-100%
      旧方式（42%）→ PC-KEIBAの壊れたカラムをバイパスし、
      正しくパースされたデータで直接JOIN。
    
    Args:
        date_from: 開始日（YYYYMMDD形式）
        date_to: 終了日（YYYYMMDD形式）
        config: DB接続設定
    
    Returns:
        結合済みDataFrame（fukusho_odds カラム含む）
    """
    # 複勝オッズ UNPIVOT CTE
    fukusho_cte = _build_fukusho_unpivot_cte()

    query = f"""
    WITH fukusho_pay AS (
        {fukusho_cte}
    )
    SELECT
        se.*,
        ra.babajotai_code_shiba,
        ra.babajotai_code_dirt,
        ra.tenko_code,
        ra.kyori AS ra_kyori,
        ra.track_code,
        -- KYI (正しくパースされたデータ)
        kyi.idm,
        kyi.sogo_shisu,
        kyi.agari_shisu,
        kyi.pace_shisu,
        kyi.kyori_tekisei AS kyori_tekisei_code,
        kyi.shiba_tekisei_code AS course_tekisei,
        kyi.omo_tekisei_code AS baba_tekisei,
        kyi.chokyo_yajirushi_code,
        kyi.soho,
        kyi.kishu_shisu,
        kyi.chokyo_shisu,
        kyi.kyusha_shisu,
        -- CYB (正しくパースされたデータ)
        cyb.chokyo_hyoka,
        -- JOA (正しくパースされたデータ)
        joa.ls_shisu,
        -- BAC (正しくパースされたデータ)
        bac.juryo_shubetsu_code,
        bac.kyori AS bac_kyori,
        -- =================================================================
        -- 複勝オッズ: jvd_hr（払戻テーブル）からUNPIVOT結合
        -- haraimodoshi_fukusho_Xb / 100.0 でオッズ値に変換
        -- 複勝的中馬（3着以内）のみ値あり、それ以外はNULL
        -- =================================================================
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
    -- 複勝的中馬のみ行が存在する → LEFT JOINで非的中馬はNULL
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
    -- JRA-VAN側から合成した8byteキーと、パーサーが生成した正確なキーで結合
    -- 期待マッチ率: 95-100%
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
        
        # 各テーブルのJOINマッチ率
        tables = {
            "jrd_kyi_fixed": ("idm", True),
            "jrd_cyb_fixed": ("chokyo_hyoka", True),
            "jrd_joa_fixed": ("ls_shisu", True),
            "jrd_bac_fixed": ("juryo_shubetsu_code", False),
        }
        
        for table, (check_col, has_umaban) in tables.items():
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

        # --- 複勝オッズJOIN診断 ---
        lines.append("")
        lines.append("  --- 複勝オッズ (jvd_hr UNPIVOT) ---")
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
        lines.append("")
        lines.append("  --- fixed テーブル行数 ---")
        for table in tables:
            try:
                df = pd.read_sql_query(f"SELECT COUNT(*) AS cnt FROM {table}", conn)
                cnt = int(df["cnt"].iloc[0])
                lines.append(f"    {table}: {cnt:,}")
            except Exception as e:
                lines.append(f"    {table}: ERROR - {e}")

        # jvd_hr行数
        try:
            df = pd.read_sql_query("SELECT COUNT(*) AS cnt FROM jvd_hr", conn)
            cnt = int(df["cnt"].iloc[0])
            lines.append(f"    jvd_hr: {cnt:,}")
        except Exception as e:
            lines.append(f"    jvd_hr: ERROR - {e}")
        
    finally:
        conn.close()
    
    return "\n".join(lines)

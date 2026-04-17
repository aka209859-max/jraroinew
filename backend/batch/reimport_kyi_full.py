#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================================
reimport_kyi_full.py  -- jrd_kyi_fixed 全カラム再インポート
============================================================================
目的:
  JRDB KYI*.lzh ファイル群 (1102件) を 7-Zip で解凍し、
  DataSettings.xml 公式仕様 (1026 bytes/record, cp932) に従って
  全132カラムをパースして jrd_kyi_fixed へ UPSERT する。

  既存データ (490,000行) は ON CONFLICT DO UPDATE で上書き更新。
  新カラム (101列) は NULL→実値 に埋まる。

前提:
  - Python 3.12
  - 7-Zip: C:\\Program Files\\7-Zip\\7z.exe
  - PostgreSQL: pckeiba (host 127.0.0.1:5432)
  - jrd_kyi_fixed に alter_kyi_fixed.sql を適用済み

使用方法:
  # ALTER TABLE のみ実行 (インポートしない)
  py -3.12 backend/batch/reimport_kyi_full.py --alter-only

  # ドライラン (パースのみ、DBに書き込まない)
  py -3.12 backend/batch/reimport_kyi_full.py <KYI_DIR> --dry-run

  # 本番インポート (ALTER TABLE 込み)
  py -3.12 backend/batch/reimport_kyi_full.py <KYI_DIR>

  # ALTER TABLE をスキップしてインポートのみ
  py -3.12 backend/batch/reimport_kyi_full.py <KYI_DIR> --skip-alter

  # 特定ファイルのみ (ファイル名パターン指定)
  py -3.12 backend/batch/reimport_kyi_full.py <KYI_DIR> --pattern "KYI26*"

デフォルト KYI_DIR: E:\\anonymous-keiba-ai-JRA\\data\\jrdb\\KYI
============================================================================
"""

import argparse
import logging
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

import psycopg2
import psycopg2.extras

# ---------------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------------

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 5432,
    "database": "pckeiba",
    "user": "postgres",
    "password": "postgres123",
}

SEVEN_ZIP = r"C:\Program Files\7-Zip\7z.exe"

DEFAULT_KYI_DIR = r"E:\anonymous-keiba-ai-JRA\data\jrdb\raw\KYI"

ALTER_SQL_PATH = Path(__file__).parent / "alter_kyi_fixed.sql"

# KYI 固定長レコード長 (CRLF を除いたデータバイト数)
# 実ファイルは 1022 bytes/record + CRLF(2) = 1024 bytes/line
# DataSettings.xml の 1026 は race_shikonen フィールドの重複定義を含む誤差
RECORD_LENGTH = 1022

# バッチサイズ (UPSERT 1回のレコード数)
BATCH_SIZE = 500

# ---------------------------------------------------------------------------
# KYI フォーマット定義 (実ファイル準拠, 合計1022バイト/レコード)
#
# (開始バイト位置, バイト長, カラム名)
#
# DataSettings.xml との差異:
#   DataSettings は "race_shikonen"(6) を独立フィールドとして定義した後、
#   kaisai_kai(1)/kaisai_nichime(1)/race_bango(2) を別エントリとして重複定義している。
#   実ファイルではこれらは連続した単一ブロック (pos 2-7) に格納されており、
#   DataSettings の pos>=8 は全て -4 補正が必要。
#   結果: 実レコード長 = 1026 - 4 = 1022 bytes (CRLF 除く)
#
# jrdb_race_key8 = bytes[0:8] (8連続バイト)
#   = keibajo_code(2) + race_shikonen_YY(2) + kaisai_kai(1) + kaisai_nichime(1) + race_bango(2)
# ---------------------------------------------------------------------------

KYI_FORMAT: List[tuple] = [
    # (start, length, col_name)
    (0,   2,  "keibajo_code"),
    (2,   2,  "race_shikonen"),         # YY (2桁年)
    (4,   1,  "kaisai_kai"),
    (5,   1,  "kaisai_nichime"),         # 16進数 '1'-'9','a'-'c'
    (6,   2,  "race_bango"),
    (8,   2,  "umaban"),
    (10,  8,  "ketto_toroku_bango"),
    (18,  36, "bamei"),
    (54,  5,  "idm"),
    (59,  5,  "kishu_shisu"),
    (64,  5,  "joho_shisu"),
    (69,  15, "yobi_1"),
    (84,  5,  "sogo_shisu"),
    (89,  1,  "kyakushitsu_code"),
    (90,  1,  "kyori_tekisei_code"),
    (91,  1,  "joshodo_code"),
    (92,  3,  "rotation"),
    (95,  5,  "kijun_odds_tansho"),
    (100, 2,  "kijun_ninkijun_tansho"),
    (102, 5,  "kijun_odds_fukusho"),
    (107, 2,  "kijun_ninkijun_fukusho"),
    (109, 3,  "tokutei_joho_1"),
    (112, 3,  "tokutei_joho_2"),
    (115, 3,  "tokutei_joho_3"),
    (118, 3,  "tokutei_joho_4"),
    (121, 3,  "tokutei_joho_5"),
    (124, 3,  "sogo_joho_1"),
    (127, 3,  "sogo_joho_2"),
    (130, 3,  "sogo_joho_3"),
    (133, 3,  "sogo_joho_4"),
    (136, 3,  "sogo_joho_5"),
    (139, 5,  "ninki_shisu"),
    (144, 5,  "chokyo_shisu"),
    (149, 5,  "kyusha_shisu"),
    (154, 1,  "chokyo_yajirushi_code"),
    (155, 1,  "kyusha_hyoka_code"),
    (156, 4,  "kishu_kitai_rentai_ritsu"),
    (160, 3,  "gekiso_shisu"),
    (163, 2,  "hizume_code"),
    (165, 1,  "tekisei_code_omo"),
    (166, 2,  "class_code"),
    (168, 2,  "yobi_2"),
    (170, 1,  "blinker_shiyo_kubun"),
    (171, 12, "kishumei"),
    (183, 3,  "futan_juryo"),
    (186, 1,  "kishu_minarai_code"),
    (187, 12, "chokyoshimei"),
    (199, 4,  "chokyoshi_shozoku"),
    (203, 16, "kako1_kyoso_seiseki_key"),
    (219, 16, "kako2_kyoso_seiseki_key"),
    (235, 16, "kako3_kyoso_seiseki_key"),
    (251, 16, "kako4_kyoso_seiseki_key"),
    (267, 16, "kako5_kyoso_seiseki_key"),
    (283, 8,  "kako1_race_key"),
    (291, 8,  "kako2_race_key"),
    (299, 8,  "kako3_race_key"),
    (307, 8,  "kako4_race_key"),
    (315, 8,  "kako5_race_key"),
    (323, 1,  "wakuban"),
    (324, 2,  "yobi_3"),
    (326, 1,  "shirushi_code_1"),
    (327, 1,  "shirushi_code_2"),
    (328, 1,  "shirushi_code_3"),
    (329, 1,  "shirushi_code_4"),
    (330, 1,  "shirushi_code_5"),
    (331, 1,  "shirushi_code_6"),
    (332, 1,  "shirushi_code_7"),
    (333, 1,  "tekisei_code_shiba"),
    (334, 1,  "tekisei_code_dirt"),
    (335, 5,  "kishu_code"),
    (340, 5,  "chokyoshi_code"),
    (345, 1,  "yobi_4"),
    (346, 6,  "kakutoku_shokin_ruikei"),
    (352, 5,  "shutoku_shokin_ruikei"),
    (357, 1,  "joken_class_code"),
    (358, 5,  "ten_shisu"),
    (363, 5,  "pace_shisu"),
    (368, 5,  "agari_shisu"),
    (373, 5,  "ichi_shisu"),
    (378, 1,  "pace_yoso"),
    (379, 2,  "dochu_juni"),
    (381, 2,  "dochu_sa"),
    (383, 1,  "dochu_uchisoto"),
    (384, 2,  "kohan_3f_juni"),
    (386, 2,  "kohan_3f_sa"),
    (388, 1,  "kohan_3f_uchisoto"),
    (389, 2,  "goal_juni"),
    (391, 2,  "goal_sa"),
    (393, 1,  "goal_uchisoto"),
    (394, 1,  "tenkai_kigo_code"),
    (395, 1,  "kyori_tekisei_code_2"),
    (396, 3,  "bataiju"),
    (399, 3,  "bataiju_zogen"),
    (402, 1,  "torikeshi_flag"),
    (403, 1,  "seibetsu_code"),
    (404, 40, "banushimei"),
    (444, 2,  "banushikai_code"),
    (446, 2,  "umakigo_code"),
    (448, 2,  "gekiso_juni"),
    (450, 2,  "ls_shisu_juni"),
    (452, 2,  "ten_shisu_juni"),
    (454, 2,  "pace_shisu_juni"),
    (456, 2,  "agari_shisu_juni"),
    (458, 2,  "ichi_shisu_juni"),
    (460, 4,  "kishu_kitai_tansho_ritsu"),
    (464, 4,  "kishu_kitai_sanchakunai_ritsu"),
    (468, 1,  "yuso_kubun"),
    (469, 8,  "soho"),
    (477, 24, "taikei"),
    (501, 3,  "taikei_sogo_1"),
    (504, 3,  "taikei_sogo_2"),
    (507, 3,  "taikei_sogo_3"),
    (510, 3,  "uma_tokki_1"),
    (513, 3,  "uma_tokki_2"),
    (516, 3,  "uma_tokki_3"),
    (519, 4,  "uma_start_shisu"),
    (523, 4,  "uma_deokure_ritsu"),
    (527, 2,  "sanko_zenso"),
    (529, 5,  "sanko_zenso_kishu_code"),
    (534, 3,  "manken_shisu"),
    (537, 1,  "manken_shirushi"),
    (538, 1,  "kokyu_flag"),
    (539, 2,  "gekiso_type"),
    (541, 2,  "kyuyo_riyu_bunrui_code"),
    (543, 16, "flag"),
    (559, 2,  "nyukyu_nansome"),
    (561, 8,  "nyukyu_nengappi"),
    (569, 3,  "nyukyu_nannichimae"),
    (572, 50, "hobokusaki"),
    (622, 1,  "hobokusaki_rank"),
    (623, 1,  "kyusha_rank"),
    (624, 398, "yobi_5"),
]

# ---------------------------------------------------------------------------
# jrd_kyi カラム名 → jrd_kyi_fixed カラム名 リネームマッピング (8件)
# ---------------------------------------------------------------------------

RENAME_TO_FIXED: Dict[str, str] = {
    "ketto_toroku_bango":   "kettou_toroku_bango",  # 既存typo吸収
    "kyakushitsu_code":     "kyakushitsu",
    "kyori_tekisei_code":   "kyori_tekisei",
    "tekisei_code_omo":     "omo_tekisei_code",
    "tekisei_code_shiba":   "shiba_tekisei_code",
    "tekisei_code_dirt":    "da_tekisei_code",
    "blinker_shiyo_kubun":  "blinker",
    "kyori_tekisei_code_2": "kyori_tekisei_2",
}

# ---------------------------------------------------------------------------
# ロギング
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ユーティリティ
# ---------------------------------------------------------------------------

def nichi_hex_to_int(ch: str) -> int:
    """kaisai_nichime の16進数1文字を整数に変換 ('1'-'9' → 1-9, 'a'-'c' → 10-12)"""
    try:
        return int(ch, 16)
    except (ValueError, TypeError):
        return 0


def decode_bytes(raw_bytes: bytes, start: int, length: int) -> Optional[str]:
    """cp932 バイト列から指定範囲を切り出して文字列化 (空文字は None 返却)"""
    chunk = raw_bytes[start: start + length]
    try:
        val = chunk.decode("cp932", errors="replace").strip()
    except Exception:
        val = ""
    return val if val else None


def parse_record(raw_bytes: bytes) -> Dict[str, Optional[str]]:
    """
    KYI 1レコード (1022 bytes) をパースして dict を返す。
    キー名は jrd_kyi_fixed のカラム名 (RENAME 済み)。
    """
    rec: Dict[str, Optional[str]] = {}

    for start, length, col_name in KYI_FORMAT:
        val = decode_bytes(raw_bytes, start, length)
        fixed_name = RENAME_TO_FIXED.get(col_name, col_name)
        rec[fixed_name] = val

    return rec


def compute_derived(rec: Dict[str, Optional[str]]) -> Dict[str, object]:
    """
    パース済み dict から派生カラムを計算して返す。
    """
    kc  = (rec.get("keibajo_code") or "").strip()
    rs  = (rec.get("race_shikonen") or "").strip()   # YY (2桁)
    kai = (rec.get("kaisai_kai") or "").strip()
    nm  = (rec.get("kaisai_nichime") or "").strip()  # 16進1桁
    rb  = (rec.get("race_bango") or "").strip()

    # jrdb_race_key8: bytes[0:8] = keibajo_code(2)+YY(2)+kai(1)+nichi(1)+race_bango(2)
    jrdb_race_key8: Optional[str] = None
    if len(kc) == 2 and len(rs) == 2 and len(kai) == 1 and len(nm) == 1 and len(rb) == 2:
        jrdb_race_key8 = kc + rs + kai + nm + rb

    # kaisai_nen_2: 4桁年 "20YY"
    kaisai_nen_2: Optional[str] = None
    if rs and rs.isdigit():
        yy = int(rs)
        kaisai_nen_2 = str(2000 + yy)

    # basho_code = keibajo_code
    basho_code: Optional[str] = kc if kc else None

    # year: 整数年
    year_val: Optional[int] = int(kaisai_nen_2) if kaisai_nen_2 else None

    # kai_int
    kai_int: Optional[int] = int(kai) if kai and kai.isdigit() else None

    # nichi_int (16進→整数)
    nichi_int: Optional[int] = nichi_hex_to_int(nm) if nm else None

    # race_num
    race_num: Optional[int] = int(rb) if rb and rb.isdigit() else None

    return {
        "jrdb_race_key8": jrdb_race_key8,
        "kaisai_nen_2":   kaisai_nen_2,
        "basho_code":     basho_code,
        "year":           year_val,
        "kai":            kai_int,
        "nichi":          nichi_int,
        "race_num":       race_num,
    }


def parse_kyi_file(txt_path: Path) -> List[Dict]:
    """
    解凍済み KYI テキストファイルをバイト単位でパースしてレコードリストを返す。
    """
    records = []
    try:
        with open(txt_path, "rb") as fh:
            data = fh.read()
    except Exception as e:
        logger.error("ファイル読み込みエラー %s: %s", txt_path, e)
        return records

    lines = data.splitlines()  # CR/LF 両対応
    for line_num, line in enumerate(lines, 1):
        if len(line) < RECORD_LENGTH:
            if len(line) > 0:
                logger.debug("  行 %d: 短いレコード (%d bytes), スキップ", line_num, len(line))
            continue

        raw = line[:RECORD_LENGTH]
        rec = parse_record(raw)
        derived = compute_derived(rec)
        rec.update(derived)
        records.append(rec)

    logger.info("  パース完了: %d レコード (ファイル %d bytes)", len(records), len(data))
    return records


# ---------------------------------------------------------------------------
# 7-Zip 解凍
# ---------------------------------------------------------------------------

def extract_lzh(lzh_path: Path, out_dir: Path) -> List[Path]:
    """
    7-Zip を使って LZH ファイルを out_dir に解凍し、解凍された .txt ファイル一覧を返す。
    """
    cmd = [SEVEN_ZIP, "e", str(lzh_path), f"-o{out_dir}", "-y"]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            logger.warning(
                "  7z 警告 %s (rc=%d): %s",
                lzh_path.name,
                result.returncode,
                result.stderr.strip()[:200],
            )
    except subprocess.TimeoutExpired:
        logger.error("  7z タイムアウト: %s", lzh_path.name)
        return []
    except FileNotFoundError:
        logger.error("7-Zip が見つかりません: %s", SEVEN_ZIP)
        sys.exit(1)

    txt_files = list(out_dir.glob("*.txt")) + list(out_dir.glob("*.TXT"))
    return txt_files


# ---------------------------------------------------------------------------
# ALTER TABLE
# ---------------------------------------------------------------------------

def run_alter_table(conn) -> bool:
    """ALTER TABLE SQL を実行して jrd_kyi_fixed を拡張する。"""
    if not ALTER_SQL_PATH.exists():
        logger.error("ALTER SQL ファイルが見つかりません: %s", ALTER_SQL_PATH)
        return False

    sql = ALTER_SQL_PATH.read_text(encoding="utf-8")
    logger.info("ALTER TABLE 実行中: %s", ALTER_SQL_PATH)
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        logger.info("[OK] ALTER TABLE 完了 (101カラム追加)")
        return True
    except Exception as e:
        conn.rollback()
        logger.error("[ERROR] ALTER TABLE エラー: %s", e)
        return False


# ---------------------------------------------------------------------------
# UPSERT
# ---------------------------------------------------------------------------

def build_upsert_sql(columns: List[str]) -> str:
    """
    columns リストに基づいて UPSERT SQL を生成する。
    PK: (jrdb_race_key8, umaban)
    """
    col_list = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))

    pk_cols = {"jrdb_race_key8", "umaban"}
    update_cols = [c for c in columns if c not in pk_cols]
    update_clause = ",\n        ".join(
        f"{c} = EXCLUDED.{c}" for c in update_cols
    )

    return f"""
INSERT INTO jrd_kyi_fixed ({col_list})
VALUES ({placeholders})
ON CONFLICT (jrdb_race_key8, umaban) DO UPDATE SET
        {update_clause}
"""


def upsert_records(records: List[Dict], conn, dry_run: bool = False) -> int:
    """
    レコードリストを jrd_kyi_fixed に UPSERT する。
    dry_run=True の場合は SQL 生成のみでロールバックする。
    """
    if not records:
        return 0

    # 全レコードに含まれるカラムを収集
    all_cols: List[str] = []
    seen: set = set()
    for rec in records:
        for k in rec.keys():
            if k not in seen:
                seen.add(k)
                all_cols.append(k)

    # PK 必須チェック
    valid_records = [
        r for r in records
        if r.get("jrdb_race_key8") and r.get("umaban")
    ]
    if len(valid_records) < len(records):
        logger.warning(
            "  [WARN]  PK欠如レコードをスキップ: %d 件",
            len(records) - len(valid_records),
        )
    if not valid_records:
        return 0

    upsert_sql = build_upsert_sql(all_cols)

    if dry_run:
        logger.info("  [DRY RUN] UPSERT SQL (先頭200文字):\n  %s", upsert_sql[:200])
        logger.info("  [DRY RUN] %d レコード (書き込みなし)", len(valid_records))
        return len(valid_records)

    success = 0
    error_count = 0

    with conn.cursor() as cur:
        for batch_start in range(0, len(valid_records), BATCH_SIZE):
            batch = valid_records[batch_start: batch_start + BATCH_SIZE]
            rows = [
                [r.get(c) for c in all_cols]
                for r in batch
            ]
            try:
                psycopg2.extras.execute_batch(cur, upsert_sql, rows, page_size=BATCH_SIZE)
                conn.commit()
                success += len(batch)
                if batch_start > 0 and batch_start % (BATCH_SIZE * 20) == 0:
                    logger.info(
                        "  進捗: %d / %d 件",
                        batch_start + len(batch),
                        len(valid_records),
                    )
            except Exception as e:
                conn.rollback()
                logger.warning(
                    "  [WARN]  バッチ %d〜%d エラー: %s",
                    batch_start,
                    batch_start + len(batch),
                    str(e)[:200],
                )
                error_count += len(batch)

    if error_count:
        logger.warning("  [WARN]  %d 件エラー", error_count)
    return success


# ---------------------------------------------------------------------------
# メイン処理
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="jrd_kyi_fixed 全カラム再インポート (KYI*.lzh → PostgreSQL)"
    )
    parser.add_argument(
        "kyi_dir",
        nargs="?",
        default=DEFAULT_KYI_DIR,
        help=f"KYI*.lzh が格納されているディレクトリ (デフォルト: {DEFAULT_KYI_DIR})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="パースのみ実行、DB への書き込みはしない",
    )
    parser.add_argument(
        "--alter-only",
        action="store_true",
        help="ALTER TABLE のみ実行してインポートは行わない",
    )
    parser.add_argument(
        "--skip-alter",
        action="store_true",
        help="ALTER TABLE をスキップしてインポートのみ実行",
    )
    parser.add_argument(
        "--pattern",
        default="KYI*.lzh",
        help="処理するファイルのグロブパターン (デフォルト: KYI*.lzh)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="処理ファイル数の上限 (デバッグ用、0=無制限)",
    )
    args = parser.parse_args()

    logger.info("=" * 72)
    logger.info("[START] reimport_kyi_full.py 開始")
    logger.info("=" * 72)

    # DB 接続
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = False
        logger.info("[OK] DB 接続完了 (pckeiba)")
    except Exception as e:
        logger.error("[ERROR] DB 接続エラー: %s", e)
        sys.exit(1)

    # ALTER TABLE
    if not args.skip_alter:
        ok = run_alter_table(conn)
        if not ok:
            conn.close()
            sys.exit(1)
    else:
        logger.info("[INFO]  ALTER TABLE スキップ (--skip-alter)")

    if args.alter_only:
        logger.info("[OK] ALTER TABLE のみ完了 (--alter-only)")
        conn.close()
        return

    # KYI ディレクトリ確認
    kyi_dir = Path(args.kyi_dir)
    if not kyi_dir.exists():
        logger.error("[ERROR] KYI ディレクトリが見つかりません: %s", kyi_dir)
        conn.close()
        sys.exit(1)

    # LZH ファイル一覧
    lzh_files = sorted(kyi_dir.glob(args.pattern))
    if not lzh_files:
        logger.warning("[WARN]  %s に %s が見つかりません", kyi_dir, args.pattern)
        conn.close()
        return

    if args.limit:
        lzh_files = lzh_files[: args.limit]

    logger.info("対象ファイル数: %d", len(lzh_files))
    if args.dry_run:
        logger.info("[WARN]  DRY RUN モード: DB 書き込みなし")

    total_records = 0
    total_upserted = 0

    for file_idx, lzh_path in enumerate(lzh_files, 1):
        logger.info("\n[%d/%d] 処理中: %s", file_idx, len(lzh_files), lzh_path.name)

        with tempfile.TemporaryDirectory(prefix="kyi_extract_") as tmp_dir:
            tmp_path = Path(tmp_dir)
            txt_files = extract_lzh(lzh_path, tmp_path)

            if not txt_files:
                logger.warning("  [WARN]  解凍ファイルなし: %s", lzh_path.name)
                continue

            for txt_path in txt_files:
                records = parse_kyi_file(txt_path)
                if not records:
                    continue

                total_records += len(records)
                n = upsert_records(records, conn, dry_run=args.dry_run)
                total_upserted += n
                logger.info("  [OK] %s: %d 件 UPSERT 完了", txt_path.name, n)

    conn.close()

    logger.info("\n" + "=" * 72)
    logger.info("[OK] インポート完了")
    logger.info("   処理ファイル数  : %d", len(lzh_files))
    logger.info("   パース総レコード: %d", total_records)
    logger.info("   UPSERT 件数    : %d", total_upserted)
    if args.dry_run:
        logger.info("   [WARN]  DRY RUN: DB への実際の変更なし")
    logger.info("=" * 72)


if __name__ == "__main__":
    main()

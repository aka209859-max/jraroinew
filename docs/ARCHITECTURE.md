# Enable Edge Engine - Architecture

## システム構成
- Backend: FastAPI (Python 3.12)
- Frontend: Next.js (TBD)
- Database: PostgreSQL (pckeiba)

## データフロー
1. PostgreSQL → data_loader_v2.py → 基本データ取得
2. prev_race_loader.py → 前走データ取得（LAG方式）
3. derived_factors.py → 加工ファクター生成
4. analysis_engine.py → 分析実行（集計キークロス、補正回収率計算）
5. FastAPI → JSON API → Next.js → ユーザー画面

## DB情報
- 全テーブル・カラム定義: docs/ACTUAL_DB_SCHEMA_2293_COLUMNS.csv
- データ期間: 2016-2025
- 主要テーブル: jvd_se(出走), jvd_ra(レース), jrd_kyi_fixed(JRDB指数), jrd_sed(成績), jvd_sk(血統)

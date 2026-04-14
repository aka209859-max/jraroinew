# CLAUDE.md - Enable Edge Engine

## プロジェクト概要
競馬予想分析システム「Enable Edge Engine」のバックエンド + フロントエンド。
CrossFactorを超える分析自由度を持つ、プロフェッショナル向け競馬データ分析プラットフォーム。

## 技術スタック
- Backend: Python 3.12 + FastAPI
- Frontend: Next.js (後で実装)
- Database: PostgreSQL (既存DB: pckeiba)
- テスト: pytest

## DB接続
- host: 127.0.0.1
- port: 5432
- db: pckeiba
- user: postgres
- password: postgres123

## 絶対ルール
1. ACTUAL_DB_SCHEMA_2293_COLUMNS.csv に存在するカラム名のみ使用すること
2. _fixed テーブルが存在する場合はそちらを優先（jrd_kyi_fixed: 490k行, jrd_kyi: 517行）
3. 単勝オッズ条件: 1.0〜100.0倍
4. 複勝オッズ条件: 1.0〜17.0倍
5. 取消馬除外: kakutei_chakujun = '00' は集計から除外
6. 異常区分除外: ijo_kubun_code != '0' は集計から除外
7. データ期間: 2016-2025（10年間）
8. 期間重み付け: 2016=1, 2017=2, ..., 2025=10
9. 補正回収率: 108段階配当補正係数 + 期間重み付け
10. 信頼度: √(N/(N+400))
11. ビンのソート: 必ず数値順（文字列ソート禁止）
12. 既存テストを壊すな
13. 新規ファイル作成時は必ずテストも作成

## JRDBテーブル対応
- jrd_kyi → jrd_kyi_fixed を使用（490,000行）
- jrd_kyi (raw) は517行のみ、使用禁止
- jrd_sed: 前走実脚質、レースペース
- jrd_joa: 基準オッズ、CID（JOINカバレッジ34.6%、NULLは"不明"扱い）

## JRDB JOIN条件
jrd_kyi_fixed: JVAN_TO_JRDB_RACE_KEY8 でJOIN
jrd_joa: keibajo_code + race_shikonen(YYDDMM) + umaban でJOIN
jrd_sed: ketto_toroku_bango + 日付でJOIN

## コマンド
- テスト実行: py -3.12 -m pytest backend/tests/ -v
- サーバー起動: py -3.12 -m uvicorn backend.main:app --reload
- 全テスト: py -3.12 -m pytest backend/tests/ -v --tb=short

## 作業ディレクトリ
E:\jraroinew

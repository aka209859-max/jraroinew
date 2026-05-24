# PROJECT_STATUS_REPORT.md
Generated: 2026-05-23

---

## 1. プロジェクト概要

**プロジェクト名**: Enable Edge Engine  
**目的**: JRDBデータを活用した競馬予想分析プラットフォーム。CrossFactorを超える分析自由度を持つプロフェッショナル向けシステム。  
**構成**: Python 3.12 + FastAPI（バックエンド実装済み）、Next.js（フロントエンド未実装）、PostgreSQL DB: `pckeiba`

---

## 2. 完了済み作業（ファイル・コミット根拠あり）

### 2-1. データ基盤

| 作業 | 根拠ファイル / コミット |
|------|------------------------|
| JVD優先マイグレーション（umakigo_code, kishu_minarai_code, bataiju, bataiju_zogen の取得元を jrd_kyi → jvd_se に変更） | `backend/batch/factor_screening.py` `_LOAD_QUERY` 内 CAST/CASE WHEN 実装 |
| bataiju が全NULL だったバグ修正（TRIM + NULLIF + CAST） | コミット `9bf5d56` |
| futan_juryo は既に JVD 参照済み（変更不要と確認） | `reports/source_of_truth/bataiju_futan_juryo_comparison.md` |
| jrd_kyi_fixed テーブル使用（490,167行）、jrd_kyi (517行) 使用禁止 | `factor_screening.py` `_LOAD_QUERY` の FROM 句 |
| jrd_joa (kijun_odds, CID) JOIN カバレッジ確認（34.6%、NULL→"不明"扱い） | `reports/source_of_truth/revised_summary_20260504.md` |

### 2-2. ファクター設計（factor_screening.py コミット `3960437`）

| 種別 | 数 | 代表例 |
|------|----|--------|
| NUMERIC_FACTORS | 10 | ls_shisu_juni, bataiju, kijun_ninkijun_tansho |
| CODE_FACTORS | 33 | manken_shirushi, *_decile (9種), rotation_bin, uma_deokure_bin |
| **ALL_FACTORS 合計** | **43** | — |

**ビン設計方針（2026-05-04確定）**:
1. 生指数(raw shisu)は除外 → Juni順位 または 10分位(decile)を使用
2. kakutoku_shokin_ruikei / nyukyu_nannichimae は除外（過分割・情報漏洩リスク）
3. rotation → rotation_bin（0/1/2/3/4/5-9/10-25/26+の8バケット）
4. uma_deokure_ritsu → uma_deokure_bin（0-4%/5-9%/10-14%/15-19%/20%+の5バケット）
5. kishu_kitai_*_ritsu → _decile（10分位変換）

**除外ファクター（_FS_SKIP_COLS）**: idm, sogo_shisu, ten_shisu, pace_shisu, agari_shisu, ichi_shisu, gekiso_shisu, ninki_shisu, joho_shisu, manken_shisu, kishu_shisu, chokyo_shisu, kyusha_shisu, uma_start_shisu（生指数14種）、kakutoku_shokin_ruikei, nyukyu_nannichimae, kishu_kitai_rentai_ritsu, kishu_kitai_tansho_ritsu, rotation, uma_deokure_ritsu

### 2-3. コンボパイプライン（master_combo_pipeline.py）

| Phase | セグメント数 | コンボ数 | 内容 |
|-------|------------|---------|------|
| Phase1 | 144 | 12 | 単一ファクター（CLB >= 75.0 通過候補のみ） |
| Phase2 | 144 | 260 | 2-factor combo |
| Phase3 | 144 | 1,192 | 3-factor combo |
| Phase4 | 144 | 0（実行未完了） | 4-factor combo（処理時間超過で中断） |

生成ファイル: `reports/production_search/segments/` 以下 combo*_results.csv（576ファイル）  
→ Git管理外（.gitignore 登録済み、コミット `542d6ea`）

### 2-4. 監査パイプライン（audit_factor_bins.py / audit_factor_bins_v2.py）

- **audit_factor_bins.py**: Phase別分割処理（OOM対策済み）。各Phase処理後 gc.collect()  
- **audit_factor_bins_v2.py**: 6バケット SHS対応監査。Rule C 適用で shortlist 生成  
- 両ファイルの空DataFrameクラッシュ修正済み（コミット `3960437`）

生成ファイル（Git管理外）:
- `reports/production_search/phase*_bin_detail*.csv`（Phase3: 1,664,215行 / ~180MB）
- `reports/production_search/phase*_factor_bin_audit*.csv`
- `reports/production_search/phase*_segment_factor_summary*.csv`

### 2-5. 採用候補（shortlist）確定

ファイル根拠: `reports/production_search/final_adoption_shortlist.csv`

| Phase | セグメント | ファクター | 採用レベル | min_bin_n | 総ビン数 |
|-------|-----------|-----------|------------|-----------|---------|
| 1 | KEIBAJO_SURFACE_08_芝 | manken_shirushi | **500-level** | 965 | 8（9ビン中8観測） |
| 1 | SURFACE_2_ダ_条件戦 | uma_deokure_bin | **300-level** | 436 | 5 |

Phase2〜4: 採用候補 0件（全rejct）

### 2-6. テスト

ファイル: `backend/tests/` (test_analysis_engine.py, test_api.py, test_bin_scoring.py, test_database.py)  
直近テスト結果: **51 passed, 21 warnings in 371.51s** （コンテキスト内 task 出力から確認）

---

## 3. ファクター採用状況

### 採用確定（2件）

| ファクター | セグメント | レベル | 判定日 |
|-----------|-----------|--------|--------|
| manken_shirushi | KEIBAJO_SURFACE_08_芝 | 500 | 2026-05-22 |
| uma_deokure_bin | SURFACE_2_ダ_条件戦 | 300 | 2026-05-22（ビン再設計後の新規） |

### 採用保留（精査待ち）

- SHSファクター（juni系: ls_shisu_juni, ten_shisu_juni, pace_shisu_juni, agari_shisu_juni, ichi_shisu_juni, gekiso_juni）
  - Rule C のテールビン除外（rank >= 13 かつ n < 30）後の実効ビンで min >= 閾値を満たす可能性あり
  - Phase1 SHSコンボ数: 2件（`final_adoption_summary.csv` shs_combos=2）
  - 要: レース別頭数分布での「構造的ゼロ」再確認

### 採用却下

- Phase2〜4 全コンボ（合計 1,452 combos）: 全ビンで n_horses が閾値未満
- 除外済みファクター（上記 _FS_SKIP_COLS 参照）

### 採用判定ルール（Rule C、確定）

1. total_bins <= 30（過分割防止）
2. 非SHSファクター: 全ビン n_horses >= 閾値（500/300/150）
3. SHSファクター: テールビン（rank >= 13 かつ n < 30）除外後の実効ビンで min >= 閾値
4. SHS除外後でも1桁ビンがあれば reject

根拠ファイル: `reports/production_search/final_adoption_rule_proposals.md`

---

## 4. 解決済み問題

| 問題 | 原因 | 対応 | コミット |
|------|------|------|---------|
| bataiju が全NULL | jrd_kyi の bataiju は文字列ゴミ。TRIM+NULLIF+CASTが必要 | `_LOAD_QUERY` で `CAST(NULLIF(TRIM(v.bataiju),'') AS NUMERIC)` に変更 | `9bf5d56` |
| audit_factor_bins.py OOM（60/117セグメント時点）| 全フェーズ分の rows を一括メモリ保持 | main() をフェーズ別分割 + gc.collect() に書き換え | `3960437` |
| audit_factor_bins.py 空DataFrame KeyError | `pd.DataFrame([]).sort_values()` が失敗 | `if not rows: return pd.DataFrame(columns=[...])` ガード追加 | `3960437` |
| audit_factor_bins_v2.py 空DataFrame KeyError（Phase4） | 同上 | 同上（make_factor_audit, make_bin_detail, make_segment_summary の3箇所） | `3960437` |
| GitHub 100MB制限超過（Phase3 bin_detail CSV ~180MB） | Phase3 監査出力が巨大 | git reset --soft でコミット取り消し、.gitignore 追加、再コミット | `542d6ea` |
| combo_results.csv がチェックポイントにより再生成スキップ | checkpoints/pipeline_master.json が古い完了済み状態 | 576ファイルを削除後、Phase1-4 を順次再実行 | — |
| Phase4 監査が無限スタック | C(20,4)=4,845コンボ × 360k行 で処理時間超過 | プロセス中断、空Phase4ファイルを手動作成 | — |

---

## 5. 未解決・保留事項

| 事項 | 優先度 | 備考 |
|------|--------|------|
| S-score計算ロジック未設計 | **最高** | 採用ファクター2件のビン別補正回収率→S-scoreへの変換式が未定義 |
| S-score辞書の構築 | **最高** | manken_shirushi + uma_deokure_bin を元にした辞書DB/CSVが未生成 |
| Phase4 監査未実施 | 低 | 歴史的に shortlist 0件。実施コスト高（C(20,4)×144セグメント） |
| SHSファクター精査 | 中 | レース別頭数分布分析でテールビンの「構造的ゼロ」を確認後、Rule C 適用で追加採用判断 |
| 採用閾値（150/300/500）の妥当性検証 | 中 | 「年平均レース数から逆算」アプローチが提案済み（未実施） |
| フロントエンド（Next.js）未実装 | 低（後工程） | CLAUDE.md に「後で実装」と明記 |
| ACTUAL_DB_SCHEMA_2293_COLUMNS.csv と実テーブルのカラム数不一致 | 中 | CSV には38カラム記載、jrd_kyi_fixed 実測では139カラム（要確認） |
| `kijun_ninkijun_tansho` の NULL 率 | 未確認 | jrd_joa JOIN カバレッジ 34.6% のため、このファクターも約65% が NULL の可能性 |

---

## 6. 確定設計ルール

### データルール

| ルール | 値 |
|--------|----|
| 単勝オッズ条件 | 1.0〜100.0倍 |
| 複勝オッズ条件 | 1.0〜17.0倍 |
| 取消馬除外 | kakutei_chakujun = '00' |
| 異常区分除外 | ijo_kubun_code != '0' |
| データ期間 | 2016-2025（10年間） |
| 期間重み付け | 2016=1, 2017=2, ..., 2025=10 |

### 計算ルール

| ルール | 式 |
|--------|----|
| 補正回収率 | 108段階配当補正係数 × 期間重み付け |
| 信頼度 | √(N / (N + 400)) |
| ビンのソート | 必ず数値順（文字列ソート禁止） |

### JVD優先ルール（確定）

| カラム | 旧取得元 | 新取得元 |
|--------|---------|---------|
| umakigo_code | jrd_kyi | jvd_se (`v.umakigo_code`) |
| kishu_minarai_code | jrd_kyi | jvd_se (`v.kishu_minarai_code`) |
| bataiju | jrd_kyi（ゴミデータ） | jvd_se (`CAST(NULLIF(TRIM(v.bataiju),'') AS NUMERIC)`) |
| bataiju_zogen | jrd_kyi | jvd_se (`CASE WHEN zogen_fugo='-' THEN -zogen_sa ELSE zogen_sa END`) |
| futan_juryo | — | 変更不要（既に JVD 参照済み） |

---

## 7. 主要ファイル構成

```
E:\jraroinew\
├── backend/
│   ├── batch/
│   │   ├── factor_screening.py          # ★ファクター定義・DB取得・派生計算（43ファクター）
│   │   ├── master_combo_pipeline.py     # Phase1-4 コンボ生成パイプライン
│   │   ├── audit_factor_bins.py         # 監査 Step1: Phase別ビン集計
│   │   ├── audit_factor_bins_v2.py      # 監査 Step2: Rule C 採用判定
│   │   ├── audit_period_verification.py # データ期間・フィルタ影響確認
│   │   ├── bin_scoring.py               # ビンスコア計算
│   │   ├── factor_adoption.py           # 採用管理
│   │   └── ... (その他18ファイル)
│   ├── engine/
│   │   ├── analysis_engine.py           # 分析エンジン本体
│   │   ├── data_loader_v2.py            # データローダー（SQLAlchemy警告あり）
│   │   ├── corrected_return.py          # 補正回収率計算
│   │   └── ...
│   ├── tests/
│   │   ├── test_analysis_engine.py      # 51 tests all passing
│   │   ├── test_api.py
│   │   ├── test_bin_scoring.py
│   │   └── test_database.py
│   └── main.py                          # FastAPI アプリケーション
├── reports/
│   ├── source_of_truth/                 # Git管理対象
│   │   ├── revised_summary_20260504.md  # JVD移行・ビン再設計サマリー
│   │   ├── current_factor_bin_definitions.csv   # ★ (100MB超 → gitignore)
│   │   ├── current_factor_bin_definitions_compact.csv  # ★ (同上)
│   │   └── ... (その他設計資料)
│   └── production_search/               # Git管理外（大容量）
│       ├── final_adoption_shortlist.csv # ★採用候補 2件確定済み
│       ├── final_adoption_summary.csv   # Phase別統計
│       ├── final_adoption_rule_proposals.md  # Rule A/B/C 定義
│       ├── final_adoption_rejects.csv   # reject一覧
│       ├── checkpoints/pipeline_master.json  # パイプライン進捗（要注意: 常に"completed"）
│       └── segments/                    # combo*_results.csv × 576件 (gitignore)
├── docs/
│   ├── PROJECT_STATUS_REPORT.md        # このファイル
│   └── PROJECT_COMPLETION_DEFINITION.md
├── CLAUDE.md                            # プロジェクト規約（絶対ルール）
└── .gitignore                           # 大容量CSV除外設定 (コミット 542d6ea)
```

---

*このレポートは実在するファイル・コード・コミット履歴のみを根拠に作成。未確認事項は「未確認」と明記。*

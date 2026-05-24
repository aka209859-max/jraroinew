# PROJECT_COMPLETION_DEFINITION.md
Generated: 2026-05-23

---

## 1. 完成の定義（1文）

**「採用済みファクターのビン別補正回収率・信頼度をS-scoreに変換し、任意レース・馬に対してAPIでスコアを返せる状態」をもって完成とする。**

---

## 2. 必須機能リスト

### Layer 1: データ層（実装済み）

| 機能 | 状態 | 根拠 |
|------|------|------|
| DB接続 (PostgreSQL: pckeiba) | ✅ 完了 | `backend/engine/data_loader_v2.py` |
| jrd_kyi_fixed から馬データ取得（490k行） | ✅ 完了 | `factor_screening.py` `_LOAD_QUERY` |
| jrd_joa JOIN（基準オッズ・CID） | ✅ 完了 | `factor_screening.py` `_JOA_QUERY` |
| jrd_sed JOIN（前走脚質・ペース） | ✅ 完了 | `factor_screening.py` `_PREV_QUERY` |
| jvd_se 優先カラム取得（bataiju等4列） | ✅ 完了 | コミット `9bf5d56`, `3960437` |
| オッズフィルタ（単勝1.0-100.0, 複勝1.0-17.0） | ✅ 完了 | `factor_screening.py` odds filter |
| 取消・異常区分除外 | ✅ 完了 | `factor_screening.py` |
| 期間重み付け（2016=1〜2025=10） | ✅ 完了 | `backend/engine/corrected_return.py` |
| 108段階配当補正係数 | ✅ 完了 | `backend/engine/corrected_return.py` |

### Layer 2: ファクター層（実装済み）

| 機能 | 状態 | 根拠 |
|------|------|------|
| 43ファクター定義（NUMERIC 10 + CODE 33） | ✅ 完了 | `factor_screening.py` ALL_FACTORS |
| 派生計算（decile×11、rotation_bin、uma_deokure_bin） | ✅ 完了 | `factor_screening.py` compute_derived_factors() |
| Phase1-3 コンボ生成（1,464コンボ） | ✅ 完了 | `master_combo_pipeline.py` |
| Phase1-3 ビン監査（Rule C 採用判定） | ✅ 完了 | `audit_factor_bins_v2.py` |
| 採用候補確定（2件） | ✅ 完了 | `final_adoption_shortlist.csv` |

### Layer 3: スコアリング層（**未実装**）

| 機能 | 状態 | 必要作業 |
|------|------|---------|
| 採用ファクターのビン別補正回収率・信頼度テーブル作成 | ❌ 未着手 | manken_shirushi (8ビン) + uma_deokure_bin (5ビン) の集計 |
| S-score変換式の設計 | ❌ 未設計 | 補正回収率 × 信頼度 → S-score のマッピング未定義 |
| S-score辞書構築（DB or CSV） | ❌ 未着手 | 辞書スキーマ未定義 |
| 任意馬へのS-score適用ロジック | ❌ 未着手 | 馬のファクター値→辞書参照→スコア返却 |

### Layer 4: バリデーション層（部分実装）

| 機能 | 状態 | 根拠 |
|------|------|------|
| pytest 単体テスト（51件） | ✅ 完了 | `backend/tests/` 51 passed |
| S-scoreバックテスト | ❌ 未着手 | スコアリング未実装のため実施不可 |
| 予測精度評価（回収率・的中率） | ❌ 未着手 | 同上 |

### Layer 5: 運用層

| 機能 | 状態 | 根拠 |
|------|------|------|
| FastAPI エンドポイント（/analyze 他） | ✅ 完了 | `backend/main.py` |
| フロントエンド（Next.js） | ❌ 未実装 | CLAUDE.md「後で実装」 |
| 本番デプロイ設定 | 未確認 | — |

---

## 3. 現在のギャップ（フェーズ別）

### フェーズ A: データ・ファクター確立 → ✅ **完了**

- ファクター43件定義完了
- ビン再設計（2026-05-04方針）完了
- JVD移行完了
- Phase1-3 コンボ監査完了
- 採用候補2件確定

**残課題**: SHSファクター（juni系6件）の精査（保留中）

---

### フェーズ B: S-score設計・構築 → ❌ **未着手**

**ギャップの詳細**:

1. **採用ファクターのビン別集計テーブルが存在しない**
   - manken_shirushi × KEIBAJO_SURFACE_08_芝: 8ビン × (補正回収率, 信頼度, N) の表
   - uma_deokure_bin × SURFACE_2_ダ_条件戦: 5ビン × 同上
   - これらをどの形式（DB table / CSV / JSON）で保持するか未定義

2. **S-score変換式が未設計**
   - 補正回収率と信頼度からS-scoreへの変換アルゴリズム未定義
   - 単純積（roi × confidence）なのか、対数変換なのか、未確定

3. **多ファクター統合方法が未設計**
   - 採用ファクターが複数になった場合の統合ルール（加重平均？最大値？）未定義
   - 現時点では採用2件のため単一スコアも複合スコアも設計未着手

4. **S-score辞書スキーマが未定義**
   - DB table として持つのか、JSON/CSV として保持するのか未定義
   - APIレスポンス形式との統合方針未定義

---

### フェーズ C: フロントエンド → ❌ **未着手**

- Next.js プロジェクト未作成
- API仕様との繋ぎ込み未設計

---

### フェーズ D: バックテスト・本番化 → ❌ **未着手**

- S-scoreによる馬券シミュレーション未実施
- 回収率・的中率の評価基準未定義

---

## 4. 完成への最短パス

以下を順に実装することで「定義1文」の状態に到達できる。

### Step 1: S-score辞書の集計（推定1-2日）

```
対象ファイル: backend/batch/factor_screening.py の get_data() 出力
処理:
  - KEIBAJO_SURFACE_08_芝 セグメント × manken_shirushi 全8ビン
    → 各ビンの (n_horses, tansho_corr_weighted_roi, confidence) を集計
  - SURFACE_2_ダ_条件戦 セグメント × uma_deokure_bin 全5ビン
    → 同上
出力: reports/source_of_truth/sscore_dictionary.csv (Git管理対象)
```

### Step 2: S-score変換式の決定と実装（推定0.5日）

```
設計決定が必要:
  - 補正ROI × 信頼度 = S-score（暫定案）
  - 基準ROI（1.0以下は負スコア）の設定
実装先: backend/engine/ 以下に sscore_calculator.py を新規作成
テスト: backend/tests/test_sscore_calculator.py を同時作成（CLAUDE.md ルール13）
```

### Step 3: APIエンドポイントへの組み込み（推定0.5日）

```
対象: backend/main.py または backend/engine/analysis_engine.py
機能: 任意のレースID + 馬番 → ファクター値取得 → 辞書引き → S-score返却
エンドポイント案: POST /api/score { race_id, umaban } → { s_score, factors }
```

### Step 4: 動作確認・テスト（推定0.5日）

```
- test_sscore_calculator.py: ビン→スコア変換の単体テスト
- test_api.py に /api/score エンドポイントのテスト追加
- 実データ1レースで手動確認
```

---

## 5. MVP定義（最小本番投入条件）

以下の全条件を満たす状態を MVP とする:

| 条件 | 判定基準 |
|------|---------|
| S-score辞書が存在する | `reports/source_of_truth/sscore_dictionary.csv` または同等のDB tableが存在 |
| 任意の馬にS-scoreを付与できる | `GET /api/score?race_id=X&umaban=Y` が数値を返す |
| 全pytestが通過する | `py -3.12 -m pytest backend/tests/ -v` が all passed |
| バックテスト回収率が 100% 以上 | 保有サンプルでの補正回収率期待値が 1.00 以上（採用条件の裏付け） |

**MVP スコープ外（後回しOK）**:
- フロントエンド（Next.js）
- Phase4 監査
- SHSファクター精査（juni系）
- 複数ファクター統合スコア
- 本番サーバーデプロイ

---

## 付記: 現在地

```
データ層     [██████████] 100% 完了
ファクター層  [████████░░]  80% 完了（SHS精査保留）
スコアリング  [░░░░░░░░░░]   0% 未着手
バリデーション[████░░░░░░]  40% 部分完了（pytestのみ）
運用層       [████░░░░░░]  40% API完了、フロント未実装
```

---

*このドキュメントは実在するファイル・コード・実行結果のみを根拠に作成。未確認事項は「未確認」と明記。*

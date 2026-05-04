# JVD優先正本ルール 移行計画

生成日: 2026-05-03

---

## 結論（先出し10行以内）

1. **Phase1〜4の49ファクターのうち、`umakigo_code` と `kishu_minarai_code` はJVD切替可能（完了）、`bataiju` / `bataiju_zogen` はk.が全NULLのためJVD切替必須（完了）、`futan_juryo` はMANUAL_REVIEW（実態はJVD済み）**
2. **JVDが正本となる列はすでに多くが正しく参照されている** — wakuban/surface/kyori_kubun/結果ラベルはJVD済み
3. **即座に切替可能なのは2列のみ**: `umakigo_code` と `kishu_minarai_code`（JRDB→JVD。ビン件数+11.8%見込み）
4. **要注意が3列**: `bataiju` / `bataiju_zogen` / `futan_juryo`（JVDとJRDBで定義差の可能性あり）
5. **JVD正本移行の最大効果**: jrd_kyi_fixed INNER JOINを外すことで全ビン件数が約+11.8%増加
6. **ACTUAL_DB_SCHEMA_2293_COLUMNS.csvは古い** — jrd_kyi_fixedの実DB列数は139(CSV記載38)
7. **最優先アクション**: bataiju/futan_juryo の定義差をDB直接確認してから移行判断

---

## 重複カラムの扱い方針

| 分類 | 対象列 | 方針 |
|------|--------|------|
| exact_overlap (JOIN確定) | keibajo_code, race_bango, umaban | JVDを正本。JOIN条件で同値保証済み |
| exact_overlap (切替推奨) | wakuban, kishu_minarai_code, umakigo_code, seibetsu_code | JVDを正本。wakubanは既に切替済み |
| caution (定義差確認要) | bataiju, bataiju_zogen, futan_juryo | 手動確認後に決定 |
| semantic_overlap | blinker vs blinker_shiyo_kubun, kyakushitsu vs kyakushitsu_hantei | 定義差あり。現状JRDB維持 |
| jrdb_only | idm, ten_shisu, manken_shirushi など全スコア指数 | JRDB固定。JVDに同値なし |
| jvd_only | barei, ijo_kubun_code, grade_code, track_code, haraimodoshi_* | JVD固定。既に正しく参照 |

---

## Phase1〜4 で切替対象となる主要カラム

### 切替確定（JVD優先）
| カラム | 現状 | 変更後 | 影響 |
|--------|------|--------|------|
| `wakuban` | jvd_se.wakuban_v → wakuban (**既に切替済み**) | 変更不要 | なし |
| `umakigo_code` | k.umakigo_code (JRDB) | v.umakigo_code (JVD) | ビン件数+11.8%。要リグレッションテスト |
| `kishu_minarai_code` | k.kishu_minarai_code (JRDB) | v.kishu_minarai_code (JVD) | ビン件数+11.8%。要リグレッションテスト |

### 要注意（手動判断）
| カラム | 現状 | 懸念 | アクション |
|--------|------|------|-----------|
| `bataiju` | k.bataiju (JRDB) | jvd_se.bataijuとの数値差? | DB直接で20件程度比較して定義確認 |
| `bataiju_zogen` | k.bataiju_zogen (JRDB) | jvd_se.zogen_saとの定義差? | 符号方向・単位の確認 |
| `futan_juryo` | k.futan_juryo (JRDB) | jvd_se.futan_juryo_rawとの差? | 既に両方参照済み。SQLで差異分析 |

---

## 変更優先順位

1. **P0 (最優先・今すぐ)**: ACTUAL_DB_SCHEMA_2293_COLUMNS.csvを実DBに合わせて更新 (139列のjrd_kyi_fixed)
2. **P1 (高)**: `umakigo_code` の参照をk.→v.に切替 → ビン件数増加で監査再実行が必要
3. **P1 (高)**: `kishu_minarai_code` の参照をk.→v.に切替 → 同上
4. **P2 (中)**: `bataiju` / `bataiju_zogen` / `futan_juryo` の定義差確認
5. **P3 (低)**: kyakushitsu vs kyakushitsu_hanteiの定義差分析（現状JRDB維持で問題なし）

---

## 変更で壊れる可能性がある箇所

| ファイル | 影響内容 |
|----------|---------|
| `factor_screening.py` (_LOAD_QUERY) | k.umakigo_code → v.umakigo_code に変更が必要 |
| `factor_screening.py` (_LOAD_QUERY) | k.kishu_minarai_code → v.kishu_minarai_code に変更が必要 |
| `backend/batch/master_combo_pipeline.py` | セグメント件数が変わるため再実行要 |
| `backend/batch/factor_investment_screening.py` | 全Phase再スクリーニング要 |
| `reports/production_search/segments/` | 全combo_results.csvの再計算要 |
| `reports/production_search/phase*_bin_detail*.csv` | ビン件数が変わるため再生成要 |
| `reports/source_of_truth/audit_factor_bins*.py` | 監査の再実施要 |

---

## 再監査が必要なファクター一覧

umakigo_code / kishu_minarai_code を切替た場合:
- 両ファクターのPhase1〜4全セグメントのビン件数監査
- 特にKEIBAJO_SURFACE_08_芝の manken_shirushi との掛け合わせcombosの再確認

bataiju / bataiju_zogen を切替た場合:
- 両ファクターの全ビン件数・採用判定の再評価

---

## 今後の実装原則

1. **JVDを正本**: 馬齢(barei)、着順(kakutei_chakujun)、オッズ(tansho_odds)、馬場(track_code)、グレード(grade_code)、着順ラベル(haraimodoshi_*)
2. **JRDBを正本**: 全スコア指数(idm, ten_shisu等)、予測マーク(manken_shirushi)、適性コード、輸送・休養情報
3. **JOIN経路**: jrd_kyi_fixed INNER JOIN は JRDB因子の分析に必要。JVD因子のみ分析する場合はjvd_se + jvd_ra + jvd_hrのみで可
4. **ビン件数の参照母数**: JRDB因子 → jrd_kyi_fixed JOINありの件数が正しい母数。JVD因子 → JVD全件数が母数
5. **スキーマ管理**: ACTUAL_DB_SCHEMA_2293_COLUMNS.csvは定期的に実DBと照合すること

---

## 注記

- **ACTUAL_DB_SCHEMA_2293_COLUMNS.csv は更新要**: jrd_kyi_fixedは139列だがCSVには38列のみ記載
- `jrd_kyi` (raw) にも同様の問題あり — 実DB132列だがCSVでも132列で整合
- jrd_kyi_fixedは jrd_kyi + 複数JRDBテーブルからの派生列を追加した拡張テーブル

---
*このドキュメントは factor_screening.py / factor_investment_screening.py / ACTUAL_DB_SCHEMA_2293_COLUMNS.csv / 実DBスキーマ の直接調査に基づく。推測なし。*

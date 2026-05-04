# JVD正本移行 修正版サマリー

生成日: 2026-05-04  
対象: factor_screening.py JVD切替 + Phase1〜4 ビン件数再監査

---

## 1. 実施した変更（factor_screening.py _LOAD_QUERY）

| カラム | 変更前 | 変更後 | 理由 |
|--------|--------|--------|------|
| `umakigo_code` | `k.umakigo_code` (JRDB) | `v.umakigo_code` (JVD) | JVD/JRDB同値確認済み。JVDが正本 |
| `kishu_minarai_code` | `k.kishu_minarai_code` (JRDB) | `v.kishu_minarai_code` (JVD) | JVD/JRDB同値確認済み。JVDが正本 |
| `bataiju` | `k.bataiju` (JRDB, **全NULL**) | `CAST(NULLIF(TRIM(v.bataiju),'') AS NUMERIC)` (JVD) | jrd_kyi_fixed.bataiju = 0件非NULL。**サイレントバグ修正** |
| `bataiju_zogen` | `k.bataiju_zogen` (JRDB, **全NULL**) | `CASE WHEN zogen_fugo='-' THEN -zogen_sa ELSE zogen_sa END` (JVD) | 同上。符号は zogen_fugo で付与 |
| `futan_juryo` | — | 変更なし | 既に `v.futan_juryo_raw/10.0`。変更不要 |

**変更ファイル**: [`backend/batch/factor_screening.py`](../../backend/batch/factor_screening.py) 行174, 178, 183

---

## 2. bataiju サイレントバグの影響範囲

- `bataiju` ファクター: 修正前は全行NULLだったためビン評価不能 → **修正済み**
- `bataiju_zogen` ファクター: 同様に全行NULL → **修正済み**
- `bataiju_change_bin`: `bataiju_actual`（v.bataiju）と `prev1_bataiju`（_PREV_QUERYからJVD）を使用しており、**修正前から正常動作していた**
- `prev1_bataiju_bin`: _PREV_QUERYが `jvd_se.bataiju` を直接参照するため **修正前から正常**

---

## 3. Phase1〜4 ビン件数再監査結果

### 概要

| Phase | 対象combo数 | 総ビン数 | n≥100ビン | n≥50ビン | 採用shortlist |
|-------|------------|---------|----------|---------|-------------|
| Phase1 | 33 | 4,051 | 846 | 1,140 | **1** |
| Phase2 | 116 | 46,663 | 816 | 5,958 | 0 |
| Phase3 | 313 | 301,907 | 1,720 | 12,155 | 0 |
| Phase4 | 168 | 330,937 | 765 | 4,653 | 0 |
| **合計** | **630** | **683,558** | **4,147** | **23,906** | **1** |

### 採用shortlist（Rule C: 全ビン≥500件）

| Phase | Segment | Factor/Combo | 採用レベル | 理由 |
|-------|---------|-------------|----------|------|
| Phase1 | KEIBAJO_SURFACE_08_芝 | manken_shirushi | 500 | 全ビン≥500 (min=965) |

---

## 4. JVD正本ルール 最終確定状態

| 分類 | 列名 | ソース | 状態 |
|------|------|--------|------|
| JVD済み（変更不要） | wakuban | v.wakuban_v | 確定 |
| JVD済み（変更不要） | futan_juryo | v.futan_juryo_raw/10.0 | 確定 |
| JVD済み（変更不要） | barei, ijo_kubun_code, grade_code, track_code | jvd_se/jvd_ra | 確定 |
| JVD切替済み（今回） | umakigo_code | v.umakigo_code | **完了** |
| JVD切替済み（今回） | kishu_minarai_code | v.kishu_minarai_code | **完了** |
| JVD切替済み（今回） | bataiju | v.bataiju (CAST NUMERIC) | **完了（バグ修正）** |
| JVD切替済み（今回） | bataiju_zogen | v.zogen_fugo + v.zogen_sa | **完了（バグ修正）** |
| JRDB固定 | idm, ten_shisu, manken_shirushi 等 全スコア指数 | k.* | 変更不要 |

---

## 5. 比較レポート・参照ドキュメント

- [`bataiju_futan_juryo_comparison.md`](bataiju_futan_juryo_comparison.md) — bataiju/zogen/futan_juryo のDB直接比較証拠
- [`jvd_priority_migration_plan.md`](jvd_priority_migration_plan.md) — 移行計画（結論行修正済み）
- [`column_overlap_matrix.csv`](column_overlap_matrix.csv) — JVD/JRDB重複カラム全量
- [`phase1_4_column_usage.csv`](phase1_4_column_usage.csv) — 49ファクター × 4フェーズの正本状況

---

## 6. 残課題

1. **ACTUAL_DB_SCHEMA_2293_COLUMNS.csv 更新**: jrd_kyi_fixedは実DB139列だがCSVには38列のみ記載（P0優先）
2. **master_combo_pipeline.py 再実行**: セグメント件数が変わったため全combo_results.csvの再計算が必要
3. **factor_investment_screening.py 再スクリーニング**: 全Phase再実行要

---

*根拠: DB直接クエリ + factor_screening.py ソースコード直接読取。推測なし。*

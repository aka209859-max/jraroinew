# bataiju / bataiju_zogen / futan_juryo JVD-JRDB 値比較レポート

生成日: 2026-05-03

---

## 結論（先出し）

| カラム | JRDBソース | JRDB非NULL件数 | JVDソース | JVD非NULL件数 | 判定 | 対応 |
|--------|-----------|---------------|---------|--------------|------|------|
| `bataiju` | k.bataiju (jrd_kyi_fixed) | **0件（全NULL）** | v.bataiju (jvd_se) | 737,321件 | JVD切替必須 | **完了** |
| `bataiju_zogen` | k.bataiju_zogen (jrd_kyi_fixed) | **0件（全NULL）** | v.zogen_sa + v.zogen_fugo (jvd_se) | 737,321件相当 | JVD切替必須 | **完了** |
| `futan_juryo` | k.futan_juryo (未参照) | — | v.futan_juryo_raw/10.0 (jvd_se) | 461,421件 | JVD済み（変更不要） | 変更なし |

---

## bataiju（馬体重）

### 調査結果

```
k.bataiju non-null count: 0  （jrd_kyi_fixed.bataiju = varchar型, 全行空白/NULL）
v.bataiju non-null count: 737,321
```

- `jrd_kyi_fixed.bataiju` は型は varchar だが全行が NULL または空白
- `jvd_se.bataiju` は 737,321件の実数値を保有
- _LOAD_QUERY で `k.bataiju` を選択していたため、`bataiju` ファクターは全行 NULL となっていた（**サイレントバグ**）

### 修正内容（factor_screening.py 行174）

```sql
-- BEFORE（バグ状態）:
k.bataiju, k.bataiju_zogen, k.kakutoku_shokin_ruikei,

-- AFTER（修正済み）:
CAST(NULLIF(TRIM(v.bataiju), '') AS NUMERIC) AS bataiju,
CASE WHEN v.zogen_fugo = '-'
     THEN -CAST(NULLIF(TRIM(v.zogen_sa), '') AS NUMERIC)
     ELSE  CAST(NULLIF(TRIM(v.zogen_sa), '') AS NUMERIC)
END AS bataiju_zogen,
k.kakutoku_shokin_ruikei,
```

---

## bataiju_zogen（馬体重増減）

### 調査結果

```
k.bataiju_zogen non-null count: 0  （同上、全NULL）
v.zogen_sa: 絶対値（0〜999kg）
v.zogen_fugo: '+' または '-'（各110万件程度）
```

- JVDでは増減量を `zogen_sa`（絶対値）+ `zogen_fugo`（符号）の2カラムで管理
- 符号適用後の signed value = `CASE WHEN zogen_fugo='-' THEN -zogen_sa ELSE zogen_sa END`
- 平均 |zogen_sa| ≈ 5.3 kg（正常範囲）

### bataiju_change_bin への影響

`bataiju_change_bin` は `bataiju_actual`（v.bataiju, JVD）と `prev1_bataiju`（_PREV_QUERY内で jvd_se.bataiju を LAG）を使用しており、**修正前から正しく動作していた**。bataiju_change_bin への影響なし。

---

## futan_juryo（負担重量）

### 調査結果

```
k.futan_juryo vs v.futan_juryo（生値）:
  match_without_div: 461,421件  （k = v）
  mismatch:              637件  （差異あり）
```

- 実コードでは既に `CAST(NULLIF(TRIM(v.futan_juryo), '') AS NUMERIC) AS futan_juryo_raw` として JVD から取得
- Python側で `/10.0` して `futan_juryo` 列に格納（単位: kg）
- `k.futan_juryo` は _LOAD_QUERY で**一切参照されていない**
- 637件の差異は生データの軽微な不一致（0.1〜0.2kg相当）。影響なし

**→ 変更不要。現状JVD済み。**

---

## 関連する _LOAD_QUERY 内の JVD 参照列

修正後の状態（正本確定）:

| 論理名 | SQLエイリアス | 参照元 | 備考 |
|--------|-------------|--------|------|
| bataiju（ファクター） | `bataiju` | `v.bataiju` JVD | **今回修正** |
| bataiju_zogen（ファクター） | `bataiju_zogen` | `v.zogen_fugo` + `v.zogen_sa` JVD | **今回修正** |
| bataiju_change_bin 用現在値 | `bataiju_actual` | `v.bataiju` JVD | 修正前から正常 |
| bataiju_change_bin 用前走値 | `prev1_bataiju` | `jvd_se.bataiju` via _PREV_QUERY | 修正前から正常 |
| futan_juryo | `futan_juryo_raw` → `/10.0` | `v.futan_juryo` JVD | 変更なし |
| zogen_sa（内部） | `zogen_sa` | `v.zogen_sa` JVD | 変更なし |
| zogen_fugo（内部） | `zogen_fugo` | `v.zogen_fugo` JVD | 変更なし |

---

*調査根拠: DB直接クエリによる非NULL件数確認（推測なし）*

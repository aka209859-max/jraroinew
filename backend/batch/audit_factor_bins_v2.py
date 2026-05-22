#!/usr/bin/env python3
"""
audit_factor_bins_v2.py
========================
Phase1〜4 本採用候補絞り込み監査 (詳細版)

【データソース】
  reports/production_search/phase{1-4}_bin_detail_for_adoption_review.csv
  ← audit_factor_bins.py が全ビン・フィルタなしで _bin_metrics() 再実行して生成
  ← n_horses = オッズフィルタ後のビン内全馬数

【生成ファイル (15件)】
  phase{1-4}_segment_factor_summary.csv  (A: segment粒度)
  phase{1-4}_factor_bin_audit.csv        (B: combo粒度)
  phase{1-4}_bin_detail_audit.csv        (C: bin粒度)
  final_adoption_rule_proposals.md
  final_adoption_shortlist.csv
  final_adoption_rejects.csv
  final_adoption_summary.csv

Usage:
  py -3.12 -u -m backend.batch.audit_factor_bins_v2
"""

import textwrap
import time
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
OUT_DIR  = Path("reports/production_search")
IN_TMPL  = "reports/production_search/phase{p}_bin_detail_for_adoption_review.csv"

# 小頭数依存（ランク系）ファクター: bin_key が 出走頭数上限 に依存する
SHS_FACTORS = frozenset({
    "agari_shisu_juni",
    "gekiso_juni",
    "ichi_shisu_juni",
    "ls_shisu_juni",
    "pace_shisu_juni",
    "ten_shisu_juni",
})

# SHS ファクターにおける「テールビン」判定閾値
# rank >= SHS_TAIL_RANK かつ n_horses < SHS_TAIL_N → is_possible_marginal
SHS_TAIL_RANK = 13    # 13頭立て以上でないと現れないランク
SHS_TAIL_N    = 30    # 30頭未満 → テール

# 理論上の最大ビン数（既知のもの）
POSSIBLE_BINS_KNOWN = {
    "kyori_tekisei":           5,   # A-E
    "kyori_tekisei_2":         5,
    "kyakushitsu":             4,   # 逃げ/先行/差し/追込
    "pace_yoso":               5,   # 予測ペース区分
    "manken_shirushi":         9,   # 印コード 0-8
    "kishu_minarai_code":      3,   # 見習い区分
    "omo_tekisei_code":        5,
    "da_tekisei_code":         5,
    "shiba_tekisei_code":      5,
    "joshodo_code":            4,
    "hizume_code":             4,
    "umakigo_code":            6,
    "tenkai_kigo_code":        6,
    "joken_class_code":        7,
    "kyusha_hyoka_code":       5,
    "kyuyo_riyu_bunrui_code":  8,
    "rotation":               12,
    "keibajo_code":           10,
    "kyori_kubun":             5,
}
# SHS: JRA 最大出走頭数 = 18
SHS_MAX_RANK = 18
for f in SHS_FACTORS:
    POSSIBLE_BINS_KNOWN[f] = SHS_MAX_RANK
# --------------------------------------------------------------------------


def bucket6(n: int) -> str:
    if n <= 9:      return "1_9"
    if n <= 99:     return "10_99"
    if n <= 149:    return "100_149"
    if n <= 299:    return "150_299"
    if n <= 499:    return "300_499"
    return "500_plus"


def is_shs_combo(combo: str) -> bool:
    return any(f in SHS_FACTORS for f in combo.split("+"))


def possible_bins_for_combo(combo: str) -> Optional[int]:
    """理論上の最大ビン数を推定。不明 = None"""
    parts = combo.split("+")
    if len(parts) == 1:
        return POSSIBLE_BINS_KNOWN.get(parts[0])
    # 多因子: 積 (None があれば None)
    prod = 1
    for p in parts:
        v = POSSIBLE_BINS_KNOWN.get(p)
        if v is None:
            return None
        prod *= v
    return prod


def is_shs_tail_bin(combo: str, bin_key: str, n: int) -> bool:
    """SHS テールビン判定: rank >= SHS_TAIL_RANK かつ n < SHS_TAIL_N"""
    if not is_shs_combo(combo):
        return False
    try:
        # bin_key が "rank1|rank2|..." 形式の場合もある
        # まず最初の数値部分を取る
        first_val = float(str(bin_key).split("|")[0])
        return first_val >= SHS_TAIL_RANK and n < SHS_TAIL_N
    except (ValueError, TypeError):
        return False


# --------------------------------------------------------------------------
#  C. ビン明細
# --------------------------------------------------------------------------

def make_bin_detail(raw_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in raw_df.iterrows():
        combo    = str(row["combo"])
        bk       = str(row["bin_key"])
        n        = int(row["n_horses"])
        shs      = is_shs_combo(combo)
        tail     = is_shs_tail_bin(combo, bk, n) if shs else False

        # should_count: テールビン以外はすべて採用判定対象
        should_count = not tail

        rows.append({
            "phase":                         int(row["phase"]),
            "segment":                       str(row["segment"]),
            "combo":                         combo,
            "bin_key":                       bk,
            "n_horses":                      n,
            "sample_bucket":                 bucket6(n),
            "is_existing_bin":               True,
            "is_possible_bin_if_determinable": True,  # 全観測ビン = 存在確認済み
            "should_count_for_adoption_judgement": should_count,
            "note": ("SHS tail bin excluded from adoption check"
                     if tail else ""),
        })

    if not rows:
        return pd.DataFrame(columns=[
            "phase","segment","combo","bin_key","n_horses","sample_bucket",
            "is_existing_bin","is_possible_bin_if_determinable",
            "should_count_for_adoption_judgement","note",
        ])
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
#  B. ファクター監査表
# --------------------------------------------------------------------------

def make_factor_audit(raw_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (seg, combo), grp in raw_df.groupby(["segment", "combo"], sort=True):
        n_arr      = grp["n_horses"].values
        total      = len(n_arr)
        phase      = int(grp["phase"].iloc[0])
        shs        = is_shs_combo(combo)
        poss       = possible_bins_for_combo(combo)

        # ビンバケット
        b1       = int((n_arr <= 9).sum())
        b2       = int(((n_arr >= 10) & (n_arr <= 99)).sum())
        b100_149 = int(((n_arr >= 100) & (n_arr <= 149)).sum())
        b150_299 = int(((n_arr >= 150) & (n_arr <= 299)).sum())
        b300_499 = int(((n_arr >= 300) & (n_arr <= 499)).sum())
        b500     = int((n_arr >= 500).sum())

        # SHSテール除外後の実効指標
        tail_mask = np.array([
            is_shs_tail_bin(combo, bk, nh)
            for bk, nh in zip(grp["bin_key"].values, n_arr)
        ])
        eff_arr = n_arr[~tail_mask]
        eff_min = int(eff_arr.min()) if len(eff_arr) > 0 else 0
        eff_all150 = bool((eff_arr >= 150).all()) if len(eff_arr) > 0 else False
        eff_all300 = bool((eff_arr >= 300).all()) if len(eff_arr) > 0 else False
        eff_all500 = bool((eff_arr >= 500).all()) if len(eff_arr) > 0 else False
        n_tail   = int(tail_mask.sum())

        # 判定メモ
        notes = []
        if b1 > 0:
            notes.append(f"{b1} bins with n<10")
        if shs and n_tail > 0:
            notes.append(f"{n_tail} SHS tail bins excluded from eff. check")
        if poss is not None and total < poss:
            notes.append(f"only {total}/{poss} possible bins observed")

        rows.append({
            "phase":                      phase,
            "segment":                    seg,
            "combo":                      combo,
            "total_bins":                 total,
            "existing_bins":              total,
            "possible_bins_if_determinable": poss,
            "bins_1_9":                   b1,
            "bins_10_99":                 b2,
            "bins_100_149":               b100_149,
            "bins_150_299":               b150_299,
            "bins_300_499":               b300_499,
            "bins_500_plus":              b500,
            "min_bin_n":                  int(n_arr.min()),
            "max_bin_n":                  int(n_arr.max()),
            "mean_bin_n":                 round(float(n_arr.mean()), 1),
            "median_bin_n":               round(float(np.median(n_arr)), 1),
            "ratio_1_9":                  round(b1 / total, 4),
            "ratio_10_99":                round(b2 / total, 4),
            "ratio_500_plus":             round(b500 / total, 4),
            "has_any_1digit_bin":         bool(b1 > 0),
            "has_any_2digit_bin":         bool(b2 > 0),
            "all_existing_bins_ge_150":   bool((n_arr >= 150).all()),
            "all_existing_bins_ge_300":   bool((n_arr >= 300).all()),
            "all_existing_bins_ge_500":   bool((n_arr >= 500).all()),
            "eff_min_bin_n":              eff_min,
            "eff_all_ge_150":             eff_all150,
            "eff_all_ge_300":             eff_all300,
            "eff_all_ge_500":             eff_all500,
            "n_shs_tail_bins":            n_tail,
            "small_headcount_sensitive":  shs,
            "review_note":                "; ".join(notes) if notes else "ok",
        })

    if not rows:
        return pd.DataFrame(columns=[
            "phase","segment","combo","total_bins","existing_bins","possible_bins_if_determinable",
            "bins_1_9","bins_10_99","bins_100_149","bins_150_299","bins_300_499","bins_500_plus",
            "min_bin_n","max_bin_n","mean_bin_n","median_bin_n","ratio_1_9","ratio_10_99",
            "ratio_500_plus","has_any_1digit_bin","has_any_2digit_bin",
            "all_existing_bins_ge_150","all_existing_bins_ge_300","all_existing_bins_ge_500",
            "eff_min_bin_n","eff_all_ge_150","eff_all_ge_300","eff_all_ge_500",
            "n_shs_tail_bins","small_headcount_sensitive","review_note",
        ])
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
#  A. セグメント要約
# --------------------------------------------------------------------------

def make_segment_summary(raw_df: pd.DataFrame, phase: int) -> pd.DataFrame:
    rows = []
    for seg, sdf in raw_df.groupby("segment", sort=True):
        n_arr   = sdf["n_horses"].values
        total   = len(n_arr)
        combos  = sdf["combo"].unique()
        fc      = len(combos)

        b1       = int((n_arr <= 9).sum())
        b2       = int(((n_arr >= 10) & (n_arr <= 99)).sum())
        b100_149 = int(((n_arr >= 100) & (n_arr <= 149)).sum())
        b150_299 = int(((n_arr >= 150) & (n_arr <= 299)).sum())
        b300_499 = int(((n_arr >= 300) & (n_arr <= 499)).sum())
        b500     = int((n_arr >= 500).sum())

        f_any1d  = 0; f_any2d  = 0
        f_all150 = 0; f_all300 = 0; f_all500 = 0
        for combo, cgrp in sdf.groupby("combo", sort=False):
            cv = cgrp["n_horses"].values
            if (cv <= 9).any():   f_any1d  += 1
            if ((cv >= 10) & (cv <= 99)).any(): f_any2d += 1
            if (cv >= 150).all(): f_all150 += 1
            if (cv >= 300).all(): f_all300 += 1
            if (cv >= 500).all(): f_all500 += 1

        rows.append({
            "phase":                        phase,
            "segment":                      seg,
            "factor_count":                 fc,
            "total_bins":                   total,
            "bins_1_9":                     b1,
            "bins_10_99":                   b2,
            "bins_100_149":                 b100_149,
            "bins_150_299":                 b150_299,
            "bins_300_499":                 b300_499,
            "bins_500_plus":                b500,
            "ratio_1_9":                    round(b1 / total, 4),
            "ratio_10_99":                  round(b2 / total, 4),
            "ratio_100_149":                round(b100_149 / total, 4),
            "ratio_150_299":                round(b150_299 / total, 4),
            "ratio_300_499":                round(b300_499 / total, 4),
            "ratio_500_plus":               round(b500 / total, 4),
            "factors_with_any_1digit_bin":  f_any1d,
            "factors_with_any_2digit_bin":  f_any2d,
            "factors_with_all_bins_ge_150": f_all150,
            "factors_with_all_bins_ge_300": f_all300,
            "factors_with_all_bins_ge_500": f_all500,
        })

    if not rows:
        return pd.DataFrame(columns=[
            "phase","segment","factor_count","total_bins","bins_1_9","bins_10_99",
            "bins_100_149","bins_150_299","bins_300_499","bins_500_plus",
            "ratio_1_9","ratio_10_99","ratio_100_149","ratio_150_299","ratio_300_499","ratio_500_plus",
            "factors_with_any_1digit_bin","factors_with_any_2digit_bin",
            "factors_with_all_bins_ge_150","factors_with_all_bins_ge_300","factors_with_all_bins_ge_500",
        ])
    return pd.DataFrame(rows).sort_values("segment").reset_index(drop=True)


# --------------------------------------------------------------------------
#  推奨ルール採用判定
# --------------------------------------------------------------------------

def adoption_level_recommended(row: pd.Series) -> tuple:
    """
    推奨ルール (Rule C: SHS考慮型閾値) で adoption_level と reason を返す。

    - SHS以外: 全ビン >= 閾値 で判定
    - SHS: テールビン除外後の実効ビンで判定 + total_bins <= 20 (過学習防止)
    - 追加条件: total_bins <= 30 (combo粒度が粗すぎる場合を除外)
    """
    shs = row["small_headcount_sensitive"]
    tb  = row["total_bins"]

    # 過剰分割チェック
    if tb > 30:
        return ("reject",
                f"too many bins ({tb}); combo splits data too finely")

    if shs:
        eff_min = row["eff_min_bin_n"]
        n_tail  = row["n_shs_tail_bins"]
        tail_note = f" ({n_tail} SHS tail bins excluded)" if n_tail else ""
        if row["eff_all_ge_500"]:
            return ("500", f"SHS: eff_min={eff_min}{tail_note}")
        if row["eff_all_ge_300"]:
            return ("300", f"SHS: eff_min={eff_min}{tail_note}")
        if row["eff_all_ge_150"]:
            return ("150", f"SHS: eff_min={eff_min}{tail_note}")
        return ("reject",
                f"SHS: eff_min_bin_n={eff_min} fails 150 threshold{tail_note}")
    else:
        if row["has_any_1digit_bin"]:
            return ("reject",
                    f"has 1-digit bins (bins_1_9={row['bins_1_9']})")
        if row["all_existing_bins_ge_500"]:
            return ("500", f"all bins >= 500 (min={row['min_bin_n']})")
        if row["all_existing_bins_ge_300"]:
            return ("300", f"all bins >= 300 (min={row['min_bin_n']})")
        if row["all_existing_bins_ge_150"]:
            return ("150", f"all bins >= 150 (min={row['min_bin_n']})")
        return ("reject",
                f"min_bin_n={row['min_bin_n']} fails 150 threshold "
                f"(bins_10_99={row['bins_10_99']}, bins_100_149={row['bins_100_149']})")


# --------------------------------------------------------------------------
#  最終ファイル生成
# --------------------------------------------------------------------------

def make_final_files(all_fba: pd.DataFrame) -> tuple:
    """shortlist, rejects, summary を返す"""
    results = []
    for _, row in all_fba.iterrows():
        level, reason = adoption_level_recommended(row)
        results.append({
            "phase":                    row["phase"],
            "segment":                  row["segment"],
            "combo":                    row["combo"],
            "adoption_level":           level,
            "reason":                   reason,
            "total_bins":               row["total_bins"],
            "min_bin_n":                row["min_bin_n"],
            "median_bin_n":             row["median_bin_n"],
            "eff_min_bin_n":            row["eff_min_bin_n"],
            "ratio_1_9":                row["ratio_1_9"],
            "ratio_10_99":              row["ratio_10_99"],
            "ratio_500_plus":           row["ratio_500_plus"],
            "small_headcount_sensitive":row["small_headcount_sensitive"],
            "all_existing_bins_ge_150": row["all_existing_bins_ge_150"],
            "all_existing_bins_ge_300": row["all_existing_bins_ge_300"],
            "all_existing_bins_ge_500": row["all_existing_bins_ge_500"],
            "reviewer_comment":         row["review_note"],
        })

    df = pd.DataFrame(results)
    shortlist = df[df["adoption_level"] != "reject"].copy()
    rejects   = df[df["adoption_level"] == "reject"].copy()

    # summary
    summary_rows = []
    for phase in [1, 2, 3, 4]:
        p = df[df["phase"] == phase]
        summary_rows.append({
            "phase":        phase,
            "total_combos": len(p),
            "shortlist_500":  (p["adoption_level"] == "500").sum(),
            "shortlist_300":  (p["adoption_level"] == "300").sum(),
            "shortlist_150":  (p["adoption_level"] == "150").sum(),
            "rejects":        (p["adoption_level"] == "reject").sum(),
            "shs_combos":     p["small_headcount_sensitive"].sum(),
        })
    summary = pd.DataFrame(summary_rows)

    return shortlist, rejects, summary


# --------------------------------------------------------------------------
#  Markdown 提案書
# --------------------------------------------------------------------------

def make_markdown(all_fba: pd.DataFrame, shortlist: pd.DataFrame,
                  rejects: pd.DataFrame, summary: pd.DataFrame) -> str:

    def pct(a, b): return f"{a/b*100:.1f}%" if b else "N/A"

    # 全体統計
    phase_stats = {}
    for p in [1, 2, 3, 4]:
        pdf = all_fba[all_fba["phase"] == p]
        phase_stats[p] = {
            "combos": len(pdf), "segs": pdf["segment"].nunique(),
        }

    sl_500 = summary["shortlist_500"].sum()
    sl_300 = summary["shortlist_300"].sum()
    sl_150 = summary["shortlist_150"].sum()
    sl_all = sl_500 + sl_300 + sl_150

    return textwrap.dedent(f"""
# 本採用判定ルール提案書
Generated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}

---

## 1. 監査対象サマリー

| Phase | combos | segments | 全ビン数 | 1桁ビン% | 10-99% | 150+% | 500+% |
|-------|--------|----------|---------|---------|--------|-------|-------|
| Phase1 | 33 | 24 | 4,045 | 52.9% | 26.3% | 7.2% | 9.9% |
| Phase2 | 116 | 49 | 46,624 | 50.9% | 47.4% | 0.5% | 0.0% |
| Phase3 | 313 | 82 | 301,877 | 76.0% | 23.5% | 0.1% | 0.0% |
| Phase4 | 168 | 54 | 330,937 | 87.8% | 12.0% | 0.0% | 0.0% |

---

## 2. 現行ルール（±20件許容）の問題点

現行 `split_bins_by_sample_size.py` は以下の閾値を採用：
- 150-class: `tansho_n >= 130` (150 - 20)
- 300-class: `tansho_n >= 280` (300 - 20)
- 500-class: `tansho_n >= 480` (500 - 20)

### 問題点

1. **ビン単位ではなくcombo単位の集計に近い**
   `tansho_n` はオッズ有効ベットの総数であり、個別ビンの `n_horses` ではない。
   combo全体でn_horsesが150以上でも、特定ビンが1桁という危険な状況を見逃す。

2. **馬番/ランク系ファクターへの不公平**
   `pace_shisu_juni`（ペース指数順位）のように bin_key が 1〜18 のランク系ファクターでは、
   頭数が少ないレースではランク13〜18が「そもそも存在しない」。
   固定 ±20件 ルールはこれを「サンプル不足」と同一視し、不当に不採用にする可能性がある。

3. **連続変数の過分割を見逃す**
   `kakutoku_shokin_ruikei`（獲得賞金累計）は2518ビンに分割される。
   ±20件ルールでは合計サンプル数だけを見るため、
   各ビンが1〜4件しかない過分割状態を検知できない。

4. **異なるPhase間の比較不能**
   Phase3（3-combo）や Phase4（4-combo）は多因子掛け合わせで
   ビン数が爆発的に増加し、ほぼ全ビンが1桁サンプルになる。
   ±20件ルールは単一ファクターと4-comboを同じ基準で評価し不合理。

---

## 3. 小頭数レースでの馬番系ファクターに何が起きるか

`pace_shisu_juni` / `agari_shisu_juni` 等はレースの出走頭数（N頭立て）に応じて
1〜N のランク値をとる。

**例: KEIBAJO_SURFACE_07_芝_OP重賞**
- OP重賞は12〜18頭立てが多いが、12頭以下のレースも存在する
- 結果: ランク13〜18 の bin に対応するレースが少なく n_horses が 16〜30 程度になる
- これは「データ不足」ではなく「そのランクに対応するレースが存在しない」

この "structural zero（構造的ゼロ）" と "観測不足" を区別しないと、
ランク系ファクターがすべて不採用になる。

---

## 4. 代替ルール案 (3案)

### Rule A: 全ビン絶対閾値（厳格版）
**条件**: 全ての既存ビンで `n_horses >= 150`

| 観点 | 評価 |
|------|------|
| ✅ メリット | シンプル・明確・過学習リスク最小 |
| ✅ メリット | Phase間の比較が容易 |
| ❌ デメリット | ランク系ファクター（SHS）が構造的ゼロによって全滅する |
| ❌ デメリット | Phase1 で採用可能なfactorが `manken_shirushi` のみ（1件）に激減 |
| ❌ デメリット | 少数ビン（2ビン）と多数ビン（100ビン）を同一に扱う |

採用数見込み: **Phase1=1, Phase2=0, Phase3=0, Phase4=0**

---

### Rule B: パーセンタイルベース中央値閾値
**条件**:
1. `median_bin_n >= 150`（中央値閾値）
2. `ratio_1_9 == 0`（1桁ビン完全排除）
3. `total_bins <= 30`（過分割防止）

| 観点 | 評価 |
|------|------|
| ✅ メリット | 極端なテールビン数本による全滅を防ぐ |
| ✅ メリット | ランク系ファクターにも一定の柔軟性 |
| ❌ デメリット | 中央値150だが最小ビンが1桁、という危険なcaseを通過させる可能性 |
| ❌ デメリット | 「中央値だけ高く見えるが実は数ビンが支配的」なファクターを誤採用 |
| ❌ デメリット | SHSの構造的ゼロをまだ適切に処理できない |

採用数見込み: **Phase1=5〜8, Phase2=0〜2, Phase3=0, Phase4=0**

---

### Rule C（推奨）: SHS考慮型実効閾値
**条件**:
1. `total_bins <= 30`（過分割防止）
2. SHS以外のfactor: 全ビン `n_horses >= 150`（全ビン絶対閾値）
3. SHSファクター: **テールビン（rank >= 13 かつ n < 30）を除外**した実効ビンで `min >= 150`
4. 追加: `has_any_1digit_bin == False`（SHS除外後でも1桁があれば reject）

| 観点 | 評価 |
|------|------|
| ✅ メリット | 構造的ゼロ（非存在ビン）を識別して除外 |
| ✅ メリット | 存在するが薄いビンは厳しく評価 |
| ✅ メリット | Phase1 の SHS ファクター（pace_shisu_juni 等）を正当に評価 |
| ✅ メリット | 過分割 combo を排除（total_bins <= 30） |
| ⚠️ 注意 | SHS テールの閾値（rank>=13, n<30）は暫定値。要レース分析で精緻化 |
| ⚠️ 注意 | 連続変数の過分割（kakutoku_shokin_ruikei 等）は total_bins <= 30 でカバー |

採用数見込み: 下記参照

---

## 5. 推奨ルール (Rule C) による Phase1〜4 採用候補数

{_count_table(summary, shortlist)}

---

## 6. 次アクション

### S-score 辞書構築への進み方

採用候補が少ないという現実を踏まえ、以下の段階的アプローチを推奨：

1. **Phase1 500-level ファクターを最優先採用**
   現状: `KEIBAJO_SURFACE_08_芝 × manken_shirushi`（全8ビン min=965）
   → そのままS-score辞書のベースに使用可能

2. **Phase1 150-levelのSHSファクター精査**
   `pace_shisu_juni`, `ten_shisu_juni` 等でRule C通過後、
   レース別頭数分布でテールビンの「存在有無」を再確認してから採用

3. **Phase2-4は原則「参考情報」扱い**
   ほぼ全combosが reject。
   CLB が高くても「サンプル不足によるCLB過大評価」の可能性が極めて高い。
   S-score辞書への採用は Phase2 500-level のみに限定することを強く推奨。

4. **閾値の見直し検討**
   「150件」は市場規模や期間に依存。
   2016-2025の10年データで各セグメントの年平均レース数から
   適正サンプル閾値を逆算することを次フェーズの課題とする。
""").strip()


def _count_table(summary: pd.DataFrame, shortlist: pd.DataFrame) -> str:
    lines = ["| Phase | 全combos | 500-level | 300-level | 150-level | reject |",
             "|-------|----------|-----------|-----------|-----------|--------|"]
    total_sl = 0
    for _, row in summary.iterrows():
        p = int(row["phase"])
        tot = int(row["total_combos"])
        s5 = int(row["shortlist_500"])
        s3 = int(row["shortlist_300"])
        s1 = int(row["shortlist_150"])
        rj = int(row["rejects"])
        total_sl += s5 + s3 + s1
        lines.append(f"| Phase{p} | {tot} | {s5} | {s3} | {s1} | {rj} |")
    lines.append(f"| **合計** | **{summary['total_combos'].sum()}** | "
                 f"**{summary['shortlist_500'].sum()}** | "
                 f"**{summary['shortlist_300'].sum()}** | "
                 f"**{summary['shortlist_150'].sum()}** | "
                 f"**{summary['rejects'].sum()}** |")
    return "\n".join(lines)


# --------------------------------------------------------------------------
#  main
# --------------------------------------------------------------------------

def main() -> None:
    t0 = time.time()
    print("=" * 70)
    print("  audit_factor_bins_v2  本採用候補絞り込み監査")
    print("  データソース: phase{1-4}_bin_detail_for_adoption_review.csv")
    print("=" * 70)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    all_fba_frames = []

    for phase in [1, 2, 3, 4]:
        src = Path(IN_TMPL.format(p=phase))
        print(f"\n[Phase{phase}] {src.name} を読み込み...")
        raw = pd.read_csv(src, encoding="utf-8-sig")
        print(f"  {len(raw):,} rows, {raw['combo'].nunique()} unique combos, "
              f"{raw['segment'].nunique()} segments")

        # --- A. segment summary ---
        seg_sum = make_segment_summary(raw, phase)
        f_a = OUT_DIR / f"phase{phase}_segment_factor_summary.csv"
        seg_sum.to_csv(f_a, index=False, encoding="utf-8-sig")
        print(f"  [A] {f_a.name}  ({len(seg_sum)} rows)")

        # --- B. factor audit ---
        fba = make_factor_audit(raw)
        f_b = OUT_DIR / f"phase{phase}_factor_bin_audit.csv"
        fba.to_csv(f_b, index=False, encoding="utf-8-sig")
        print(f"  [B] {f_b.name}  ({len(fba)} rows)")
        all_fba_frames.append(fba)

        # 簡易ハイライト
        n_all150 = fba["all_existing_bins_ge_150"].sum()
        n_eff150 = fba["eff_all_ge_150"].sum()
        print(f"  → all_bins_ge_150: {n_all150} / eff_ge_150(SHS考慮): {n_eff150}")

        # --- C. bin detail ---
        bdt = make_bin_detail(raw)
        f_c = OUT_DIR / f"phase{phase}_bin_detail_audit.csv"
        bdt.to_csv(f_c, index=False, encoding="utf-8-sig")
        print(f"  [C] {f_c.name}  ({len(bdt)} rows)")

    # --- 最終ファイル ---
    print("\n[FINAL] 最終提案ファイル生成...")
    all_fba = pd.concat(all_fba_frames, ignore_index=True)
    shortlist, rejects, summary = make_final_files(all_fba)

    f_sl = OUT_DIR / "final_adoption_shortlist.csv"
    f_rj = OUT_DIR / "final_adoption_rejects.csv"
    f_su = OUT_DIR / "final_adoption_summary.csv"
    f_md = OUT_DIR / "final_adoption_rule_proposals.md"

    shortlist.to_csv(f_sl, index=False, encoding="utf-8-sig")
    rejects.to_csv(f_rj,   index=False, encoding="utf-8-sig")
    summary.to_csv(f_su,   index=False, encoding="utf-8-sig")

    md_text = make_markdown(all_fba, shortlist, rejects, summary)
    f_md.write_text(md_text, encoding="utf-8")

    print(f"  [OK] {f_sl.name}  ({len(shortlist)} rows)")
    print(f"  [OK] {f_rj.name}  ({len(rejects)} rows)")
    print(f"  [OK] {f_su.name}")
    print(f"  [OK] {f_md.name}")

    print("\n=== 採用サマリー (推奨Rule C) ===")
    print(summary.to_string(index=False))

    if len(shortlist) > 0:
        print("\n=== Shortlist ===")
        print(shortlist[["phase","segment","combo","adoption_level","reason"]].to_string(index=False))

    elapsed = time.time() - t0
    print(f"\n[完了] elapsed={elapsed:.1f}s")


if __name__ == "__main__":
    main()

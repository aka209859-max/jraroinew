#!/usr/bin/env python3
"""
generate_bin_summary.py  ―  ファクター別・combo別の集約サマリーCSVを生成
出力:
  reports/source_of_truth/current_factor_bin_summary.csv   (44行・ファクター1行)
  reports/source_of_truth/current_combo_bin_summary.csv   (535行・combo1行)
"""
import sys
from pathlib import Path
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

FACTOR_JA = {
    "idm":"IDM指数","sogo_shisu":"総合指数","ten_shisu":"テン指数","pace_shisu":"ペース指数",
    "agari_shisu":"上がり指数","ichi_shisu":"位置指数","gekiso_shisu":"激走指数",
    "ninki_shisu":"人気指数","joho_shisu":"情報指数","manken_shisu":"万券指数",
    "kishu_shisu":"騎手指数","chokyo_shisu":"調教指数","kyusha_shisu":"厩舎指数",
    "ls_shisu_juni":"LS指数順位","ten_shisu_juni":"テン指数順位","pace_shisu_juni":"ペース指数順位",
    "agari_shisu_juni":"上がり指数順位","ichi_shisu_juni":"位置指数順位","gekiso_juni":"激走順位",
    "kishu_kitai_rentai_ritsu":"騎手期待連対率","kishu_kitai_tansho_ritsu":"騎手期待単勝率",
    "kishu_kitai_sanchakunai_ritsu":"騎手期待3着内率","uma_start_shisu":"馬スタート指数",
    "uma_deokure_ritsu":"馬出遅率","rotation":"ローテーション","bataiju":"馬体重",
    "bataiju_zogen":"馬体重増減","kakutoku_shokin_ruikei":"獲得賞金累計",
    "nyukyu_nannichimae":"入厩何日前","kijun_ninkijun_tansho":"基準人気順単勝",
    "keibajo_code":"競馬場","kyakushitsu":"脚質","class_code":"クラスコード",
    "joshodo_code":"上昇度","hizume_code":"蹄コード","blinker":"ブリンカー",
    "pace_yoso":"ペース予想","kishu_minarai_code":"騎手見習","kyori_tekisei":"距離適性",
    "kyori_tekisei_2":"距離適性2","shiba_tekisei_code":"芝適性","da_tekisei_code":"ダ適性",
    "omo_tekisei_code":"重適性","tenkai_kigo_code":"展開記号","manken_shirushi":"万券印",
    "kokyu_flag":"コ休フラグ","kyuyo_riyu_bunrui_code":"休養理由","kyusha_hyoka_code":"厩舎評価",
    "umakigo_code":"馬記号","joken_class_code":"条件クラス",
    "prev1_chakujun":"前走着順","prev2_chakujun":"前々走着順","prev3_chakujun":"3走前着順",
    "prev1_corner4":"前走4角通過順","prev1_corner4_bin":"前走4角通過順ビン",
    "prev1_blinker":"前走ブリンカー","prev1_kyakushitsu":"前走脚質",
    "prev1_keibajo":"前走競馬場","prev1_bataiju_bin":"前走馬体重ビン",
    "bataiju_change_bin":"馬体重変化ビン","kyori_change":"距離変化",
    "futan_juryo":"負担重量","kishu_rank":"騎手勝率ランク","chokyoshi_rank":"調教師勝率ランク",
    "wakuban":"枠番","umaban":"馬番","barei":"馬齢","babajotai_heavy":"馬場状態(重)",
    "sanchimei":"産地名","taikei_dou":"体型(胴)","taikei_tomo":"体型(トモ)",
    "bamei_hahachichi":"母父馬名","bamei_chichi":"父馬名","kishumei":"騎手名",
    "chokyoshimei":"調教師名","tozai_shozoku_code":"東西所属",
    "chokyo_yajirushi_code":"調教矢印コード","yuso_kubun":"輸送区分",
    "course_27":"コース27分類","surface":"馬場種別","kyori_kubun":"距離区分",
    "joa_odds_shisu":"JOA基準オッズ指数","kijun_odds_tansho":"基準単勝オッズ",
    "kijun_odds_fukusho":"基準複勝オッズ","kijun_ninkijun_fukusho":"基準複勝人気順",
    "shutoku_shokin_ruikei":"取得賞金累計",
}

BIN_RULE = {
    "prev1_bataiju_bin":   "20kg刻みバケット化 (// 20 * 20)",
    "bataiju_change_bin":  "±10kg刻みバケット化 (// 10 * 10)",
    "prev1_corner4_bin":   "4グループ集約 (1-3/4-6/7-9/10+)",
    "kishu_rank":          "騎手コード別勝率でランク付け",
    "chokyoshi_rank":      "調教師コード別勝率でランク付け",
    "bataiju":             "馬体重(kg)そのままビン化 [JVD v.bataiju]",
    "bataiju_zogen":       "馬体重増減(符号付き)そのままビン化 [zogen_fugo+zogen_sa]",
    "futan_juryo":         "負担重量(kg)そのままビン化 [v.futan_juryo_raw/10]",
    "rotation":            "ローテーション日数(整数)そのままビン化",
    "prev1_chakujun":      "前走着順(整数)そのままビン化",
    "prev2_chakujun":      "前々走着順(整数)そのままビン化",
    "prev3_chakujun":      "3走前着順(整数)そのままビン化",
    "prev1_corner4":       "前走4角通過順そのままビン化",
    "wakuban":             "枠番(1-8)そのままビン化 [JVD]",
    "umaban":              "馬番そのままビン化",
    "barei":               "馬齢(歳)そのままビン化",
    "manken_shirushi":     "万券印コード(1-8)そのままビン化",
    "kishu_minarai_code":  "騎手見習コード(0-4,9)そのままビン化 [JVD]",
    "kyakushitsu":         "脚質コード(1逃/2先/3差/4追)そのままビン化",
    "joken_class_code":    "条件クラスコード(0/1/2/3/9)そのままビン化",
    "pace_yoso":           "ペース予想コード(1-5)そのままビン化",
    "kyori_tekisei":       "距離適性コード(A-E)そのままビン化",
    "kyori_tekisei_2":     "距離適性2コード(A-E)そのままビン化",
    "umakigo_code":        "馬記号コードそのままビン化 [JVD]",
    "kyori_change":        "距離変化（未実装・全NULL）",
}
NUMERIC_FACTORS = {
    "idm","sogo_shisu","ten_shisu","pace_shisu","agari_shisu","ichi_shisu",
    "gekiso_shisu","ninki_shisu","joho_shisu","manken_shisu","kishu_shisu",
    "chokyo_shisu","kyusha_shisu","ls_shisu_juni","ten_shisu_juni",
    "pace_shisu_juni","agari_shisu_juni","ichi_shisu_juni","gekiso_juni",
    "kishu_kitai_rentai_ritsu","kishu_kitai_tansho_ritsu",
    "kishu_kitai_sanchakunai_ritsu","uma_start_shisu","uma_deokure_ritsu",
    "rotation","bataiju","bataiju_zogen","kakutoku_shokin_ruikei",
    "nyukyu_nannichimae","kijun_ninkijun_tansho","futan_juryo",
}
REDESIGN_REC = {
    "kishu_kitai_tansho_ritsu":      "10分位化(qcut q=10)推奨 / 現状537ビンは多すぎ",
    "kishu_kitai_rentai_ritsu":      "10分位化推奨",
    "kishu_kitai_sanchakunai_ritsu": "10分位化推奨",
    "uma_deokure_ritsu":             "5%刻みバケット推奨 (0/5/10/15/20+)",
    "kakutoku_shokin_ruikei":        "対数スケールor分位化推奨 (値幅大)",
    "kishumei":                      "高カーディナリティ → 別途ランク化",
    "chokyoshimei":                  "高カーディナリティ → 別途ランク化",
    "bamei_chichi":                  "高カーディナリティ → 血統グループ化",
    "bamei_hahachichi":              "高カーディナリティ → 血統グループ化",
    "sanchimei":                     "産地名グループ化推奨",
    "kyori_change":                  "実装必要（現状全NULL）",
    "bataiju_change_bin":            "現状±10kg刻み → ±5kg刻み細分化検討",
    "prev1_bataiju_bin":             "現状20kg刻み → 10kg刻み細分化検討",
    "rotation":                      "間隔グループ化推奨(14以下/15-28/29-56/57+)",
}

def get_bin_type(factor):
    if factor == "prev1_bataiju_bin":      return "manual_bucket"
    if factor in {"bataiju_change_bin","prev1_corner4_bin"}: return "derived_bucket"
    if factor in {"ls_shisu_juni","ten_shisu_juni","pace_shisu_juni","agari_shisu_juni",
                  "ichi_shisu_juni","gekiso_juni","prev1_chakujun","prev2_chakujun",
                  "prev3_chakujun","prev1_corner4","kishu_rank","chokyoshi_rank"}:
        return "rank_bucket"
    if factor in NUMERIC_FACTORS:          return "numeric_range"
    return "categorical"


def main():
    print("Loading phase CSVs ...")
    all_dfs = []
    for p in [1, 2, 3, 4]:
        df = pd.read_csv(f"reports/production_search/phase{p}_bin_detail_for_adoption_review.csv")
        all_dfs.append(df[["phase", "segment", "combo", "bin_key", "n_horses"]])
    df_all = pd.concat(all_dfs, ignore_index=True)
    df_all["bin_key"] = df_all["bin_key"].astype(str).str.strip()
    print(f"  Total: {len(df_all)} rows, {df_all['combo'].nunique()} combos")

    all_combos = sorted(df_all["combo"].unique())

    # -----------------------------------------------------------------------
    # 1. Factor-level summary
    # -----------------------------------------------------------------------
    all_factors = sorted({f for c in all_combos for f in c.split("+")})
    factor_rows = []
    for factor in all_factors:
        combos_with = [c for c in all_combos if factor in c.split("+")]
        parts_list = []
        for combo in combos_with:
            idx = combo.split("+").index(factor)
            csub = df_all[df_all["combo"] == combo][["bin_key", "n_horses"]].copy()
            csub["factor_bk"] = csub["bin_key"].apply(
                lambda bk: bk.split("|")[idx] if idx < len(bk.split("|")) else bk.split("|")[0]
            )
            parts_list.append(csub[["factor_bk", "n_horses"]])
        fbk_df = pd.concat(parts_list, ignore_index=True)
        fbk_agg = (
            fbk_df.groupby("factor_bk")["n_horses"]
            .agg(["sum", "max"])
            .reset_index()
            .rename(columns={"factor_bk": "bin_key", "sum": "total_n", "max": "max_n"})
        )
        fbk_agg["_sort"] = pd.to_numeric(fbk_agg["bin_key"], errors="coerce")
        fbk_agg = fbk_agg.sort_values(["_sort", "bin_key"], na_position="last").drop(columns=["_sort"])
        n_unique = len(fbk_agg)
        bk_num = pd.to_numeric(fbk_agg["bin_key"], errors="coerce")
        bmin = float(bk_num.min()) if bk_num.notna().any() else None
        bmax = float(bk_num.max()) if bk_num.notna().any() else None
        all_bk_str = (
            ", ".join(fbk_agg["bin_key"].tolist())
            if n_unique <= 30
            else f"({n_unique}個 → compact CSVに全件)"
        )
        sample_bk = ", ".join(fbk_agg["bin_key"].head(15).tolist())
        max_n = int(fbk_agg["max_n"].max()) if n_unique > 0 else 0
        min_n = int(fbk_agg["max_n"].min()) if n_unique > 0 else 0
        btype = get_bin_type(factor)
        rule  = BIN_RULE.get(factor,
            "数値そのままビン化 (監査:groupby raw / スクリーニング:qcut q=10)"
            if factor in NUMERIC_FACTORS else "カテゴリ値そのままビン化")
        rec = REDESIGN_REC.get(factor, "")
        if n_unique > 50 and not rec:
            rec = f"ビン数多({n_unique}個) → 集約推奨"
        factor_rows.append({
            "factor_name":               factor,
            "factor_name_ja":            FACTOR_JA.get(factor, f"【要確認】{factor}"),
            "n_combos_using":            len(combos_with),
            "n_unique_bins":             n_unique,
            "bin_type":                  btype,
            "current_bin_rule":          rule,
            "bin_value_min":             bmin,
            "bin_value_max":             bmax,
            "max_n_horses_per_bin":      max_n,
            "min_n_horses_per_bin":      min_n,
            "all_bin_keys_le30":         all_bk_str,
            "sample_bin_keys_top15":     sample_bk,
            "redesign_recommendation":   rec,
        })

    factor_df = pd.DataFrame(factor_rows)
    out1 = "reports/source_of_truth/current_factor_bin_summary.csv"
    factor_df.to_csv(out1, index=False, encoding="utf-8-sig")
    print(f"[OK] {out1}  ({len(factor_df)} rows)")

    # -----------------------------------------------------------------------
    # 2. Combo-level summary
    # -----------------------------------------------------------------------
    combo_rows = []
    for combo in all_combos:
        factors = combo.split("+")
        csub = df_all[df_all["combo"] == combo]
        n_bins = csub["bin_key"].nunique()
        n_segs = csub["segment"].nunique()
        phases = "+".join(sorted(csub["phase"].astype(str).unique()))
        max_n  = int(csub["n_horses"].max())
        min_n  = int(csub["n_horses"].min())
        bin_agg = (
            csub.groupby("bin_key")["n_horses"].sum().reset_index()
        )
        bin_agg["_sort"] = pd.to_numeric(bin_agg["bin_key"].str.split("|").str[0], errors="coerce")
        bin_agg = bin_agg.sort_values(["_sort", "bin_key"]).drop(columns=["_sort"])
        all_bk = (
            ", ".join(bin_agg["bin_key"].tolist())
            if n_bins <= 20
            else f"({n_bins}個)"
        )
        sample_bk = ", ".join(bin_agg["bin_key"].head(10).tolist())
        combo_rows.append({
            "combo":              combo,
            "combo_ja":           "＋".join(FACTOR_JA.get(f, f"【要確認】{f}") for f in factors),
            "phases":             phases,
            "n_segments":         n_segs,
            "n_bins_total":       n_bins,
            "max_n_horses":       max_n,
            "min_n_horses":       min_n,
            "all_bin_keys_le20":  all_bk,
            "sample_bin_keys":    sample_bk,
            "bin_type_primary":   get_bin_type(factors[0]),
            "current_bin_rule":   BIN_RULE.get(factors[0],
                "数値そのままビン化" if factors[0] in NUMERIC_FACTORS else "カテゴリ値そのままビン化"),
        })
    combo_df = pd.DataFrame(combo_rows)
    out2 = "reports/source_of_truth/current_combo_bin_summary.csv"
    combo_df.to_csv(out2, index=False, encoding="utf-8-sig")
    print(f"[OK] {out2}  ({len(combo_df)} rows)")

    # Print factor summary
    print()
    print("=== Factor Summary ===")
    cols = ["factor_name","factor_name_ja","n_unique_bins","bin_type","bin_value_min","bin_value_max","redesign_recommendation"]
    print(factor_df[cols].to_string(index=False))

    no_ja = [f for f in all_factors if f not in FACTOR_JA]
    print(f"\n日本語名なしファクター: {len(no_ja)}  → {no_ja}")
    print(f"\n完了: {out1}, {out2}")


if __name__ == "__main__":
    main()

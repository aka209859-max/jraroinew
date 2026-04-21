#!/usr/bin/env python3
"""
generate_report.py
==================
採用ファクター一覧レポートと全体スコアリングレポートを生成する。

Usage:
  py -3.12 reports/scoring/generate_report.py
"""

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

# ── Paths ─────────────────────────────────────────────────────────────────────
_HERE         = Path(__file__).parent          # reports/scoring/
_SCREENING    = _HERE.parent / "screening"

ADOPTION_CSV  = _SCREENING / "factor_adoption_result.csv"
F1_CSV        = _HERE / "bin_scores_formula1.csv"
F2_CSV        = _HERE / "bin_scores_formula2.csv"
SUMMARY_CSV   = _HERE / "scoring_summary.csv"
OUT_FACTORS   = _HERE / "adopted_factors_list.txt"
OUT_REPORT    = _HERE / "scoring_report.txt"


# ── CSV loader ────────────────────────────────────────────────────────────────

def _read(path: Path) -> pd.DataFrame:
    for enc in ("utf-8-sig", "utf-8", "cp932"):
        try:
            return pd.read_csv(path, encoding=enc)
        except (UnicodeDecodeError, LookupError):
            continue
    raise RuntimeError(f"Cannot read: {path}")


# ── Output 1: adopted_factors_list.txt ───────────────────────────────────────

def build_factors_list(adoption_df: pd.DataFrame, f2_bins: int) -> str:
    """
    採用ファクター一覧（式2適用）を文字列で返す。
    ソート: pass_rate DESC → avg_place_roi DESC
    """
    adopted = adoption_df[adoption_df["decision"] == "採用"].copy()

    # 障害レース除外: segment に「障」を含む行を除外
    shogai_mask = adopted["segment"].str.contains("\u969c", na=False)
    shogai_count = int(shogai_mask.sum())
    if shogai_count > 0:
        print(f"[INFO] build_factors_list: excluding {shogai_count} 障害 segment rows")
        adopted = adopted[~shogai_mask].copy()

    adopted = adopted.sort_values(
        ["pass_rate", "avg_place_roi"], ascending=[False, False]
    ).reset_index(drop=True)

    lines = []
    sep = "=" * 65

    lines.append(sep)
    lines.append("採用ファクター一覧（式2適用）")
    lines.append(f"合計: {len(adopted):,}ファクター / {f2_bins:,}ビン")
    lines.append(sep)
    lines.append("")

    for i, row in adopted.iterrows():
        no       = i + 1
        segment  = str(row["segment"])
        factors  = str(row["factors"])
        ftype    = str(row.get("type",  ""))
        grade    = str(row.get("grade", ""))
        score_std= float(row.get("score_std", 0.0))
        total_b  = int(row.get("total_bins",  0))
        valid_b  = int(row.get("valid_bins",  0))
        pass_b   = int(row.get("pass_bins",   0))
        pass_r   = float(row.get("pass_rate", 0.0))
        avg_pr   = float(row.get("avg_place_roi", 0.0))
        avg_wr   = float(row.get("avg_win_roi",   0.0))

        lines.append(f"[No.{no:03d}] {segment} | {factors}")
        lines.append(f"  - type: {ftype} | grade: {grade} | score_std: {score_std:.3f}")
        lines.append(
            f"  - total_bins: {total_b} | valid_bins: {valid_b} | "
            f"pass_bins: {pass_b} | pass_rate: {pass_r:.3f}"
        )
        lines.append(
            f"  - avg_place_roi: {avg_pr:.1f}% | avg_win_roi: {avg_wr:.1f}%"
        )
        lines.append("")

    return "\n".join(lines)


# ── Output 2: scoring_report.txt ─────────────────────────────────────────────

def build_scoring_report(
    summary_df: pd.DataFrame,
    f1_bins: int,
    f2_bins: int,
) -> str:
    lines = []
    sep   = "=" * 65
    now   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── Header ────────────────────────────────────────────────────
    lines += [
        sep,
        "BIN SCORING REPORT",
        f"生成日時: {now}",
        sep,
        "",
    ]

    # ── 概要 ──────────────────────────────────────────────────────
    f1_df   = summary_df[summary_df["formula"] == "formula1"]
    f2_df   = summary_df[summary_df["formula"] == "formula2"]
    f1_pats = len(f1_df)
    f2_facs = len(f2_df)
    total_b = f1_bins + f2_bins

    lines += [
        "■ 概要",
        f"  式1（相対評価）: {f1_pats}パターン / {f1_bins:,}ビン / スコア範囲 -12.0〜+12.0",
        f"  式2（絶対評価）: {f2_facs:,}ファクター / {f2_bins:,}ビン / スコア範囲 -10.0〜+10.0",
        f"  合計: {f1_pats + f2_facs:,}パターン / {total_b:,}ビン",
        "",
    ]

    # ── 式1 パターン別サマリ ──────────────────────────────────────
    lines.append("■ 式1 パターン別サマリ")
    col_w = [45, 6, 9, 9, 9]
    hdr = (
        f"  {'パターン':<{col_w[0]}} {'bins':>{col_w[1]}} "
        f"{'avg_score':>{col_w[2]}} {'max_score':>{col_w[3]}} {'min_score':>{col_w[4]}}"
    )
    lines.append(hdr)
    lines.append("  " + "-" * (sum(col_w) + 4))
    for _, r in f1_df.iterrows():
        lines.append(
            f"  {str(r['name']):<{col_w[0]}} {int(r['total_bins']):>{col_w[1]}} "
            f"{r['avg_score']:>{col_w[2]}.3f} {r['max_score']:>{col_w[3]}.1f} "
            f"{r['min_score']:>{col_w[4]}.1f}"
        )
    lines.append("")

    # ── 式2 セグメント別集計 ──────────────────────────────────────
    lines.append("■ 式2 セグメント別集計")
    f2_df_c = f2_df.copy()
    f2_df_c["seg"] = f2_df_c["name"].str.split(" | ").str[0]

    seg_grp = (
        f2_df_c.groupby("seg", sort=True)
        .agg(
            factor_count=("name",       "count"),
            total_bins  =("total_bins", "sum"),
            avg_score   =("avg_score",  "mean"),
            max_score   =("max_score",  "max"),
        )
        .reset_index()
        .sort_values("factor_count", ascending=False)
    )

    sw = [20, 6, 7, 9, 9]
    sh = (
        f"  {'セグメント':<{sw[0]}} {'件数':>{sw[1]}} "
        f"{'ビン数':>{sw[2]}} {'avg_score':>{sw[3]}} {'max_score':>{sw[4]}}"
    )
    lines.append(sh)
    lines.append("  " + "-" * (sum(sw) + 4))
    for _, r in seg_grp.iterrows():
        lines.append(
            f"  {str(r['seg']):<{sw[0]}} {int(r['factor_count']):>{sw[1]}} "
            f"{int(r['total_bins']):>{sw[2]}} {r['avg_score']:>{sw[3]}.3f} "
            f"{r['max_score']:>{sw[4]}.1f}"
        )
    lines.append("")

    # ── 式2 TOP30 高スコアファクター ──────────────────────────────
    lines.append("■ 式2 TOP30 高スコアファクター（max_score DESC）")
    top30 = f2_df.nlargest(30, "max_score").reset_index(drop=True)

    lines.append(
        f"  {'rank':>4}  {'name':<65} {'max_score':>9} {'avg_score':>9} {'total_bins':>10}"
    )
    lines.append("  " + "-" * 102)
    for i, r in top30.iterrows():
        lines.append(
            f"  {i+1:>4}  {str(r['name']):<65} "
            f"{r['max_score']:>9.1f} {r['avg_score']:>9.3f} {int(r['total_bins']):>10}"
        )
    lines.append("")

    # ── 式1 適用ルール ─────────────────────────────────────────────
    lines += [
        "■ 式1 適用ルール",
        "  ・①〜⑤の5パターン（8ファクター）はCEO定義の固定ルール",
        "  ・スクリーニング結果や採用判定とは無関係に常に適用",
        "  ・派生（クロス追加）は禁止",
        "",
    ]

    # ── 得点付与ロジック ──────────────────────────────────────────
    lines += [
        "■ 得点付与ロジック",
        "  各馬の最終スコア = 式1合計 × 0.2 + 式2合計 × 0.8",
        "  式1: 8パターンのスコアを合算（各 -12〜+12）",
        "  式2: 615ファクターのスコアを合算（各 -10〜+10）",
        "",
    ]

    # ── ファイル一覧 ──────────────────────────────────────────────
    lines += [
        "■ ファイル一覧",
        f"  - reports/scoring/bin_scores_formula1.csv（{f1_bins:,}行）",
        f"  - reports/scoring/bin_scores_formula2.csv（{f2_bins:,}行）",
        f"  - reports/scoring/scoring_summary.csv（{len(summary_df):,}行）",
        "  - reports/scoring/adopted_factors_list.txt",
        "  - reports/scoring/scoring_report.txt",
        "",
    ]

    return "\n".join(lines)


# ── Output 3: adopted_factors_by_segment.txt ─────────────────────────────────

SEGMENT_LABELS = {
    "GLOBAL":                  "全体（芝ダ共通）",
    "COURSE_27":               "コース27分類",
    "SURFACE_2_\u829d":        "全場芝",
    "SURFACE_2_\u30c0":        "全場ダート",
    "KEIBAJO_SURFACE_01_\u829d": "札幌芝",
    "KEIBAJO_SURFACE_01_\u30c0": "札幌ダート",
    "KEIBAJO_SURFACE_02_\u829d": "函館芝",
    "KEIBAJO_SURFACE_02_\u30c0": "函館ダート",
    "KEIBAJO_SURFACE_03_\u829d": "福島芝",
    "KEIBAJO_SURFACE_03_\u30c0": "福島ダート",
    "KEIBAJO_SURFACE_04_\u829d": "新潟芝",
    "KEIBAJO_SURFACE_04_\u30c0": "新潟ダート",
    "KEIBAJO_SURFACE_05_\u829d": "東京芝",
    "KEIBAJO_SURFACE_05_\u30c0": "東京ダート",
    "KEIBAJO_SURFACE_06_\u829d": "中山芝",
    "KEIBAJO_SURFACE_06_\u30c0": "中山ダート",
    "KEIBAJO_SURFACE_07_\u829d": "中京芝",
    "KEIBAJO_SURFACE_07_\u30c0": "中京ダート",
    "KEIBAJO_SURFACE_08_\u829d": "京都芝",
    "KEIBAJO_SURFACE_08_\u30c0": "京都ダート",
    "KEIBAJO_SURFACE_09_\u829d": "阪神芝",
    "KEIBAJO_SURFACE_09_\u30c0": "阪神ダート",
    "KEIBAJO_SURFACE_10_\u829d": "小倉芝",
    "KEIBAJO_SURFACE_10_\u30c0": "小倉ダート",
}

# セグメント表示順（上記の定義順）
SEGMENT_ORDER = list(SEGMENT_LABELS.keys())

FACTOR_LABELS = {
    "kishu_rank": "騎手ランク",
    "barei": "馬齢",
    "babajotai_heavy": "馬場状態（重分類）",
    "uma_deokure_ritsu": "出遅れ率",
    "kyi_kyusha_rank": "厩舎ランク（KYI）",
    "shirushi_code_1": "印コード1",
    "shirushi_code_2": "印コード2",
    "shirushi_code_3": "印コード3",
    "shirushi_code_4": "印コード4",
    "shirushi_code_5": "印コード5",
    "shirushi_code_6": "印コード6",
    "shirushi_code_7": "印コード7",
    "gekiso_type": "激走タイプ",
    "kyakushitsu": "脚質",
    "prev1_keibajo": "前走競馬場",
    "joken_class_code": "条件クラス",
    "yuso_kubun": "輸送区分",
    "chokyoshi_rank": "調教師ランク",
    "bac_tosu": "出走頭数",
    "agari_shisu": "上がり指数",
    "pace_shisu": "ペース指数",
    "moshoku_code": "毛色コード",
    "tenkai_kigo_code": "展開記号",
    "ten_shisu": "テン指数",
    "idm": "IDM",
    "manken_shirushi": "万券印",
    "babajotai_code_dirt": "ダート馬場状態",
    "bataiju_change_bin": "馬体重増減（区分）",
    "futan_juryo": "斤量",
    "bac_juryo_shubetsu_code": "負担重量種別",
    "kyori_tekisei": "距離適性",
    "uma_tokki_1": "馬特記1",
    "uma_tokki_2": "馬特記2",
    "uma_tokki_3": "馬特記3",
    "uma_start_shisu": "スタート指数",
    "ichi_shisu_juni": "位置指数順位",
    "shutoku_shokin_ruikei": "獲得賞金累計",
    "kohan_3f_sa": "後半3F差",
    "rotation": "ローテーション",
    "kijun_odds_fukusho": "基準複勝オッズ",
    "prev2_chakujun": "前2走着順",
    "prev1_chakujun": "前走着順",
    "prev3_chakujun": "前3走着順",
    "manken_shisu": "万券指数",
    "kakutoku_shokin_ruikei": "獲得賞金累計",
    "pace_yoso": "ペース予想",
    "ls_shisu_juni": "LS指数順位",
    "kishu_minarai_code": "騎手見習い",
    "agari_shisu_juni": "上がり指数順位",
    "goal_juni": "ゴール順位",
    "goal_sa": "ゴール差",
    "dochu_juni": "道中順位",
    "dochu_sa": "道中差",
    "gekiso_juni": "激走指数順位",
    "gekiso_shisu": "激走指数",
    "prev1_bataiju_bin": "前走馬体重（区分）",
    "prev1_corner4": "前走4角位置",
    "prev1_kyakushitsu": "前走脚質",
    "kijun_ninkijun_tansho": "基準人気順（単勝）",
    "kijun_ninkijun_fukusho": "基準人気順（複勝）",
    "kijun_odds_tansho": "基準単勝オッズ",
    "joa_odds_shisu": "JOAオッズ指数",
    "joa_ls_shisu": "JOA LS指数",
    "yoso_juni": "予想順位",
    "taikei_dou": "体型（胴）",
    "taikei_tomo": "体型（トモ）",
    "hizume_code": "蹄コード",
    "class_code": "クラスコード",
    "kyusha_shisu": "厩舎指数",
    "chokyo_shisu": "調教指数",
    "kishu_shisu": "騎手指数",
    "kishu_kitai_rentai_ritsu": "騎手期待連対率",
    "kishu_kitai_sanchakunai_ritsu": "騎手期待3着内率",
    "kishu_kitai_tansho_ritsu": "騎手期待単勝率",
    "sogo_shisu": "総合指数",
    "ninki_shisu": "人気指数",
    "joho_shisu": "情報指数",
    "chokyo_yajirushi_code": "調教矢印",
    "hobokusaki_rank": "放牧先ランク",
    "nyukyu_nannichimae": "入厩何日前",
    "kyori": "距離",
    "kyori_tekisei_2": "距離適性2",
    "kyori_kubun": "距離区分",
    "omo_tekisei_code": "重適性",
    "wakuban": "枠番",
    "prev1_bataiju": "前走馬体重",
    "track_code": "トラックコード",
    "tozai_shozoku_code": "東西所属",
    "kishumei": "騎手名",
    "chokyoshimei": "調教師名",
    "bamei_chichi": "父馬名",
    "bamei_hahachichi": "母父馬名",
    "keibajo_code": "競馬場",
    "tenko_code": "天候",
    "kyusha_hyoka_code": "厩舎評価",
    "kokyu_flag": "国休フラグ",
    "babajotai_code": "馬場状態コード",
    "prev1_corner4_bin": "前走4角位置（区分）",
    "bac_jouken": "レース条件",
    "bac_shubetsu": "レース種別",
    "bac_grade": "グレード",
    "umaban_clean": "馬番",
    "yy_int": "YY値",
    "sanchimei": "産地名",
    "ten_shisu_juni": "テン指数順位",
    "pace_shisu_juni": "ペース指数順位",
    "ichi_shisu": "位置指数",
    "joho_shisu": "情報指数",
    "kyusha_rank": "厩舎ランク",
    "prev1_blinker": "前走ブリンカー",
    "blinker": "ブリンカー",
    "prev1_bataiju_bin": "前走馬体重（区分）",
    "taikei_sogo_1": "体型総合1",
    "taikei_sogo_2": "体型総合2",
    "taikei_sogo_3": "体型総合3",
}


def _factor_ja(factors_str: str) -> str:
    """
    ファクター名を日本語化する。
    - 単体: "kishu_rank" → "kishu_rank（騎手ランク）"
    - クロス: "a+b" → "a（A） × b（B）"
    """
    parts = [p.strip() for p in factors_str.split("+")]
    ja_parts = []
    for p in parts:
        label = FACTOR_LABELS.get(p)
        ja_parts.append(f"{p}（{label}）" if label else p)
    return " × ".join(ja_parts)


def build_factors_by_segment(adoption_df: pd.DataFrame) -> str:
    """セグメント別採用ファクター一覧を文字列で返す。"""
    # 採用 + 障害除外 + dedup
    df = adoption_df[adoption_df["decision"] == "\u63a1\u7528"].copy()
    shogai = df["segment"].str.contains("\u969c", na=False)
    df = df[~shogai].drop_duplicates(subset=["segment", "factors"]).copy()

    total = len(df)
    seg_counts = df["segment"].value_counts().to_dict()

    lines = []
    sep_wide = "=" * 65
    sep_seg  = "\u2501" * 38   # ━

    lines += [
        sep_wide,
        "\u63a1\u7528\u30d5\u30a1\u30af\u30bf\u30fc\u4e00\u89a7\uff08\u30bb\u30b0\u30e1\u30f3\u30c8\u5225\uff09",  # 採用ファクター一覧（セグメント別）
        f"\u5408\u8a08: {total:,}\u30d5\u30a1\u30af\u30bf\u30fc",  # 合計: XXXファクター
        sep_wide,
        "",
    ]

    # セグメント処理順: SEGMENT_ORDER に従い、データにあるものだけ出力
    # SEGMENT_ORDER にないセグメントは末尾に追加
    seen_segs = set(SEGMENT_ORDER)
    extra_segs = sorted(s for s in seg_counts if s not in seen_segs)
    ordered_segs = [s for s in SEGMENT_ORDER if s in seg_counts] + extra_segs

    for seg in ordered_segs:
        label = SEGMENT_LABELS.get(seg, seg)
        count = seg_counts.get(seg, 0)

        lines += [
            sep_seg,
            f"\u3010{seg}\u3011{label}\uff08{count}\u4ef6\uff09",   # 【seg】label（N件）
            sep_seg,
        ]

        seg_df = (
            df[df["segment"] == seg]
            .sort_values(["pass_rate", "avg_place_roi"], ascending=[False, False])
            .reset_index(drop=True)
        )

        for i, row in seg_df.iterrows():
            factors_str = str(row["factors"])
            fja  = _factor_ja(factors_str)
            pr   = float(row.get("pass_rate",     0.0))
            apr  = float(row.get("avg_place_roi", 0.0))
            lines.append(
                f"  {i + 1:>3}: {fja}"
                f" | pass_rate: {pr:.3f} | place_roi: {apr:.1f}%"
            )

        lines.append("")

    return "\n".join(lines)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    print("[INFO] Loading CSVs...")
    adoption_df = _read(ADOPTION_CSV)
    summary_df  = _read(SUMMARY_CSV)
    f1_df_raw   = _read(F1_CSV)
    f2_df_raw   = _read(F2_CSV)

    f1_bins = len(f1_df_raw)
    f2_bins = len(f2_df_raw)

    # ── Output 1: adopted_factors_list.txt ─────────────────────────
    print("[INFO] Building adopted_factors_list.txt...")
    factors_txt = build_factors_list(adoption_df, f2_bins)
    OUT_FACTORS.write_text(factors_txt, encoding="utf-8")
    print(f"[OK] {OUT_FACTORS}  ({factors_txt.count(chr(10)):,} lines)")

    # ── Output 2: scoring_report.txt ───────────────────────────────
    print("[INFO] Building scoring_report.txt...")
    report_txt = build_scoring_report(summary_df, f1_bins, f2_bins)
    OUT_REPORT.write_text(report_txt, encoding="utf-8")
    print(f"[OK] {OUT_REPORT}  ({report_txt.count(chr(10)):,} lines)")

    # ── Console preview (first 100 lines each) ─────────────────────
    print()
    def _print_safe(text: str) -> None:
        """Print with cp932-safe fallback for non-encodable chars."""
        enc = sys.stdout.encoding or "cp932"
        print(text.encode(enc, errors="replace").decode(enc))

    _print_safe("=" * 70)
    _print_safe("adopted_factors_list.txt (first 100 lines)")
    _print_safe("=" * 70)
    lines_f = factors_txt.splitlines()
    for ln in lines_f[:100]:
        _print_safe(ln)
    if len(lines_f) > 100:
        _print_safe(f"... ({len(lines_f) - 100:,} more lines)")

    print()
    _print_safe("=" * 70)
    _print_safe("scoring_report.txt (first 100 lines)")
    _print_safe("=" * 70)
    lines_r = report_txt.splitlines()
    for ln in lines_r[:100]:
        _print_safe(ln)
    if len(lines_r) > 100:
        _print_safe(f"... ({len(lines_r) - 100:,} more lines)")

    # ── Output 3: adopted_factors_by_segment.txt ──────────────────
    print("[INFO] Building adopted_factors_by_segment.txt...")
    by_seg_txt = build_factors_by_segment(adoption_df)
    out_by_seg = _HERE / "adopted_factors_by_segment.txt"
    out_by_seg.write_text(by_seg_txt, encoding="utf-8")
    print(f"[OK] {out_by_seg}  ({by_seg_txt.count(chr(10)):,} lines)")

    # ── Console: segment summary ───────────────────────────────────
    print()
    _print_safe("=" * 70)
    _print_safe("adopted_factors_by_segment.txt -- segment summary")
    _print_safe("=" * 70)
    # Parse segment counts from the text
    df_adopted = adoption_df[adoption_df["decision"] == "\u63a1\u7528"].copy()
    df_no_shogai = df_adopted[
        ~df_adopted["segment"].str.contains("\u969c", na=False)
    ].drop_duplicates(subset=["segment", "factors"])
    seg_summary = df_no_shogai["segment"].value_counts()
    _print_safe(f"合計: {len(df_no_shogai):,}ファクター（障害除外・dedup済）")
    _print_safe("")
    for seg, cnt in seg_summary.items():
        label = SEGMENT_LABELS.get(str(seg), "")
        _print_safe(f"  {str(seg):<35} {label:<15} {cnt:>4}件")

    print()
    print("[DONE] 3 files generated.")


if __name__ == "__main__":
    main()

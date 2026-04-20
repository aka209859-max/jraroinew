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

    print()
    print("[DONE] 2 files generated.")


if __name__ == "__main__":
    main()

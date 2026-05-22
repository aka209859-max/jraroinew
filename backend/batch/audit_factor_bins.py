#!/usr/bin/env python3
"""
audit_factor_bins.py
======================
Phase1〜4 各ファクター（combo）のビンサンプルサイズ監査提出物を生成する。

【出力ファイル】(計12ファイル)
  per phase in [1,2,3,4]:
    reports/production_search/phase{n}_segment_factor_summary.csv
    reports/production_search/phase{n}_factor_bin_audit.csv
    reports/production_search/phase{n}_bin_detail_for_adoption_review.csv

【重要注意】
  - 既存の master_bin_metrics_cleaned.csv は tansho_n/fukusho_n >= 50 フィルタ後のため
    1桁・2桁サンプルのビンが除外済み。本スクリプトは監査用に全ビン（フィルタなし）を
    _bin_metrics() で再計算する。
  - n_horses = _bin_metrics内の len(grp)。これは既にオッズフィルタ
    (単勝1.0〜100.0倍, 複勝1.0〜17.0倍) 適用後のデータに基づく値。
  - combo収集閾値: Phase1 CLB>=75.0, Phase2〜4 pass==True (CLB>=80.0 相当)

Usage:
  py -3.12 -u -m backend.batch.audit_factor_bins
"""

import gc
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from backend.batch.factor_investment_screening import load_and_prepare
from backend.batch.master_combo_pipeline import (
    add_class_column,
    SEGMENTS_DIR,
    RACE_CLASSES,
    DEFAULT_MIN_ROWS,
)
from backend.batch.extract_bin_metrics import _bin_metrics

# --------------------------------------------------------------------------
OUT_DIR = Path("reports/production_search")
P1_CLB  = 75.0
P24_CLB = 80.0
_SURFS  = ("芝", "ダ")
_KBS    = [f"{i:02d}" for i in range(1, 11)]
# --------------------------------------------------------------------------


def _build_one_segment(
    df_full: pd.DataFrame,
    seg_name: str,
    min_rows: int = DEFAULT_MIN_ROWS,
) -> Optional[pd.DataFrame]:
    """セグメント名から単一DataFrameをオンデマンドで構築（メモリ効率化）"""
    if seg_name == "GLOBAL":
        return df_full if len(df_full) >= min_rows else None

    if seg_name.startswith("GLOBAL_"):
        rc = seg_name[7:]
        sub = df_full[df_full["_race_class"] == rc]
        return sub.reset_index(drop=True) if len(sub) >= min_rows else None

    if seg_name.startswith("COURSE_27_"):
        ckey = seg_name[10:]
        sub = df_full[df_full["course_27"] == ckey]
        return sub.reset_index(drop=True) if len(sub) >= min_rows else None

    if seg_name.startswith("SURFACE_2_"):
        rest = seg_name[10:]
        for surf in _SURFS:
            if rest == surf:
                sub = df_full[df_full["surface"] == surf]
                return sub.reset_index(drop=True) if len(sub) >= min_rows else None
            if rest.startswith(f"{surf}_"):
                rc = rest[len(surf) + 1:]
                sub = df_full[
                    (df_full["surface"] == surf) &
                    (df_full["_race_class"] == rc)
                ]
                return sub.reset_index(drop=True) if len(sub) >= min_rows else None

    if seg_name.startswith("KEIBAJO_SURFACE_"):
        rest = seg_name[16:]
        for kb in _KBS:
            for surf in _SURFS:
                prefix = f"{kb}_{surf}"
                if rest == prefix:
                    sub = df_full[
                        (df_full["keibajo_code"] == kb) &
                        (df_full["surface"] == surf)
                    ]
                    return sub.reset_index(drop=True) if len(sub) >= min_rows else None
                if rest.startswith(f"{prefix}_"):
                    rc = rest[len(prefix) + 1:]
                    sub = df_full[
                        (df_full["keibajo_code"] == kb) &
                        (df_full["surface"] == surf) &
                        (df_full["_race_class"] == rc)
                    ]
                    return sub.reset_index(drop=True) if len(sub) >= min_rows else None

    return None


def _collect_combos() -> List[Dict]:
    """Phase1: CLB>=75.0 / Phase2-4: pass==True の全comboを収集"""
    records = []
    for phase in [1, 2, 3, 4]:
        factor_col = "factor" if phase == 1 else "factors"
        threshold  = P1_CLB if phase == 1 else P24_CLB

        for seg_dir in sorted(SEGMENTS_DIR.iterdir()):
            if not seg_dir.is_dir():
                continue
            csv_path = seg_dir / f"combo{phase}_results.csv"
            if not csv_path.exists():
                continue
            try:
                df = pd.read_csv(csv_path)
            except Exception:
                continue
            if df.empty or "clb" not in df.columns:
                continue

            if phase == 1:
                target = df[df["clb"] >= threshold]
            else:
                if "pass" not in df.columns:
                    continue
                target = df[df["pass"] == True]

            if target.empty:
                continue

            seg_name = seg_dir.name
            for _, row in target.iterrows():
                raw     = str(row.get(factor_col, "")).strip()
                factors = [raw] if phase == 1 else [f.strip() for f in raw.split("+") if f.strip()]
                if not factors:
                    continue
                records.append({
                    "phase":     phase,
                    "segment":   seg_name,
                    "factors":   factors,
                    "combo":     "+".join(factors),
                    "combo_clb": round(float(row.get("clb", 0)), 2),
                })

    return records


def _bucket(n: int) -> str:
    if n <= 9:
        return "1-9"
    elif n <= 99:
        return "10-99"
    else:
        return "100+"


def _make_segment_summary(phase_df: pd.DataFrame, phase: int) -> pd.DataFrame:
    """粒度: phase × segment"""
    rows = []
    for seg, sdf in phase_df.groupby("segment"):
        combos = sdf["combo"].unique()
        total_bins = len(sdf)

        one_bins   = (sdf["n_horses"] <= 9).sum()
        two_bins   = ((sdf["n_horses"] >= 10) & (sdf["n_horses"] <= 99)).sum()
        hun_bins   = (sdf["n_horses"] >= 100).sum()

        # ファクターごとの集計
        f_with_1d  = 0
        f_with_2d  = 0
        f_all_100  = 0
        for combo, cdf in sdf.groupby("combo"):
            if (cdf["n_horses"] <= 9).any():
                f_with_1d += 1
            if ((cdf["n_horses"] >= 10) & (cdf["n_horses"] <= 99)).any():
                f_with_2d += 1
            if (cdf["n_horses"] >= 100).all():
                f_all_100 += 1

        rows.append({
            "phase":                    phase,
            "segment":                  seg,
            "factor_count":             len(combos),
            "total_bins":               total_bins,
            "factors_with_1digit_bins": f_with_1d,
            "factors_with_2digit_bins": f_with_2d,
            "factors_all_bins_100plus": f_all_100,
            "one_digit_bin_total":      int(one_bins),
            "two_digit_bin_total":      int(two_bins),
            "hundred_plus_bin_total":   int(hun_bins),
        })

    if not rows:
        return pd.DataFrame(columns=[
            "phase", "segment", "factor_count", "total_bins",
            "factors_with_1digit_bins", "factors_with_2digit_bins",
            "factors_all_bins_100plus", "one_digit_bin_total",
            "two_digit_bin_total", "hundred_plus_bin_total",
        ])
    df = pd.DataFrame(rows).sort_values(
        ["factors_with_1digit_bins", "total_bins"],
        ascending=[False, False]
    ).reset_index(drop=True)
    return df


def _make_factor_audit(phase_df: pd.DataFrame, phase: int) -> pd.DataFrame:
    """粒度: phase × segment × combo"""
    rows = []
    for (seg, combo), cdf in phase_df.groupby(["segment", "combo"]):
        n = cdf["n_horses"]
        total = len(cdf)
        b1    = int((n <= 9).sum())
        b2    = int(((n >= 10) & (n <= 99)).sum())
        b100  = int((n >= 100).sum())

        rows.append({
            "phase":             phase,
            "segment":           seg,
            "combo":             combo,
            "total_bins":        total,
            "bins_1_9":          b1,
            "bins_10_99":        b2,
            "bins_100plus":      b100,
            "min_bin_n":         int(n.min()),
            "max_bin_n":         int(n.max()),
            "mean_bin_n":        round(float(n.mean()), 1),
            "median_bin_n":      round(float(n.median()), 1),
            "ratio_bins_1_9":    round(b1 / total, 4) if total else None,
            "ratio_bins_10_99":  round(b2 / total, 4) if total else None,
            "ratio_bins_100plus":round(b100 / total, 4) if total else None,
            "has_any_1digit_bin":bool(b1 > 0),
            "has_any_2digit_bin":bool(b2 > 0),
        })

    if not rows:
        return pd.DataFrame(columns=[
            "phase", "segment", "combo", "total_bins", "bins_1_9", "bins_10_99",
            "bins_100plus", "min_bin_n", "max_bin_n", "mean_bin_n", "median_bin_n",
            "ratio_bins_1_9", "ratio_bins_10_99", "ratio_bins_100plus",
            "has_any_1digit_bin", "has_any_2digit_bin",
        ])
    df = pd.DataFrame(rows).sort_values(
        ["segment", "ratio_bins_1_9", "ratio_bins_10_99"],
        ascending=[True, False, False]
    ).reset_index(drop=True)
    return df


def _make_bin_detail(phase_df: pd.DataFrame, phase: int) -> pd.DataFrame:
    """粒度: phase × segment × combo × bin_key"""
    df = phase_df.copy()
    df["sample_size_bucket"] = df["n_horses"].apply(_bucket)
    # Y: 既存定義 = tansho_roi_corr * 0.3 + fukusho_roi_corr * 0.7 (bin level)
    df["Y"] = (
        df["tansho_roi_corr"].fillna(0) * 0.3 +
        df["fukusho_roi_corr"].fillna(0) * 0.7
    ).where(df["tansho_roi_corr"].notna() | df["fukusho_roi_corr"].notna(), other=None)
    # rank は bin レベルでは未定義のためNaN
    df["rank"] = None

    cols = [
        "phase", "segment", "combo", "bin_key", "n_horses",
        "sample_size_bucket", "tansho_roi_corr", "fukusho_roi_corr", "Y", "rank",
    ]
    return df[cols].sort_values(
        ["segment", "combo", "n_horses"],
        ascending=[True, True, True]
    ).reset_index(drop=True)


def _run_phase_audit(
    df: pd.DataFrame,
    phase: int,
    combos: List[Dict],
) -> None:
    """1フェーズ分のビン集計と3ファイル出力をメモリ効率よく実行する。"""
    phase_combos = [c for c in combos if c["phase"] == phase]
    if not phase_combos:
        print(f"\n  Phase{phase}: 0 combos → スキップ")
        # 空ファイル生成
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        empty_seg  = pd.DataFrame(columns=["phase","segment","factor_count","total_bins",
                                            "factors_with_1digit_bins","factors_with_2digit_bins",
                                            "factors_all_bins_100plus","one_digit_bin_total",
                                            "two_digit_bin_total","hundred_plus_bin_total"])
        empty_fba  = pd.DataFrame(columns=["phase","segment","combo","total_bins","bins_1_9",
                                            "bins_10_99","bins_100plus","min_bin_n","max_bin_n",
                                            "mean_bin_n","median_bin_n","ratio_bins_1_9",
                                            "ratio_bins_10_99","ratio_bins_100plus",
                                            "has_any_1digit_bin","has_any_2digit_bin"])
        empty_bdt  = pd.DataFrame(columns=["phase","segment","combo","bin_key","n_horses",
                                            "sample_size_bucket","tansho_roi_corr",
                                            "fukusho_roi_corr","Y","rank"])
        empty_seg.to_csv(OUT_DIR / f"phase{phase}_segment_factor_summary.csv", index=False, encoding="utf-8-sig")
        empty_fba.to_csv(OUT_DIR / f"phase{phase}_factor_bin_audit.csv",        index=False, encoding="utf-8-sig")
        empty_bdt.to_csv(OUT_DIR / f"phase{phase}_bin_detail_for_adoption_review.csv", index=False, encoding="utf-8-sig")
        return

    # セグメント別グループ化
    combos_by_seg: Dict[str, List[Dict]] = defaultdict(list)
    for c in phase_combos:
        combos_by_seg[c["segment"]].append(c)
    seg_total = len(combos_by_seg)
    print(f"\n  Phase{phase}: {len(phase_combos)} combos / {seg_total} segments")

    # ビン集計
    all_rows: List[Dict] = []
    n_skip = 0

    for seg_i, (seg_name, seg_combos) in enumerate(sorted(combos_by_seg.items()), 1):
        seg_df = _build_one_segment(df, seg_name)
        if seg_df is None:
            n_skip += len(seg_combos)
            continue

        for c in seg_combos:
            bins = _bin_metrics(
                seg_df, c["factors"],
                c["phase"], c["segment"], c["combo"],
                c["combo_clb"], 0.0,
            )
            all_rows.extend(bins)

        del seg_df
        gc.collect()

        if seg_i % 20 == 0 or seg_i == seg_total:
            print(f"    [{seg_i:3d}/{seg_total}] ビン行数: {len(all_rows):,}  skip={n_skip}")

    print(f"    集計完了: {len(all_rows):,} ビン行")

    if not all_rows:
        p_df = pd.DataFrame()
    else:
        p_df = pd.DataFrame(all_rows)
    del all_rows
    gc.collect()

    n_combos   = p_df.groupby(["segment", "combo"]).ngroups if len(p_df) else 0
    n_segments = p_df["segment"].nunique() if len(p_df) else 0
    n_bins     = len(p_df)
    n_1d  = int((p_df["n_horses"] <= 9).sum()) if len(p_df) else 0
    n_2d  = int(((p_df["n_horses"] >= 10) & (p_df["n_horses"] <= 99)).sum()) if len(p_df) else 0
    n_100 = int((p_df["n_horses"] >= 100).sum()) if len(p_df) else 0
    print(f"    {n_combos} combos / {n_segments} segs / {n_bins:,} bins  "
          f"(1d={n_1d:,} 2d={n_2d:,} 100+={n_100:,})")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    seg_sum = _make_segment_summary(p_df, phase)
    seg_sum.to_csv(OUT_DIR / f"phase{phase}_segment_factor_summary.csv", index=False, encoding="utf-8-sig")
    print(f"    [OK] phase{phase}_segment_factor_summary.csv  ({len(seg_sum)} rows)")

    fba = _make_factor_audit(p_df, phase)
    fba.to_csv(OUT_DIR / f"phase{phase}_factor_bin_audit.csv", index=False, encoding="utf-8-sig")
    print(f"    [OK] phase{phase}_factor_bin_audit.csv  ({len(fba)} rows)")

    bdt = _make_bin_detail(p_df, phase)
    bdt.to_csv(OUT_DIR / f"phase{phase}_bin_detail_for_adoption_review.csv", index=False, encoding="utf-8-sig")
    print(f"    [OK] phase{phase}_bin_detail_for_adoption_review.csv  ({len(bdt)} rows)")

    del p_df, seg_sum, fba, bdt
    gc.collect()


def main() -> None:
    t0 = time.time()
    print("=" * 70)
    print("  audit_factor_bins  Phase1〜4 ビンサンプルサイズ監査")
    print("  n_horses = オッズフィルタ後のビン内全馬数 (tansho/fukusho補正ビン前)")
    print("  ※フェーズ別処理でメモリ効率化")
    print("=" * 70)

    # ---- データロード ----
    print("\n[STEP 1] データロード...")
    df = load_and_prepare(row_limit=0)
    print(f"[INFO] {len(df):,} rows, {len(df.columns)} cols")
    df = add_class_column(df)

    # ---- COMBO 収集 ----
    print("\n[STEP 2] COMBO 収集...")
    combos = _collect_combos()
    by_phase = {p: sum(1 for c in combos if c["phase"] == p) for p in [1, 2, 3, 4]}
    print(f"[INFO] 総COMBO数: {len(combos):,}")
    for p in [1, 2, 3, 4]:
        print(f"  Phase{p}: {by_phase[p]}")

    # ---- Phase別にビン集計 + 出力 (一フェーズずつ処理してメモリを解放) ----
    print("\n[STEP 3] Phase別ビン集計 + CSV生成...")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for phase in [1, 2, 3, 4]:
        _run_phase_audit(df, phase, combos)
        gc.collect()

    elapsed = time.time() - t0
    print(f"\n[完了] elapsed={elapsed:.1f}s ({elapsed/60:.1f}min)")
    print(f"[出力先] {OUT_DIR.resolve()}")


if __name__ == "__main__":
    main()

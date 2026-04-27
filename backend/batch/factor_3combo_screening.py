#!/usr/bin/env python3
"""
factor_3combo_screening.py
===========================
採用済み単独ファクターの全3要素組み合わせ（C(N,3)）をスクリーニング。

【評価式: 均等払戻補正回収率（methodology_corrected_roi.txt 完全準拠）】
  bet_amount[i]   = TARGET_PAYOUT / tansho_odds[i]
  corr_payout[i]  = TARGET_PAYOUT * correction(odds[i], is_fukusho) * is_hit[i]
  corrected_roi   = Sigma(corr_payout * year_weight) / Sigma(bet_amount * year_weight) * 100

【CLB（ビン別補正ROIの95%信頼区間下限）】
  CLB = mean(bin_rois) - 1.96 * std(bin_rois) / sqrt(K)  (K = 有効ビン数)

【抽出基準】
  - 有効ビン数 K >= MIN_VALID_BINS (デフォルト3)
  - 各ビン n >= BIN_MIN_N (デフォルト100)
  - CLB >= CLB_THRESHOLD (デフォルト80.0)

【クラッシュリカバリ】
  CHECKPOINT_INTERVAL (デフォルト5000) 件ごとに中間CSVへ追記保存。
  --resume フラグで途中再開可能（チェックポイントから復旧）。

Usage:
  py -3.12 -m backend.batch.factor_3combo_screening
  py -3.12 -m backend.batch.factor_3combo_screening --resume
  py -3.12 -m backend.batch.factor_3combo_screening --dry-run   # 件数確認のみ

Output:
  reports/screening/3combo_results.csv     (CLB通過分のみ)
  reports/screening/3combo_temp.csv        (チェックポイント / 中間保存)
  reports/screening/3combo_checkpoint.json (再開用)
"""

import argparse
import json
import math
import sys
import time
from itertools import combinations
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# factor_investment_screening から共通処理を再利用
from backend.batch.factor_investment_screening import (
    load_and_prepare,
    build_seg_df_map,
    _vectorize_fukusho_correction,
    _vectorize_tansho_correction,
    prepare_corrected_cols,
    TARGET_PAYOUT,
)

# --------------------------------------------------------------------------
# 定数
# --------------------------------------------------------------------------
BIN_MIN_N          = 100    # 有効ビンの最小サンプル数
MIN_VALID_BINS     = 3      # CLB計算に必要な最小ビン数
CLB_THRESHOLD      = 80.0   # 抽出基準: ビン別補正ROI CLB >= この値
CHECKPOINT_INTERVAL = 5_000  # 何件処理ごとに中間保存するか

DEFAULT_OUTPUT_DIR = Path("reports/screening")
TEMP_CSV      = DEFAULT_OUTPUT_DIR / "3combo_temp.csv"
RESULT_CSV    = DEFAULT_OUTPUT_DIR / "3combo_results.csv"
CHECKPOINT_F  = DEFAULT_OUTPUT_DIR / "3combo_checkpoint.json"
ADOPTION_CSV  = DEFAULT_OUTPUT_DIR / "factor_adoption_result.csv"


# --------------------------------------------------------------------------
# コア評価: 1つの3-COMBOに対して補正ROI CLBを計算
# --------------------------------------------------------------------------
def _get_col_1d(seg_df: pd.DataFrame, col: str) -> np.ndarray:
    """
    DataFrame から列を確実に1D numpy配列で取得する。
    重複列名（JOAマージで発生する可能性）がある場合は先頭列を使用。
    """
    series = seg_df[col]
    if isinstance(series, pd.DataFrame):
        # 重複列名がある場合: iloc で先頭列を1列だけ取得
        series = series.iloc[:, 0]
    return series.to_numpy()


def evaluate_3combo(
    seg_df: pd.DataFrame,
    f1: str, f2: str, f3: str,
) -> Optional[Dict]:
    """
    (f1, f2, f3) 3要素組み合わせを評価し、ビン別補正ROI CLBを返す。

    【実装方針】pandas を最小限に使い、numpy 直接演算で全問題を回避。
      - 重複インデックス問題（SURFACE_2_* / GLOBAL）: .to_numpy() でインデックスを無視
      - 重複列名問題（JOAマージ由来）: _get_col_1d() で先頭列を強制選択
      - groupby高速化: np.unique + boolean mask（pandas groupby 不使用）

    Returns: result dict or None (if insufficient data)
    """
    # 全列の存在確認
    for col in (f1, f2, f3):
        if col not in seg_df.columns:
            return None

    # 有効行（3列すべて非NULL）— pandas で notna のみ使用
    valid_mask = seg_df[f1].notna() & seg_df[f2].notna() & seg_df[f3].notna()
    if isinstance(valid_mask, pd.DataFrame):
        valid_mask = valid_mask.iloc[:, 0]
    n_valid = int(valid_mask.sum())
    if n_valid < BIN_MIN_N * MIN_VALID_BINS:
        return None

    mask_arr = valid_mask.to_numpy(dtype=bool)

    # 全列を numpy 1D 配列に変換（重複列名・重複インデックス両対応）
    f1_arr  = _get_col_1d(seg_df, f1)[mask_arr].astype(str)
    f2_arr  = _get_col_1d(seg_df, f2)[mask_arr].astype(str)
    f3_arr  = _get_col_1d(seg_df, f3)[mask_arr].astype(str)
    bet_arr = _get_col_1d(seg_df, "_fukusho_bet_amount")[mask_arr].astype(float)
    pay_arr = _get_col_1d(seg_df, "_corrected_pay")[mask_arr].astype(float)
    w_arr   = _get_col_1d(seg_df, "_year_weight")[mask_arr].astype(float)

    # グループキー（numpy文字列結合: pandas align 問題を完全回避）
    key_arr = f1_arr + "\x01" + f2_arr + "\x01" + f3_arr

    # numpy unique でグループ割り当て（pandas groupby 不使用）
    _, inverse = np.unique(key_arr, return_inverse=True)

    # ビン別補正ROI
    bin_rois: List[float] = []
    total_n = 0

    for gi in range(int(inverse.max()) + 1):
        grp_mask = (inverse == gi)
        n = int(grp_mask.sum())
        if n < BIN_MIN_N:
            continue
        w    = w_arr[grp_mask]
        wbet = float((bet_arr[grp_mask] * w).sum())
        wpay = float((pay_arr[grp_mask] * w).sum())
        if wbet <= 0:
            continue
        bin_rois.append(wpay / wbet * 100.0)
        total_n += n

    K = len(bin_rois)
    if K < MIN_VALID_BINS:
        return None

    arr  = np.array(bin_rois, dtype=float)
    mean = float(arr.mean())
    std  = float(arr.std(ddof=1)) if K > 1 else 0.0
    clb  = mean - 1.96 * std / math.sqrt(K)

    return {
        "n_valid_bins":       K,
        "n_valid_bets":       total_n,
        "mean_corrected_roi": round(mean, 2),
        "std_bin_roi":        round(std, 2),
        "clb":                round(clb, 2),
        "pass":               clb >= CLB_THRESHOLD,
    }


# --------------------------------------------------------------------------
# チェックポイント I/O
# --------------------------------------------------------------------------
def load_checkpoint() -> Dict:
    if CHECKPOINT_F.exists():
        with open(CHECKPOINT_F, encoding="utf-8") as f:
            return json.load(f)
    return {"completed_segments": [], "total_processed": 0, "total_passed": 0}


def save_checkpoint(cp: Dict) -> None:
    CHECKPOINT_F.parent.mkdir(parents=True, exist_ok=True)
    with open(CHECKPOINT_F, "w", encoding="utf-8") as f:
        json.dump(cp, f, ensure_ascii=False, indent=2)


def append_to_temp(rows: List[Dict]) -> None:
    if not rows:
        return
    df = pd.DataFrame(rows)
    write_header = not TEMP_CSV.exists()
    df.to_csv(TEMP_CSV, mode="a", header=write_header, index=False, encoding="utf-8-sig")


# --------------------------------------------------------------------------
# 採用済み単独ファクターの取得
# --------------------------------------------------------------------------
def load_adopted_singles() -> Dict[str, List[str]]:
    """
    factor_adoption_result.csv から decision='採用' かつ
    factors列に '+' を含まない（単独ファクター）を段別に返す。

    Returns: {segment: [factor_name, ...]}
    """
    df = pd.read_csv(ADOPTION_CSV)
    singles = df[
        (df["decision"] == "採用") &
        (~df["factors"].astype(str).str.contains(r"\+", na=False))
    ].copy()

    seg_map: Dict[str, List[str]] = {}
    dup_warn = []
    for seg, grp in singles.groupby("segment"):
        flist_raw = grp["factors"].tolist()
        # 重複ファクター名を除去（採用CSVに同名ファクターが複数ある場合の防衛的処理）
        flist_dedup = sorted(set(flist_raw))
        if len(flist_dedup) < len(flist_raw):
            dups = [f for f in flist_raw if flist_raw.count(f) > 1]
            dup_warn.append(f"  {seg}: 重複除去 {set(dups)}")
        seg_map[str(seg)] = flist_dedup

    if dup_warn:
        print(f"[WARN] 重複ファクター名を除去:")
        for w in dup_warn:
            print(w)
    print(f"[INFO] 採用単独ファクター: {len(singles)}件 / {len(seg_map)}セグメント（重複除去後）")
    return seg_map


# --------------------------------------------------------------------------
# メインスクリーニングループ
# --------------------------------------------------------------------------
def run_3combo_screening(
    df: pd.DataFrame,
    resume: bool = False,
    dry_run: bool = False,
) -> None:
    """全セグメントの3-COMBO評価を実行する。"""

    singles    = load_adopted_singles()
    if dry_run:
        from math import comb as math_comb
        total_combos = sum(
            math_comb(len(flist), 3)
            for flist in singles.values()
            if len(flist) >= 3
        )
        print(f"\n[INFO] 総3-COMBO件数: {total_combos:,}")
        for seg, flist in sorted(singles.items(), key=lambda x: -len(x[1])):
            n = len(flist)
            if n >= 3:
                print(f"  {seg}: {n}単独 -> C({n},3)={math_comb(n,3):,}件")
        return

    seg_map    = build_seg_df_map(df)

    # 全件数を事前カウント
    from math import comb as math_comb
    total_combos = sum(
        math_comb(len(flist), 3)
        for flist in singles.values()
        if len(flist) >= 3
    )
    print(f"[INFO] 総3-COMBO件数: {total_combos:,}")

    # チェックポイントロード
    cp = load_checkpoint() if resume else {
        "completed_segments": [], "total_processed": 0, "total_passed": 0,
    }
    completed_segs = set(cp["completed_segments"])
    total_processed = cp["total_processed"]
    total_passed    = cp["total_passed"]

    if resume and completed_segs:
        print(f"[RESUME] 完了済みセグメント: {len(completed_segs)}件 "
              f"/ 処理済み: {total_processed:,}件 / 通過済み: {total_passed:,}件")

    # 中間保存バッファ
    buffer: List[Dict] = []

    t_start = time.time()

    # セグメント順でループ（大きい順に処理）
    ordered_segs = sorted(
        [(seg, flist) for seg, flist in singles.items() if len(flist) >= 3],
        key=lambda x: -math_comb(len(x[1]), 3)
    )

    for seg_idx, (seg, flist) in enumerate(ordered_segs):
        if seg in completed_segs:
            print(f"[SKIP] {seg} (already completed)")
            continue

        seg_df = seg_map.get(seg)
        if seg_df is None or len(seg_df) < BIN_MIN_N:
            print(f"[SKIP] {seg} (no segment data)")
            completed_segs.add(seg)
            cp["completed_segments"].append(seg)
            save_checkpoint(cp)
            continue

        n_singles  = len(flist)
        n_combos   = math_comb(n_singles, 3)
        seg_passed = 0
        seg_proc   = 0

        print(f"\n[SEG {seg_idx+1}/{len(ordered_segs)}] {seg}: "
              f"{n_singles}単独 -> {n_combos:,}件評価開始", flush=True)
        seg_t = time.time()

        for f1, f2, f3 in combinations(flist, 3):
            result = evaluate_3combo(seg_df, f1, f2, f3)
            seg_proc    += 1
            total_processed += 1

            row = {
                "segment":            seg,
                "factors":            f"{f1}+{f2}+{f3}",
                "n_valid_bins":       result["n_valid_bins"]       if result else None,
                "n_valid_bets":       result["n_valid_bets"]       if result else None,
                "mean_corrected_roi": result["mean_corrected_roi"] if result else None,
                "std_bin_roi":        result["std_bin_roi"]        if result else None,
                "clb":                result["clb"]                if result else None,
                "pass":               result["pass"]               if result else False,
                "skip":               result is None,
            }

            if result and result["pass"]:
                seg_passed    += 1
                total_passed  += 1

            buffer.append(row)

            # チェックポイント保存
            if len(buffer) >= CHECKPOINT_INTERVAL:
                append_to_temp(buffer)
                buffer.clear()
                cp["total_processed"] = total_processed
                cp["total_passed"]    = total_passed
                save_checkpoint(cp)

                elapsed = time.time() - t_start
                rate    = total_processed / elapsed if elapsed > 0 else 0
                eta_sec = (total_combos - total_processed) / rate if rate > 0 else 0
                print(
                    f"  [CKPT] processed={total_processed:,}/{total_combos:,}"
                    f" passed={total_passed:,}"
                    f" speed={rate:.1f}/s"
                    f" ETA={eta_sec/3600:.1f}h",
                    flush=True,
                )

            # セグメント内の進捗ログ（25%刻み）
            for pct in (25, 50, 75):
                milestone = n_combos * pct // 100
                if seg_proc == milestone:
                    seg_elapsed = time.time() - seg_t
                    print(
                        f"  {pct}% ({seg_proc:,}/{n_combos:,})"
                        f" seg_passed={seg_passed}"
                        f" {seg_elapsed/60:.1f}min",
                        flush=True,
                    )

        # セグメント完了 → バッファを強制フラッシュ
        if buffer:
            append_to_temp(buffer)
            buffer.clear()

        seg_time = time.time() - seg_t
        print(f"  [DONE] {seg}: {seg_proc:,}件 / 通過={seg_passed}件 "
              f"({seg_time/60:.1f}min)", flush=True)

        completed_segs.add(seg)
        cp["completed_segments"].append(seg)
        cp["total_processed"] = total_processed
        cp["total_passed"]    = total_passed
        save_checkpoint(cp)

    # 最終保存（残バッファ）
    if buffer:
        append_to_temp(buffer)

    # CLB通過分のみ最終CSVへ
    if TEMP_CSV.exists():
        all_df = pd.read_csv(TEMP_CSV)
        passed_df = all_df[all_df["pass"] == True].sort_values(
            "clb", ascending=False
        ).reset_index(drop=True)
        passed_df.to_csv(RESULT_CSV, index=False, encoding="utf-8-sig")
        print(f"\n[RESULT] CLB通過: {len(passed_df):,}件 -> {RESULT_CSV}")

    total_elapsed = time.time() - t_start
    print(f"\n[DONE] 総処理: {total_processed:,}件 / 通過: {total_passed:,}件 "
          f"/ 総時間: {total_elapsed/3600:.2f}h")


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="3-COMBO補正回収率スクリーニング")
    parser.add_argument("--resume",  action="store_true", help="チェックポイントから再開")
    parser.add_argument("--dry-run", action="store_true", help="件数確認のみ（評価なし）")
    args = parser.parse_args()

    if args.resume and not CHECKPOINT_F.exists():
        print("[WARN] チェックポイントファイルが見つかりません。最初から開始します。")
        args.resume = False

    # データロード・前処理（factor_investment_screening と同一）
    if not args.dry_run:
        print("[INFO] データロード開始...")
        df = load_and_prepare()
        print(f"[INFO] ロード完了: {len(df):,}行 / {len(df.columns)}列")
    else:
        df = None

    run_3combo_screening(df, resume=args.resume, dry_run=args.dry_run)


if __name__ == "__main__":
    main()

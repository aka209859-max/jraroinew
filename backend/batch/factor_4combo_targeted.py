#!/usr/bin/env python3
"""
factor_4combo_targeted.py
==========================
精鋭3-COMBO（364件）をベースに、採用単独ファクターを1つ追加した
4-COMBO ディープサーチを実行する。

【探索戦略】
  3combo_filtered.csv の精鋭3-COMBO（base）×
  対応セグメントの採用単独ファクター（追加候補）
  → 重複なし・重複ファクター排除の 4-COMBO を全探索

【評価式: 均等払戻補正回収率（methodology_corrected_roi.txt 完全準拠）】
  3combo_screening と同一。numpy高速化を維持。

  重要最適化: セグメント単位で全因子を numpy 配列にキャッシュし、
  内側ループでの pandas アクセスをゼロにすることで高速化。

【抽出基準】
  - 有効ビン数 K >= MIN_VALID_BINS (=3)
  - 各ビン n >= BIN_MIN_N (=100)
  - CLB >= CLB_THRESHOLD (=80.0)

【クラッシュリカバリ】
  CHECKPOINT_INTERVAL (=2,000) 件ごとに中間CSVへ追記保存。
  --resume フラグで途中再開可能。

Usage:
  py -3.12 -m backend.batch.factor_4combo_targeted
  py -3.12 -m backend.batch.factor_4combo_targeted --resume
  py -3.12 -m backend.batch.factor_4combo_targeted --dry-run
  py -3.12 -m backend.batch.factor_4combo_targeted --limit 100  # テスト

Output:
  reports/screening/4combo_results.csv
  reports/screening/4combo_temp.csv
  reports/screening/4combo_checkpoint.json
"""

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# 共通インフラ再利用
from backend.batch.factor_investment_screening import (
    load_and_prepare,
    build_seg_df_map,
    prepare_corrected_cols,
    TARGET_PAYOUT,
)
from backend.batch.factor_3combo_screening import (
    _get_col_1d,
    load_adopted_singles,
)

# --------------------------------------------------------------------------
# 定数
# --------------------------------------------------------------------------
BIN_MIN_N           = 100     # 有効ビンの最小サンプル数
MIN_VALID_BINS      = 3       # CLB計算に必要な最小ビン数
CLB_THRESHOLD       = 80.0    # 抽出基準: CLB >= この値
CHECKPOINT_INTERVAL = 2_000   # 何件処理ごとに中間保存するか

OUTPUT_DIR   = Path("reports/screening")
TEMP_CSV     = OUTPUT_DIR / "4combo_temp.csv"
RESULT_CSV   = OUTPUT_DIR / "4combo_results.csv"
CHECKPOINT_F = OUTPUT_DIR / "4combo_checkpoint.json"
FILTERED_CSV = OUTPUT_DIR / "3combo_filtered.csv"
ADOPTION_CSV = OUTPUT_DIR / "factor_adoption_result.csv"


# --------------------------------------------------------------------------
# セグメントキャッシュ（pandas アクセスを内側ループから排除）
# --------------------------------------------------------------------------
class SegmentCache:
    """
    1セグメント分の全ファクター numpy 配列キャッシュ。
    内側ループから pandas を完全排除して高速化。

    属性:
      n_rows    : 有効行数（not-na マスク適用前）
      factor_arr: {factor_name: np.ndarray(str, shape=(n_rows,))} 全ファクター
      bet_arr   : np.ndarray(float) — _fukusho_bet_amount
      pay_arr   : np.ndarray(float) — _corrected_pay
      w_arr     : np.ndarray(float) — _year_weight
      notna_cache: {factor_name: np.ndarray(bool)} — .notna() 結果キャッシュ
    """

    __slots__ = ("n_rows", "factor_arr", "bet_arr", "pay_arr", "w_arr", "notna_cache")

    def __init__(
        self,
        seg_df: pd.DataFrame,
        all_factors: List[str],
    ) -> None:
        self.n_rows = len(seg_df)

        # 補正列を float 配列に展開
        self.bet_arr = _get_col_1d(seg_df, "_fukusho_bet_amount").astype(float)
        self.pay_arr = _get_col_1d(seg_df, "_corrected_pay").astype(float)
        self.w_arr   = _get_col_1d(seg_df, "_year_weight").astype(float)

        # 各ファクターを str 配列 + bool 配列 に展開
        self.factor_arr:  Dict[str, np.ndarray] = {}
        self.notna_cache: Dict[str, np.ndarray] = {}
        for f in all_factors:
            if f not in seg_df.columns:
                continue
            raw = _get_col_1d(seg_df, f)
            notna = ~pd.isnull(raw)          # bool array
            self.notna_cache[f] = notna
            self.factor_arr[f]  = raw.astype(str)

    def has_factor(self, f: str) -> bool:
        return f in self.factor_arr

    def evaluate_combo(
        self,
        factors: List[str],
        bin_min_n: int = BIN_MIN_N,
        min_bins: int  = MIN_VALID_BINS,
    ) -> Optional[Dict]:
        """
        factors (長さ任意) の組み合わせを評価。
        3-COMBO / 4-COMBO 両方に対応。
        """
        # 全ファクター存在確認
        for f in factors:
            if not self.has_factor(f):
                return None

        # valid mask（全ファクター非NULL の行）— numpy 演算のみ
        mask = self.notna_cache[factors[0]].copy()
        for f in factors[1:]:
            mask &= self.notna_cache[f]

        n_valid = int(mask.sum())
        if n_valid < bin_min_n * min_bins:
            return None

        # マスク適用後の配列を抽出
        f_arrs  = [self.factor_arr[f][mask] for f in factors]
        bet_arr = self.bet_arr[mask]
        pay_arr = self.pay_arr[mask]
        w_arr   = self.w_arr[mask]

        # グループキー（区切り文字 \x01 でファクター値を結合）
        key_arr = f_arrs[0].copy()
        for fa in f_arrs[1:]:
            key_arr = np.char.add(np.char.add(key_arr, "\x01"), fa)

        # numpy unique でグループ割り当て
        _, inverse = np.unique(key_arr, return_inverse=True)

        # np.bincount で各グループのサンプル数を一括集計し、
        # bin_min_n 以上のグループだけを対象にループ（大規模セグメント高速化）
        counts = np.bincount(inverse)
        valid_gis = np.where(counts >= bin_min_n)[0]

        bin_rois: List[float] = []
        total_n = 0
        for gi in valid_gis:
            grp = (inverse == gi)
            w    = w_arr[grp]
            wbet = float((bet_arr[grp] * w).sum())
            wpay = float((pay_arr[grp] * w).sum())
            if wbet <= 0:
                continue
            bin_rois.append(wpay / wbet * 100.0)
            total_n += int(counts[gi])

        K = len(bin_rois)
        if K < min_bins:
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
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(CHECKPOINT_F, "w", encoding="utf-8") as f:
        json.dump(cp, f, ensure_ascii=False, indent=2)


def append_to_temp(rows: List[Dict]) -> None:
    if not rows:
        return
    df = pd.DataFrame(rows)
    write_header = not TEMP_CSV.exists()
    df.to_csv(TEMP_CSV, mode="a", header=write_header, index=False, encoding="utf-8-sig")


# --------------------------------------------------------------------------
# 4-COMBO 生成ユーティリティ
# --------------------------------------------------------------------------
def load_base_combos() -> pd.DataFrame:
    """3combo_filtered.csv から精鋭3-COMBOを読み込む。"""
    if not FILTERED_CSV.exists():
        print(f"[ERROR] {FILTERED_CSV} が見つかりません。")
        sys.exit(1)
    df = pd.read_csv(FILTERED_CSV)
    print(f"[INFO] 精鋭3-COMBO: {len(df)}件 / {df['segment'].nunique()}セグメント")
    return df


def build_4combo_tasks(
    base_combos: pd.DataFrame,
    adopted_singles: Dict[str, List[str]],
) -> List[Tuple[str, List[str], str]]:
    """
    (segment, 4-factors-list, base_factors_str) のタスクリストを生成。
    重複ファクター排除・ソート済みの4-factor listを返す。
    """
    tasks: List[Tuple[str, List[str], str]] = []
    seen: set = set()

    for _, row in base_combos.iterrows():
        seg          = str(row["segment"])
        base_factors = str(row["factors"]).split("+")
        base_set     = set(base_factors)
        candidates   = adopted_singles.get(seg, [])

        for add_f in candidates:
            if add_f in base_set:
                continue  # 既に含まれているファクターは追加しない

            # 4因子を順序固定（アルファベット昇順で重複検出）
            four = sorted(base_factors + [add_f])
            key  = seg + "|" + "+".join(four)
            if key in seen:
                continue  # 異なるベース3-COMBOから同じ4-COMBOが生まれた場合は除外
            seen.add(key)
            tasks.append((seg, four, row["factors"]))

    return tasks


# --------------------------------------------------------------------------
# メインスクリーニングループ
# --------------------------------------------------------------------------
def run_4combo_screening(
    df: pd.DataFrame,
    resume: bool = False,
    dry_run: bool = False,
    limit: int = 0,
) -> None:
    """精鋭3-COMBOをベースにした4-COMBO全探索。"""

    # ── 採用単独ファクター & 精鋭3-COMBO 読み込み ──────────────────────────
    adopted_singles = load_adopted_singles()
    base_combos     = load_base_combos()

    # ── タスクリスト生成 ──────────────────────────────────────────────────
    tasks = build_4combo_tasks(base_combos, adopted_singles)
    print(f"[INFO] 総4-COMBOタスク数: {len(tasks):,}件")

    if dry_run:
        # セグメント別内訳
        from collections import Counter
        seg_cnt = Counter(seg for seg, _, _ in tasks)
        for seg, cnt in sorted(seg_cnt.items(), key=lambda x: -x[1])[:15]:
            print(f"  {seg}: {cnt:,}件")
        return

    if limit > 0:
        tasks = tasks[:limit]
        print(f"[INFO] --limit {limit}: 先頭{limit}件のみ処理")

    # ── セグメントマップ構築 ───────────────────────────────────────────────
    seg_map = build_seg_df_map(df)

    # ── チェックポイントロード ──────────────────────────────────────────────
    if resume:
        cp = load_checkpoint()
        completed_keys = set(cp.get("completed_keys", []))
        total_processed = cp["total_processed"]
        total_passed    = cp["total_passed"]
        print(
            f"[RESUME] 完了済み: {len(completed_keys):,}件 / "
            f"処理済み: {total_processed:,}件 / 通過済み: {total_passed:,}件"
        )
    else:
        completed_keys  = set()
        total_processed = 0
        total_passed    = 0

    # ── セグメント別キャッシュ構築 ─────────────────────────────────────────
    # 使用するセグメントだけを対象に SegmentCache を構築
    used_segs = set(seg for seg, _, _ in tasks)
    seg_cache: Dict[str, Optional[SegmentCache]] = {}

    print(f"[INFO] セグメントキャッシュ構築中 ({len(used_segs)}セグメント)...")
    t_cache = time.time()
    for seg in used_segs:
        seg_df = seg_map.get(seg)
        if seg_df is None or len(seg_df) < BIN_MIN_N:
            seg_cache[seg] = None
            continue
        # そのセグメントで使うファクター一覧を収集
        seg_factors = list({f for s, flist, _ in tasks if s == seg for f in flist})
        seg_cache[seg] = SegmentCache(seg_df, seg_factors)
    print(f"[INFO] キャッシュ構築完了 ({time.time()-t_cache:.1f}s)")

    # ── バッファ & 進捗管理 ─────────────────────────────────────────────────
    buffer: List[Dict] = []
    t_start = time.time()
    speed_samples: List[float] = []   # 直近のspeedサンプル

    n_total   = len(tasks)
    n_done    = 0     # 今セッションの処理数
    n_skipped = 0     # resume スキップ数
    n_passed  = 0     # 今セッションの通過数

    for task_idx, (seg, four_factors, base_str) in enumerate(tasks):
        task_key = seg + "|" + "+".join(four_factors)

        # resume: 既完了タスクをスキップ
        if task_key in completed_keys:
            n_skipped += 1
            continue

        # ── 評価 ──────────────────────────────────────────────────────────
        cache = seg_cache.get(seg)
        t_eval = time.time()

        if cache is None:
            result_row = {
                "segment":            seg,
                "factors":            "+".join(four_factors),
                "base_3combo":        base_str,
                "n_valid_bins":       0,
                "n_valid_bets":       0,
                "mean_corrected_roi": None,
                "std_bin_roi":        None,
                "clb":                None,
                "pass":               False,
                "skip":               True,
            }
        else:
            result = cache.evaluate_combo(four_factors)
            if result is None:
                result_row = {
                    "segment":            seg,
                    "factors":            "+".join(four_factors),
                    "base_3combo":        base_str,
                    "n_valid_bins":       0,
                    "n_valid_bets":       0,
                    "mean_corrected_roi": None,
                    "std_bin_roi":        None,
                    "clb":                None,
                    "pass":               False,
                    "skip":               True,
                }
            else:
                result_row = {
                    "segment":            seg,
                    "factors":            "+".join(four_factors),
                    "base_3combo":        base_str,
                    **result,
                    "skip":               False,
                }
                if result["pass"]:
                    n_passed += 1
                    total_passed += 1

        # ── バッファ蓄積 ───────────────────────────────────────────────────
        buffer.append(result_row)
        n_done += 1
        total_processed += 1
        completed_keys.add(task_key)

        # speed tracking
        elapsed_eval = time.time() - t_eval
        speed_samples.append(elapsed_eval)
        if len(speed_samples) > 200:
            speed_samples.pop(0)

        # ── チェックポイント保存 ────────────────────────────────────────────
        if n_done % CHECKPOINT_INTERVAL == 0 or n_done == 1:
            append_to_temp(buffer)
            buffer = []
            cp_data = {
                "completed_keys":  list(completed_keys),
                "total_processed": total_processed,
                "total_passed":    total_passed,
            }
            save_checkpoint(cp_data)

            elapsed = time.time() - t_start
            avg_speed = len(speed_samples) / max(sum(speed_samples), 1e-9)
            remaining = n_total - (task_idx + 1)
            eta_sec   = remaining / avg_speed if avg_speed > 0 else 0

            print(
                f"[{task_idx+1:5d}/{n_total}] "
                f"通過:{total_passed:,} | "
                f"{avg_speed:.1f}件/s | "
                f"ETA:{eta_sec/60:.1f}min"
            )

        # ── 100件到達時に速度レポート ──────────────────────────────────────
        elif n_done == 100:
            elapsed = time.time() - t_start
            avg_speed = n_done / elapsed if elapsed > 0 else 0
            eta_sec   = (n_total - (task_idx + 1)) / avg_speed if avg_speed > 0 else 0
            print(
                f"\n[SPEED CHECK @ 100件]"
                f"  処理速度: {avg_speed:.2f}件/s"
                f"  推定残時間: {eta_sec/60:.1f}分"
                f"  推定総時間: {(elapsed + eta_sec)/60:.1f}分\n"
            )

    # ── 残バッファをフラッシュ ──────────────────────────────────────────────
    if buffer:
        append_to_temp(buffer)
        cp_data = {
            "completed_keys":  list(completed_keys),
            "total_processed": total_processed,
            "total_passed":    total_passed,
        }
        save_checkpoint(cp_data)

    # ── 最終結果を整形して出力 ─────────────────────────────────────────────
    if TEMP_CSV.exists():
        full_df = pd.read_csv(TEMP_CSV)
        passed_df = full_df[full_df["pass"] == True].copy()
        # CLB降順にソート
        if "clb" in passed_df.columns:
            passed_df = passed_df.sort_values("clb", ascending=False)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        passed_df.to_csv(RESULT_CSV, index=False, encoding="utf-8-sig")
        print(f"\n[SAVE] 4combo_results.csv: {len(passed_df):,}件")
    else:
        print("[WARN] 4combo_temp.csv が見つかりません")

    # ── サマリー ──────────────────────────────────────────────────────────
    elapsed_total = time.time() - t_start
    print(f"\n{'='*60}")
    print(f"4-COMBOターゲットサーチ完了 ({elapsed_total/60:.1f}分)")
    print(f"{'='*60}")
    print(f"  総タスク数: {n_total:,}件")
    print(f"  処理済み:   {total_processed:,}件")
    print(f"  スキップ:   {n_skipped:,}件（resume）")
    print(f"  CLB>={CLB_THRESHOLD}通過: {total_passed:,}件")
    print(f"{'='*60}")

    # Top 10
    if RESULT_CSV.exists():
        result_df = pd.read_csv(RESULT_CSV)
        if len(result_df) > 0:
            print(f"\n【Top 10 精鋭4-COMBO (CLB降順)】")
            top10 = result_df.nlargest(10, "clb")
            for _, r in top10.iterrows():
                print(
                    f"  [{r['segment']}] {r['factors']}\n"
                    f"    CLB={r['clb']:.2f}%  ROI={r['mean_corrected_roi']:.2f}%  "
                    f"K={int(r['n_valid_bins'])}  N={int(r['n_valid_bets']):,}"
                )


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="4-COMBOターゲットサーチ")
    parser.add_argument("--resume",   action="store_true", help="チェックポイントから再開")
    parser.add_argument("--dry-run",  action="store_true", help="件数確認のみ")
    parser.add_argument("--limit",    type=int, default=0, help="テスト用: 先頭N件のみ")
    args = parser.parse_args()

    if args.dry_run:
        adopted_singles = load_adopted_singles()
        base_combos     = load_base_combos()
        tasks = build_4combo_tasks(base_combos, adopted_singles)
        print(f"[DRY-RUN] 総4-COMBOタスク数: {len(tasks):,}件")
        from collections import Counter
        seg_cnt = Counter(seg for seg, _, _ in tasks)
        for seg, cnt in sorted(seg_cnt.items(), key=lambda x: -x[1])[:15]:
            print(f"  {seg}: {cnt:,}件")
        return

    if not args.resume:
        # 前回の中間ファイルをクリア（新規実行時）
        for f in [TEMP_CSV, CHECKPOINT_F]:
            if f.exists():
                f.unlink()
                print(f"[INFO] 前回の中間ファイルを削除: {f.name}")

    print("[INFO] レースデータ読み込み中...")
    t0 = time.time()
    df = load_and_prepare()
    df = prepare_corrected_cols(df)
    print(f"[INFO] データ準備完了 ({time.time()-t0:.1f}s)")

    run_4combo_screening(df, resume=args.resume, dry_run=False, limit=args.limit)


if __name__ == "__main__":
    main()

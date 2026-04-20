#!/usr/bin/env python3
"""
bin_scoring.py
==============
**式1（相対評価）** — DBから直接計算する8固定パターン:
  ① COURSE_27 × 順位系ファクター（ten/ichi/agari_shisu_juni, kyakushitsu）— 4パターン
  ② COURSE_27 × pace_yoso × kyakushitsu
  ③ SURFACE_2 × gekiso_juni
  ④ KEIBAJO_SURFACE × kishumei
  ⑤ KEIBAJO_SURFACE × chokyoshimei

  HitRaw = 0.65 * win_rate + 0.35 * place_rate
  RetRaw = 0.35 * win_roi  + 0.65 * place_roi
  ZH, ZR = Z-score per gid group (population std)
  Shr    = SQRT(n / (n + 400))
  score  = ROUND(12 * TANH(0.55*ZH + 0.45*ZR) * Shr, 1)   ±12.0

**式2（絶対評価・デフォルト）** — factor_adoption_detail/ CSVから読み込む:
  W  = win_count + place_count
  X  = MIN(1, SQRT(W / 500))
  Y  = win_roi * 0.3 + place_roi * 0.7
  AA = (Y - 80) * X
  score = ROUND(10 * TANH(AA / 25), 1)   ±10.0

Usage:
  py -3.12 -m backend.batch.bin_scoring [--adoption-csv ...] [--detail-dir ...]
                                         [--output-dir ...]
"""

import argparse
import math
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import psycopg2

# ── Paths / DB ────────────────────────────────────────────────────────────────
_REPO = Path(__file__).parent.parent.parent
DEFAULT_ADOPTION_CSV = _REPO / "reports" / "screening" / "factor_adoption_result.csv"
DEFAULT_DETAIL_DIR   = _REPO / "reports" / "screening" / "factor_adoption_detail"
DEFAULT_OUTPUT_DIR   = _REPO / "reports" / "scoring"

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 5432,
    "database": "pckeiba",
    "user": "postgres",
    "password": "postgres123",
}

MIN_BIN_N = 30  # bins with n < 30 are discarded


# ── Formula 1 fixed definitions (8 patterns) ──────────────────────────────────
#   gid_cols  : columns used to identify the group (for ZH/ZR computation)
#   factor_col: single factor column → bin value
#   factor_cols: multiple factor columns → bin value joined with "|"
FORMULA1_DEFINITIONS: List[Dict] = [
    # ① 競馬場×芝ダ×距離×順位系ファクター（4パターン）
    {
        "name": "COURSE_27\u00d7ten_shisu_juni",
        "gid_cols": ["keibajo_code", "surface", "kyori_kubun"],
        "factor_col": "ten_shisu_juni",
    },
    {
        "name": "COURSE_27\u00d7ichi_shisu_juni",
        "gid_cols": ["keibajo_code", "surface", "kyori_kubun"],
        "factor_col": "ichi_shisu_juni",
    },
    {
        "name": "COURSE_27\u00d7agari_shisu_juni",
        "gid_cols": ["keibajo_code", "surface", "kyori_kubun"],
        "factor_col": "agari_shisu_juni",
    },
    {
        "name": "COURSE_27\u00d7kyakushitsu",
        "gid_cols": ["keibajo_code", "surface", "kyori_kubun"],
        "factor_col": "kyakushitsu",
    },
    # ② 競馬場×芝ダ×距離×ペース予想×予想脚質
    {
        "name": "COURSE_27\u00d7pace_yoso\u00d7kyakushitsu",
        "gid_cols": ["keibajo_code", "surface", "kyori_kubun"],
        "factor_cols": ["pace_yoso", "kyakushitsu"],
    },
    # ③ 芝ダ×激走指数順位
    {
        "name": "SURFACE_2\u00d7gekiso_juni",
        "gid_cols": ["surface"],
        "factor_col": "gekiso_juni",
    },
    # ④ 競馬場×芝ダ×騎手
    {
        "name": "KEIBAJO_SURFACE\u00d7kishumei",
        "gid_cols": ["keibajo_code", "surface"],
        "factor_col": "kishumei",
    },
    # ⑤ 競馬場×芝ダ×調教師
    {
        "name": "KEIBAJO_SURFACE\u00d7chokyoshimei",
        "gid_cols": ["keibajo_code", "surface"],
        "factor_col": "chokyoshimei",
    },
]

# ── Base SQL for Formula 1 ────────────────────────────────────────────────────
_F1_BASE_QUERY = """
SELECT
    k.keibajo_code,
    NULLIF(TRIM(r.track_code), '')                       AS track_code,
    CAST(NULLIF(TRIM(r.kyori), '') AS INTEGER)           AS kyori,
    GREATEST(1, LEAST(10,
        CAST(SUBSTRING(v.kaisai_nen, 3, 2) AS INTEGER) - 15
    ))                                                   AS year_weight,
    -- Factor columns for Formula 1 patterns
    NULLIF(TRIM(CAST(k.ten_shisu_juni  AS TEXT)), '')    AS ten_shisu_juni,
    NULLIF(TRIM(CAST(k.ichi_shisu_juni AS TEXT)), '')    AS ichi_shisu_juni,
    NULLIF(TRIM(CAST(k.agari_shisu_juni AS TEXT)), '')   AS agari_shisu_juni,
    NULLIF(TRIM(CAST(k.gekiso_juni     AS TEXT)), '')    AS gekiso_juni,
    NULLIF(TRIM(CAST(k.kyakushitsu     AS TEXT)), '')    AS kyakushitsu,
    NULLIF(TRIM(CAST(k.pace_yoso       AS TEXT)), '')    AS pace_yoso,
    NULLIF(TRIM(k.kishumei),    '')                      AS kishumei,
    NULLIF(TRIM(k.chokyoshimei), '')                     AS chokyoshimei,
    -- Odds (for filter)
    NULLIF(TRIM(v.tansho_odds), '')                      AS tansho_odds,
    -- Single-win payout
    CASE
        WHEN h.haraimodoshi_tansho_1a IS NOT NULL
             AND v.umaban = h.haraimodoshi_tansho_1a
             AND NULLIF(TRIM(h.haraimodoshi_tansho_1b), '') IS NOT NULL
        THEN CAST(TRIM(h.haraimodoshi_tansho_1b) AS INTEGER)
        ELSE 0
    END AS haraimodoshi_tansho,
    -- Place payout
    CASE
        WHEN h.haraimodoshi_fukusho_1a IS NOT NULL
             AND v.umaban = h.haraimodoshi_fukusho_1a
             AND NULLIF(TRIM(h.haraimodoshi_fukusho_1b), '') IS NOT NULL
        THEN CAST(TRIM(h.haraimodoshi_fukusho_1b) AS INTEGER)
        WHEN h.haraimodoshi_fukusho_2a IS NOT NULL
             AND v.umaban = h.haraimodoshi_fukusho_2a
             AND NULLIF(TRIM(h.haraimodoshi_fukusho_2b), '') IS NOT NULL
        THEN CAST(TRIM(h.haraimodoshi_fukusho_2b) AS INTEGER)
        WHEN h.haraimodoshi_fukusho_3a IS NOT NULL
             AND v.umaban = h.haraimodoshi_fukusho_3a
             AND NULLIF(TRIM(h.haraimodoshi_fukusho_3b), '') IS NOT NULL
        THEN CAST(TRIM(h.haraimodoshi_fukusho_3b) AS INTEGER)
        ELSE 0
    END AS haraimodoshi_fukusho
FROM jrd_kyi_fixed k
JOIN jvd_se v ON
    v.keibajo_code    = k.keibajo_code
    AND SUBSTRING(v.kaisai_nen, 3, 2) = k.race_shikonen
    AND LTRIM(v.kaisai_kai, '0')       = k.kaisai_kai
    AND LTRIM(v.kaisai_nichime, '0')   = k.kaisai_nichime
    AND v.race_bango  = k.race_bango
    AND v.umaban      = k.umaban
LEFT JOIN jvd_hr h ON
    v.kaisai_nen      = h.kaisai_nen
    AND v.kaisai_tsukihi = h.kaisai_tsukihi
    AND v.keibajo_code = h.keibajo_code
    AND v.kaisai_kai   = h.kaisai_kai
    AND v.kaisai_nichime = h.kaisai_nichime
    AND v.race_bango   = h.race_bango
LEFT JOIN jvd_ra r ON
    v.kaisai_nen      = r.kaisai_nen
    AND v.kaisai_tsukihi = r.kaisai_tsukihi
    AND v.keibajo_code = r.keibajo_code
    AND v.kaisai_kai   = r.kaisai_kai
    AND v.kaisai_nichime = r.kaisai_nichime
    AND v.race_bango   = r.race_bango
WHERE v.kaisai_nen >= '2016'
  AND v.kaisai_nen <= '2025'
  AND v.ijo_kubun_code = '0'
  AND v.kakutei_chakujun IS NOT NULL
  AND v.kakutei_chakujun NOT IN ('00', '')
"""


# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_conn():
    return psycopg2.connect(**DB_CONFIG)


# ── Derivation helpers (mirrors factor_screening.py) ─────────────────────────

def _derive_surface(track_code) -> Optional[str]:
    try:
        n = int(str(track_code).strip())
    except (ValueError, TypeError):
        return None
    if 10 <= n <= 19:
        return "\u829d"   # 芝
    if 20 <= n <= 29:
        return "\u30c0"   # ダ
    if n >= 50:
        return "\u969c"   # 障
    return None


def _derive_kyori_kubun(kyori) -> Optional[str]:
    try:
        k = int(kyori)
    except (ValueError, TypeError):
        return None
    if k < 1400:
        return "\u77ed\u8ddd\u96e2"   # 短距離
    if k < 1700:
        return "\u30de\u30a4\u30eb"   # マイル
    if k < 2100:
        return "\u4e2d\u8ddd\u96e2"   # 中距離
    return "\u9577\u8ddd\u96e2"       # 長距離


# ── Formula 1: DB load and compute ───────────────────────────────────────────

def _load_f1_base_data() -> pd.DataFrame:
    """Load base data for Formula 1 from DB; apply odds filter; derive surface/kyori_kubun."""
    print("[INFO] Loading Formula 1 base data from DB...")
    conn = _get_conn()
    try:
        df = pd.read_sql(_F1_BASE_QUERY, conn)
    finally:
        conn.close()
    print(f"[INFO] Raw rows: {len(df):,}")

    # Odds filter: tansho_odds 10-1000 (= 1.0x - 100.0x stored as int*10)
    odds = pd.to_numeric(df["tansho_odds"].astype(str).str.strip(), errors="coerce")
    before = len(df)
    df = df[(odds >= 10) & (odds <= 1000)].copy()
    print(f"[INFO] After odds filter: {before:,} -> {len(df):,} rows")

    # Derive surface and kyori_kubun
    df["surface"]      = df["track_code"].apply(_derive_surface)
    df["kyori_kubun"]  = df["kyori"].apply(_derive_kyori_kubun)

    # 障害レース除外 (surface == "障")
    before_shogai = len(df)
    df = df[df["surface"] != "\u969c"].copy()
    print(f"[INFO] Excluding障害 rows: {before_shogai:,} -> {len(df):,} rows "
          f"(excluded {before_shogai - len(df):,} 障害 rows)")

    # Numeric rank columns: convert to int string for bin labels
    for col in ("ten_shisu_juni", "ichi_shisu_juni", "agari_shisu_juni", "gekiso_juni"):
        num = pd.to_numeric(df[col], errors="coerce")
        df[col] = num.apply(
            lambda x: str(int(x)) if pd.notna(x) else None
        )

    # Code/string columns: strip and normalize
    for col in ("kyakushitsu", "pace_yoso", "kishumei", "chokyoshimei"):
        df[col] = (
            df[col].astype(str).str.strip()
            .replace({"": None, "nan": None, "None": None, "NaN": None})
        )

    return df


def _bin_stats_group(grp: pd.DataFrame) -> Dict:
    """Compute per-bin stats from a grouped DataFrame."""
    n           = len(grp)
    win_count   = int((grp["haraimodoshi_tansho"] > 0).sum())
    place_count = int((grp["haraimodoshi_fukusho"] > 0).sum())
    win_rate    = round(win_count   / n * 100, 1) if n > 0 else 0.0
    place_rate  = round(place_count / n * 100, 1) if n > 0 else 0.0
    w           = grp["year_weight"].astype(float)
    w_sum       = float(w.sum())
    win_roi     = (
        float((grp["haraimodoshi_tansho"].astype(float) * w).sum()) / (w_sum * 100) * 100
        if w_sum > 0 else 0.0
    )
    place_roi   = (
        float((grp["haraimodoshi_fukusho"].astype(float) * w).sum()) / (w_sum * 100) * 100
        if w_sum > 0 else 0.0
    )
    return {
        "n":           n,
        "win_count":   win_count,
        "place_count": place_count,
        "win_rate":    round(win_rate,   1),
        "place_rate":  round(place_rate, 1),
        "win_roi":     round(win_roi,    1),
        "place_roi":   round(place_roi,  1),
    }


def _apply_f1_scores(bins_df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply Formula 1 scores to a DataFrame that has columns:
      name, gid, bin, n, win_rate, place_rate, win_roi, place_roi
    Adds ZH, ZR, Shr, score columns (computed per gid group).
    """
    df = bins_df.copy()
    df["ZH"]    = 0.0
    df["ZR"]    = 0.0
    df["Shr"]   = 0.0
    df["score"] = 0.0

    for gid_val, gidx in df.groupby("gid", sort=False):
        idx = gidx.index
        hit_raw = 0.65 * gidx["win_rate"]  + 0.35 * gidx["place_rate"]
        ret_raw = 0.35 * gidx["win_roi"]   + 0.65 * gidx["place_roi"]

        mu_h, sig_h = hit_raw.mean(), hit_raw.std(ddof=0)
        mu_r, sig_r = ret_raw.mean(), ret_raw.std(ddof=0)

        zh = (hit_raw - mu_h) / sig_h if sig_h > 0 else pd.Series(0.0, index=idx)
        zr = (ret_raw - mu_r) / sig_r if sig_r > 0 else pd.Series(0.0, index=idx)

        # Shr = SQRT(n / (n + 400))
        n_vals = gidx["n"].astype(float)
        shr    = (n_vals / (n_vals + 400.0)).apply(math.sqrt)

        raw_score = (0.55 * zh + 0.45 * zr).apply(math.tanh) * 12.0 * shr
        # n=0 bins → 0.0
        raw_score[gidx["n"] == 0] = 0.0

        df.loc[idx, "ZH"]    = zh.round(4)
        df.loc[idx, "ZR"]    = zr.round(4)
        df.loc[idx, "Shr"]   = shr.round(4)
        df.loc[idx, "score"] = raw_score.round(1)

    return df


def _compute_all_formula1(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute Formula 1 for all 8 FORMULA1_DEFINITIONS.
    Returns a DataFrame with columns:
      name, gid, bin, n, win_rate, place_rate, win_roi, place_roi, ZH, ZR, Shr, score
    """
    all_rows: List[Dict] = []

    for defn in FORMULA1_DEFINITIONS:
        name      = defn["name"]
        gid_cols  = defn["gid_cols"]
        is_multi  = "factor_cols" in defn
        factor_cols = defn.get("factor_cols", [defn.get("factor_col")])

        # Check all needed columns are in df
        needed = gid_cols + factor_cols
        missing = [c for c in needed if c not in df.columns]
        if missing:
            print(f"[WARN] {name}: missing columns {missing}, skip")
            continue

        # Drop rows where any gid col or factor col is None/NaN
        mask = df[gid_cols].notna().all(axis=1) & df[factor_cols].notna().all(axis=1)
        sub  = df[mask].copy()

        if sub.empty:
            print(f"[WARN] {name}: no valid rows after NA filter")
            continue

        # Build bin label
        if is_multi:
            sub["_bin"] = sub[factor_cols[0]].astype(str) + "|" + sub[factor_cols[1]].astype(str)
        else:
            sub["_bin"] = sub[factor_cols[0]].astype(str)

        # Build gid label
        sub["_gid"] = sub[gid_cols[0]].astype(str)
        for c in gid_cols[1:]:
            sub["_gid"] = sub["_gid"] + "_" + sub[c].astype(str)

        # Aggregate per (gid, bin)
        n_before = 0
        n_after  = 0
        for (gid_val, bin_val), grp in sub.groupby(["_gid", "_bin"], sort=True):
            n_before += 1
            if len(grp) < MIN_BIN_N:
                continue
            n_after += 1
            stats = _bin_stats_group(grp)
            all_rows.append({
                "name": name,
                "gid":  str(gid_val),
                "bin":  str(bin_val),
                **stats,
            })

        kept = n_after
        print(f"[F1] {name}: {kept} bins (>={MIN_BIN_N} samples)")

    if not all_rows:
        return pd.DataFrame(columns=[
            "name", "gid", "bin", "n", "win_rate", "place_rate",
            "win_roi", "place_roi", "ZH", "ZR", "Shr", "score",
        ])

    bins_df = pd.DataFrame(all_rows)
    bins_df = _apply_f1_scores(bins_df)
    return bins_df[["name", "gid", "bin", "n", "win_rate", "place_rate",
                    "win_roi", "place_roi", "ZH", "ZR", "Shr", "score"]]


# ── Formula 2 helpers (reads from factor_adoption_detail CSVs) ───────────────

def _safe_filename(segment: str, factors: str) -> str:
    """factor_adoption.py と同一のロジックでファイル名を構築する。"""
    s = f"{segment}_{factors}"
    s = re.sub(r'[\\/:*?"<>|\s+]', '_', s)
    return s[:120] + ".csv"


def _read_csv_safe(path: Path) -> Optional[pd.DataFrame]:
    """utf-8-sig → utf-8 → cp932 の順でCSVを読み込む。"""
    for enc in ("utf-8-sig", "utf-8", "cp932"):
        try:
            return pd.read_csv(path, encoding=enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return None


def _score_formula2(row: pd.Series) -> float:
    """式2（絶対評価）を 1 ビン分計算する。n=0 なら 0.0 を返す。"""
    n = row.get("n", 0)
    if pd.isna(n) or n == 0:
        return 0.0

    wc = row.get("win_count", 0)
    pc = row.get("place_count", 0)
    wc = 0 if pd.isna(wc) else float(wc)
    pc = 0 if pd.isna(pc) else float(pc)

    win_roi   = row.get("win_roi", 0)
    place_roi = row.get("place_roi", 0)
    win_roi   = 0.0 if pd.isna(win_roi)   else float(win_roi)
    place_roi = 0.0 if pd.isna(place_roi) else float(place_roi)

    W  = wc + pc
    X  = min(1.0, math.sqrt(W / 500.0)) if W > 0 else 0.0
    Y  = win_roi * 0.3 + place_roi * 0.7
    Z  = Y - 80.0
    AA = Z * X
    AB = AA / 25.0
    return round(10.0 * math.tanh(AB), 1)


def _compute_formula1_group(detail_df: pd.DataFrame) -> pd.DataFrame:
    """
    [Kept for unit-test compatibility]
    式1（相対評価）をグループ（同一 segment+factors）全ビンに一括適用する。
    Shr = SQRT(n / (n + 400))  ← n をサンプル数として使用
    """
    df = detail_df.copy()

    df["win_rate_f"]   = pd.to_numeric(df.get("win_rate",   0), errors="coerce").fillna(0.0)
    df["place_rate_f"] = pd.to_numeric(df.get("place_rate", 0), errors="coerce").fillna(0.0)
    df["win_roi_f"]    = pd.to_numeric(df.get("win_roi",    0), errors="coerce").fillna(0.0)
    df["place_roi_f"]  = pd.to_numeric(df.get("place_roi",  0), errors="coerce").fillna(0.0)
    df["n_f"]          = pd.to_numeric(df.get("n",          0), errors="coerce").fillna(0.0)

    hit_raw = 0.65 * df["win_rate_f"] + 0.35 * df["place_rate_f"]
    ret_raw = 0.35 * df["win_roi_f"]  + 0.65 * df["place_roi_f"]

    mu_h = hit_raw.mean()
    sig_h = hit_raw.std(ddof=0)
    mu_r = ret_raw.mean()
    sig_r = ret_raw.std(ddof=0)

    zh = (hit_raw - mu_h) / sig_h if sig_h > 0 else pd.Series(0.0, index=df.index)
    zr = (ret_raw - mu_r) / sig_r if sig_r > 0 else pd.Series(0.0, index=df.index)

    # Shr = SQRT(n / (n + 400))
    shr = (df["n_f"] / (df["n_f"] + 400.0)).apply(math.sqrt)

    raw_score = (0.55 * zh + 0.45 * zr).apply(math.tanh) * 12.0 * shr

    # n=0 のビンはスコア 0.0
    mask_zero = df["n_f"] == 0
    raw_score[mask_zero] = 0.0

    df["ZH"]    = zh.round(4)
    df["ZR"]    = zr.round(4)
    df["Shr"]   = shr.round(4)
    df["score"] = raw_score.round(1)

    df.drop(columns=["win_rate_f", "place_rate_f", "win_roi_f", "place_roi_f", "n_f"],
            inplace=True)
    return df


# ── Main logic ────────────────────────────────────────────────────────────────

def run_scoring(
    adoption_csv: Path,
    detail_dir: Path,
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # A) Formula 1 — DB-based computation
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    f1_base_df = _load_f1_base_data()
    f1_df = _compute_all_formula1(f1_base_df)
    print(f"[INFO] Formula 1 total bins: {len(f1_df):,}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # B) Formula 2 — reads from factor_adoption_detail CSVs
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    adoption_df = _read_csv_safe(adoption_csv)
    if adoption_df is None:
        print(f"[ERROR] Cannot read {adoption_csv}")
        sys.exit(1)

    adopted = adoption_df[adoption_df["decision"] == "\u63a1\u7528"].copy()  # "採用"
    # 同一 (segment, factors) が複数 source で重複する場合は先頭1件のみ使用
    before_dedup = len(adopted)
    adopted = adopted.drop_duplicates(subset=["segment", "factors"], keep="first").reset_index(drop=True)
    if len(adopted) < before_dedup:
        print(f"[INFO] Dedup: {before_dedup} -> {len(adopted)} adopted rows "
              f"(removed {before_dedup - len(adopted)} duplicate segment+factors)")

    # 障害レース除外: segment に「障」を含む行を除外
    shogai_mask = adopted["segment"].str.contains("\u969c", na=False)
    shogai_count = int(shogai_mask.sum())
    if shogai_count > 0:
        print(f"[INFO] Excluding {shogai_count} rows with segment containing '障'")
        adopted = adopted[~shogai_mask].reset_index(drop=True)
        print(f"[INFO] Adopted factors after 障害 exclusion: {len(adopted):,} rows")
    print(f"[INFO] Adopted factors (formula2): {len(adopted):,} rows")

    f2_rows:      List[Dict] = []
    summary_rows: List[Dict] = []
    skip_count = 0

    for _, arow in adopted.iterrows():
        segment = str(arow["segment"])
        factors = str(arow["factors"])

        fname  = _safe_filename(segment, factors)
        fpath  = detail_dir / fname
        if not fpath.exists():
            print(f"[SKIP] Not found: {fname}")
            skip_count += 1
            continue

        detail_df = _read_csv_safe(fpath)
        if detail_df is None or detail_df.empty:
            print(f"[SKIP] Empty/unreadable: {fname}")
            skip_count += 1
            continue

        bin_scores = []
        for _, brow in detail_df.iterrows():
            sc  = _score_formula2(brow)
            n_v = float(brow.get("n", 0) or 0)
            f2_rows.append({
                "segment":    segment,
                "factors":    factors,
                "bin":        brow.get("bin", ""),
                "n":          int(n_v),
                "win_rate":   brow.get("win_rate",   None),
                "place_rate": brow.get("place_rate", None),
                "win_roi":    brow.get("win_roi",    None),
                "place_roi":  brow.get("place_roi",  None),
                "score":      sc,
            })
            bin_scores.append(sc)

        scores = pd.Series(bin_scores)
        summary_rows.append({
            "name":          f"{segment} | {factors}",
            "formula":       "formula2",
            "total_bins":    len(scores),
            "positive_bins": int((scores > 0).sum()),
            "negative_bins": int((scores < 0).sum()),
            "avg_score":     round(float(scores.mean()), 3) if len(scores) > 0 else 0.0,
            "max_score":     float(scores.max()) if len(scores) > 0 else 0.0,
            "min_score":     float(scores.min()) if len(scores) > 0 else 0.0,
        })

    # ── Formula 1 summary rows ──────────────────────────────────────
    for name_val, grp in f1_df.groupby("name", sort=False):
        sc = grp["score"]
        summary_rows.append({
            "name":          str(name_val),
            "formula":       "formula1",
            "total_bins":    len(sc),
            "positive_bins": int((sc > 0).sum()),
            "negative_bins": int((sc < 0).sum()),
            "avg_score":     round(float(sc.mean()), 3) if len(sc) > 0 else 0.0,
            "max_score":     float(sc.max()) if len(sc) > 0 else 0.0,
            "min_score":     float(sc.min()) if len(sc) > 0 else 0.0,
        })

    # ── Build DataFrames ────────────────────────────────────────────
    f2_df = pd.DataFrame(f2_rows, columns=[
        "segment", "factors", "bin", "n",
        "win_rate", "place_rate", "win_roi", "place_roi", "score",
    ])
    summary_df = pd.DataFrame(summary_rows, columns=[
        "name", "formula", "total_bins", "positive_bins", "negative_bins",
        "avg_score", "max_score", "min_score",
    ])

    # ── Save CSVs ───────────────────────────────────────────────────
    def _save_csv(df: pd.DataFrame, path: Path) -> None:
        try:
            df.to_csv(path, index=False, encoding="utf-8-sig")
            print(f"[OK] {path}  ({len(df):,} rows)")
        except PermissionError:
            from datetime import datetime
            ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
            bak = path.with_stem(path.stem + f"_{ts}")
            df.to_csv(bak, index=False, encoding="utf-8-sig")
            print(f"[WARN] locked -- written to {bak}  ({len(df):,} rows)")

    _save_csv(f1_df,      output_dir / "bin_scores_formula1.csv")
    _save_csv(f2_df,      output_dir / "bin_scores_formula2.csv")
    _save_csv(summary_df, output_dir / "scoring_summary.csv")

    # ── Console summary ─────────────────────────────────────────────
    f1_count = int((summary_df["formula"] == "formula1").sum())
    f2_count = int((summary_df["formula"] == "formula2").sum())

    print(f"\n[RESULT] Formula1 patterns: {f1_count}  /  Formula2 factors: {f2_count:,}")
    print(f"[RESULT] Skipped (file not found / empty): {skip_count}")
    print(f"[RESULT] Formula1 bins: {len(f1_df):,}  /  Formula2 bins: {len(f2_df):,}")

    # Formula 1 pattern breakdown
    print("\n=== FORMULA1 PATTERN SUMMARY ===")
    for name_val, grp in f1_df.groupby("name", sort=False):
        sc = grp["score"]
        print(f"  {str(name_val):<45}  bins={len(grp):>4}  "
              f"max={sc.max():>5.1f}  min={sc.min():>5.1f}  mean={sc.mean():>5.2f}")

    # TOP20 bins (Formula 1 + Formula 2 combined)
    all_top = []
    for _, r in f1_df.iterrows():
        all_top.append({
            "formula": "F1", "name": r["name"], "gid": r["gid"],
            "bin": r["bin"], "n": r["n"], "score": r["score"],
        })
    for r in f2_rows:
        all_top.append({
            "formula": "F2",
            "name":  f"{r['segment']} | {r['factors']}",
            "gid":   r["segment"],
            "bin":   r["bin"], "n": r["n"], "score": r["score"],
        })

    if all_top:
        all_df = pd.DataFrame(all_top)
        top20  = all_df.nlargest(20, "score")
        print("\n=== TOP20 SCORE BINS ===")
        print(f"{'#':>3} {'F':>2} {'name':<45} {'bin':<20} {'n':>6} {'score':>6}")
        print("-" * 90)
        for rank, (_, row) in enumerate(top20.iterrows(), 1):
            print(
                f"{rank:>3} {row['formula']:>2} "
                f"{str(row['name'])[:44]:<45} "
                f"{str(row['bin'])[:19]:<20} "
                f"{int(row['n']):>6} "
                f"{float(row['score']):>6.1f}"
            )

    print(f"\n[DONE] scoring complete.")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute bin scores (Formula1 DB-based / Formula2 CSV-based)"
    )
    parser.add_argument(
        "--adoption-csv", type=str, default=str(DEFAULT_ADOPTION_CSV),
    )
    parser.add_argument(
        "--detail-dir", type=str, default=str(DEFAULT_DETAIL_DIR),
    )
    parser.add_argument(
        "--output-dir", type=str, default=str(DEFAULT_OUTPUT_DIR),
    )
    args = parser.parse_args()

    run_scoring(
        adoption_csv=Path(args.adoption_csv),
        detail_dir=Path(args.detail_dir),
        output_dir=Path(args.output_dir),
    )


if __name__ == "__main__":
    main()

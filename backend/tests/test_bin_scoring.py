"""
test_bin_scoring.py
===================
bin_scoring.py のユニットテスト（DB 不要・ファイル I/O 不要）。
"""
import math
import pytest
import pandas as pd

from backend.batch.bin_scoring import (
    _safe_filename,
    _score_formula2,
    _compute_formula1_group,
    _derive_surface,
    _derive_kyori_kubun,
    _apply_f1_scores,
)


# ── _safe_filename ─────────────────────────────────────────────────────────────

def test_safe_filename_replaces_plus():
    name = _safe_filename("GLOBAL", "factor_a+factor_b")
    assert "+" not in name
    assert name.endswith(".csv")


def test_safe_filename_replaces_spaces():
    name = _safe_filename("SEG ONE", "factor a")
    assert " " not in name


def test_safe_filename_max_length():
    long_factors = "_".join([f"factor{i}" for i in range(30)])
    name = _safe_filename("GLOBAL", long_factors)
    assert len(name) <= 120 + len(".csv")


def test_safe_filename_segment_factors_concatenated():
    name = _safe_filename("SURFACE_2", "gekiso_juni")
    assert name.startswith("SURFACE_2_")
    assert "gekiso_juni" in name


# ── _derive_surface ───────────────────────────────────────────────────────────

def test_derive_surface_shiba():
    assert _derive_surface("10") == "\u829d"   # 芝
    assert _derive_surface("19") == "\u829d"


def test_derive_surface_dirt():
    assert _derive_surface("20") == "\u30c0"   # ダ
    assert _derive_surface("29") == "\u30c0"


def test_derive_surface_obstacle():
    assert _derive_surface("51") == "\u969c"   # 障


def test_derive_surface_none():
    assert _derive_surface(None) is None
    assert _derive_surface("") is None
    assert _derive_surface("9") is None


# ── _derive_kyori_kubun ───────────────────────────────────────────────────────

def test_derive_kyori_kubun_short():
    assert _derive_kyori_kubun(1200) == "\u77ed\u8ddd\u96e2"   # 短距離


def test_derive_kyori_kubun_mile():
    assert _derive_kyori_kubun(1600) == "\u30de\u30a4\u30eb"   # マイル


def test_derive_kyori_kubun_middle():
    assert _derive_kyori_kubun(2000) == "\u4e2d\u8ddd\u96e2"   # 中距離


def test_derive_kyori_kubun_long():
    assert _derive_kyori_kubun(2400) == "\u9577\u8ddd\u96e2"   # 長距離


def test_derive_kyori_kubun_none():
    assert _derive_kyori_kubun(None) is None
    assert _derive_kyori_kubun("abc") is None


# ── _apply_f1_scores ──────────────────────────────────────────────────────────

def _make_f1_bins_df():
    return pd.DataFrame({
        "name":       ["P×F"] * 4,
        "gid":        ["G1", "G1", "G2", "G2"],
        "bin":        ["A", "B", "C", "D"],
        "n":          [200, 150, 100, 80],
        "win_rate":   [20.0, 13.0, 10.0, 8.0],
        "place_rate": [40.0, 30.0, 28.0, 20.0],
        "win_roi":    [150.0, 100.0, 80.0, 60.0],
        "place_roi":  [110.0,  90.0, 75.0, 55.0],
    })


def test_apply_f1_scores_columns():
    df = _make_f1_bins_df()
    result = _apply_f1_scores(df)
    for col in ["ZH", "ZR", "Shr", "score"]:
        assert col in result.columns, f"Missing: {col}"


def test_apply_f1_scores_shr_uses_n():
    """Shr = SQRT(n / (n + 400)) — computed from n directly."""
    df = _make_f1_bins_df()
    result = _apply_f1_scores(df)
    # Verify Shr for n=200: sqrt(200/600) ≈ 0.5774
    expected_shr = round(math.sqrt(200 / 600), 4)
    assert abs(result.loc[result["n"] == 200, "Shr"].iloc[0] - expected_shr) < 1e-3


def test_apply_f1_scores_range():
    df = _make_f1_bins_df()
    result = _apply_f1_scores(df)
    for sc in result["score"]:
        assert -12.0 <= sc <= 12.0


def test_apply_f1_scores_zero_n():
    df = _make_f1_bins_df()
    df.loc[0, "n"] = 0
    result = _apply_f1_scores(df)
    assert result.loc[0, "score"] == 0.0


def test_apply_f1_scores_per_gid():
    """異なる gid グループのスコアは独立して計算される。"""
    df = _make_f1_bins_df()
    result = _apply_f1_scores(df)
    # G1 の ZH と G2 の ZH は独立（G1 の mean/std != G2）
    g1 = result[result["gid"] == "G1"]["ZH"].tolist()
    g2 = result[result["gid"] == "G2"]["ZH"].tolist()
    # 各グループ内の ZH は平均 ≈ 0 になるはず
    assert abs(sum(g1) / len(g1)) < 1e-9
    assert abs(sum(g2) / len(g2)) < 1e-9


# ── _score_formula2 ───────────────────────────────────────────────────────────

def _make_row(**kwargs):
    return pd.Series(kwargs)


def test_score_formula2_zero_n():
    """n=0 → score=0.0"""
    row = _make_row(n=0, win_count=0, place_count=0, win_roi=100.0, place_roi=80.0)
    assert _score_formula2(row) == 0.0


def test_score_formula2_nan_n():
    """n=NaN → score=0.0"""
    row = _make_row(n=float("nan"), win_count=0, place_count=0, win_roi=100.0, place_roi=80.0)
    assert _score_formula2(row) == 0.0


def test_score_formula2_high_roi():
    """高 ROI ビン → 正のスコア"""
    row = _make_row(n=200, win_count=50, place_count=80, win_roi=180.0, place_roi=130.0)
    sc = _score_formula2(row)
    assert sc > 0.0
    assert -10.0 <= sc <= 10.0


def test_score_formula2_low_roi():
    """低 ROI ビン → 負のスコア"""
    row = _make_row(n=500, win_count=20, place_count=50, win_roi=50.0, place_roi=40.0)
    sc = _score_formula2(row)
    assert sc < 0.0


def test_score_formula2_range():
    """スコアは -10.0 〜 +10.0 の範囲内"""
    for win_roi, place_roi, n, wc, pc in [
        (500.0, 400.0, 1000, 100, 200),
        (0.0, 0.0, 1000, 0, 0),
        (100.0, 80.0, 500, 50, 100),
    ]:
        row = _make_row(n=n, win_count=wc, place_count=pc,
                        win_roi=win_roi, place_roi=place_roi)
        sc = _score_formula2(row)
        assert -10.0 <= sc <= 10.0, f"Out of range: {sc}"


def test_score_formula2_nan_roi():
    """win_roi / place_roi が NaN → 0 扱いで計算クラッシュしない"""
    row = _make_row(n=100, win_count=10, place_count=20,
                    win_roi=float("nan"), place_roi=float("nan"))
    sc = _score_formula2(row)
    assert isinstance(sc, float)
    assert not math.isnan(sc)


# ── _compute_formula1_group ───────────────────────────────────────────────────

def _make_detail_df():
    return pd.DataFrame({
        "bin":         ["A", "B", "C", "D"],
        "n":           [200, 150, 100, 50],
        "win_count":   [40,  20,  10,  5],
        "place_count": [80,  50,  30, 10],
        "win_rate":    [20.0, 13.3, 10.0, 10.0],
        "place_rate":  [40.0, 33.3, 30.0, 20.0],
        "win_roi":     [150.0, 100.0, 80.0, 70.0],
        "place_roi":   [110.0,  90.0, 75.0, 60.0],
    })


def test_compute_formula1_group_columns():
    """必要列 ZH, ZR, Shr, score が追加される"""
    df = _make_detail_df()
    result = _compute_formula1_group(df)
    for col in ["ZH", "ZR", "Shr", "score"]:
        assert col in result.columns, f"Missing column: {col}"


def test_compute_formula1_group_score_range():
    """スコアは -12.0 〜 +12.0 の範囲内"""
    df = _make_detail_df()
    result = _compute_formula1_group(df)
    for sc in result["score"]:
        assert -12.0 <= sc <= 12.0, f"Out of range: {sc}"


def test_compute_formula1_group_zero_n():
    """n=0 のビンはスコア 0.0"""
    df = _make_detail_df()
    df.loc[0, "n"] = 0
    df.loc[0, "win_count"] = 0
    df.loc[0, "place_count"] = 0
    result = _compute_formula1_group(df)
    assert result.loc[0, "score"] == 0.0


def test_compute_formula1_group_shr_uses_n():
    """Shr = SQRT(n / (n + 400)) — n を直接使う（place_count に依存しない）"""
    df = _make_detail_df()
    result = _compute_formula1_group(df)
    # n=200 → Shr ≈ sqrt(200/600) ≈ 0.5774
    expected = round(math.sqrt(200 / 600), 4)
    actual = result.loc[result["n"] == 200, "Shr"].iloc[0]
    assert abs(actual - expected) < 1e-3
    assert result["Shr"].max() > 0.0


def test_compute_formula1_group_shr_bounds():
    """Shr は 0 〜 1 の範囲"""
    df = _make_detail_df()
    result = _compute_formula1_group(df)
    for shr in result["Shr"]:
        assert 0.0 <= shr <= 1.0


def test_compute_formula1_group_place_count_nan_still_works():
    """place_count が NaN でも Shr は n から計算されるため非ゼロ"""
    df = _make_detail_df()
    df["place_count"] = float("nan")
    result = _compute_formula1_group(df)
    assert result["Shr"].max() > 0.0
    for shr in result["Shr"]:
        assert 0.0 <= shr <= 1.0


def test_compute_formula1_group_place_count_missing_column():
    """place_count カラム自体が存在しなくても正常動作する"""
    df = _make_detail_df().drop(columns=["place_count"])
    result = _compute_formula1_group(df)
    assert result["Shr"].max() > 0.0
    for shr in result["Shr"]:
        assert 0.0 <= shr <= 1.0


def test_compute_formula1_group_uniform_hit():
    """全ビンの HitRaw が同じ → ZH = 0 → score は ZR のみに依存"""
    df = pd.DataFrame({
        "bin":         ["A", "B"],
        "n":           [200, 200],
        "win_count":   [40,  20],
        "place_count": [80,  60],
        "win_rate":    [20.0, 20.0],   # 同一
        "place_rate":  [20.0, 20.0],   # 同一 → HitRaw 同一 → ZH = 0
        "win_roi":     [150.0, 80.0],
        "place_roi":   [110.0, 70.0],
    })
    result = _compute_formula1_group(df)
    assert result["ZH"].abs().max() < 1e-9

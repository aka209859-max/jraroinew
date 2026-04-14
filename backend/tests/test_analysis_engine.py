"""
分析エンジンテスト

全テストは実際のDBに接続して実行する（conftest.pyのdb_connectionフィクスチャを使用）。
高速化のため data_period は1年（2024年）に限定するテストが多い。
"""
import math
import pytest
import pandas as pd

from backend.engine.analysis_engine import AnalysisQuery, run_analysis

# デフォルト1年間（テスト高速化）
_PERIOD_2024 = ["2024-01-01", "2024-12-31"]

# 必須カラム12列
_REQUIRED_COLS = [
    "bin_label", "tansho_count", "tansho_hit", "tansho_hit_rate", "tansho_roi",
    "fukusho_count", "fukusho_hit", "fukusho_hit_rate", "fukusho_roi",
    "tansho_corrected_roi", "fukusho_corrected_roi", "confidence",
]


# =============================================================================
# 1. AnalysisQuery デフォルト値確認
# =============================================================================

def test_analysis_query_defaults():
    """AnalysisQuery のデフォルト値が正しいことを確認する。"""
    q = AnalysisQuery(name="test", segment="GLOBAL", key1="barei")
    assert q.key2 is None
    assert q.key3 is None
    assert q.prev_race_type == "none"
    assert q.odds_filter["tansho"] == [1.0, 100.0]
    assert q.odds_filter["fukusho"] == [1.0, 17.0]
    assert q.data_period == ["2016-01-01", "2025-12-31"]
    assert q.year_weights[2016] == 1
    assert q.year_weights[2025] == 10
    assert q.min_samples == 30
    assert q.conditions == {}
    assert q.bin_config == {}


# =============================================================================
# 2. 基本分析（単一キー）
# =============================================================================

def test_basic_analysis_single_key(db_connection):
    """key1="barei", segment="GLOBAL", prev_race_type="none" で基本動作を確認する。"""
    query = AnalysisQuery(
        name="barei_global",
        segment="GLOBAL",
        key1="barei",
        prev_race_type="none",
        data_period=_PERIOD_2024,
    )
    result = run_analysis(db_connection, query)

    assert "segments" in result
    assert "GLOBAL" in result["segments"]
    df = result["segments"]["GLOBAL"]

    # DataFrame が空でない
    assert not df.empty, "結果DataFrameが空です"

    # 必須12列が全て存在する
    for col in _REQUIRED_COLS:
        assert col in df.columns, f"必須カラム '{col}' が存在しない"

    # tansho_count > 0 のビンが存在する
    assert (df["tansho_count"] > 0).any(), "tansho_count > 0 のビンがない"

    # tansho_hit_rate が 0〜100 の範囲内
    valid = df[df["tansho_count"] > 0]
    assert (valid["tansho_hit_rate"] >= 0).all()
    assert (valid["tansho_hit_rate"] <= 100).all()


# =============================================================================
# 3. 単勝・複勝の件数差異
# =============================================================================

def test_tansho_fukusho_count_differ(db_connection):
    """tansho_count_total != fukusho_count_total であることを確認する。

    オッズフィルタが tansho=[1,100] vs fukusho=[1,17] で異なるため、
    100倍超の馬は tansho には含まれるが fukusho には含まれない。
    """
    query = AnalysisQuery(
        name="count_differ_test",
        segment="GLOBAL",
        key1="barei",
        prev_race_type="none",
        data_period=_PERIOD_2024,
    )
    result = run_analysis(db_connection, query)
    df = result["segments"]["GLOBAL"]

    tansho_total = df["tansho_count"].sum()
    fukusho_total = df["fukusho_count"].sum()

    assert tansho_total > 0
    assert fukusho_total > 0
    # tansho フィルタ [1,100] は fukusho フィルタ [1,17] より広いので tansho >= fukusho
    assert tansho_total >= fukusho_total
    # 実際には 17倍超の馬が存在するため、不等号であることを確認
    assert tansho_total != fukusho_total, (
        f"tansho_total={tansho_total} == fukusho_total={fukusho_total}: "
        "オッズフィルタの差が反映されていない"
    )


# =============================================================================
# 4. 取消馬の除外確認
# =============================================================================

def test_cancelled_horses_excluded(db_connection):
    """kakutei_chakujun='00'（取消馬）が集計から除外されることを確認する。"""
    # 取消馬の件数をDBで確認
    df_cancel = pd.read_sql(
        "SELECT COUNT(*) AS cnt FROM jvd_se "
        "WHERE TRIM(kakutei_chakujun) = '00' AND kaisai_nen = '2024'",
        db_connection,
    )
    n_cancelled = int(df_cancel["cnt"].iloc[0])

    query = AnalysisQuery(
        name="cancel_test",
        segment="GLOBAL",
        key1="barei",
        prev_race_type="none",
        data_period=_PERIOD_2024,
    )
    result = run_analysis(db_connection, query)
    summary = result["summary"]

    # ロード後のフィルタで行数が減少していること
    assert summary["filtered_rows"] <= summary["total_rows"]

    if n_cancelled > 0:
        # 取消馬が存在する場合、フィルタ後の行数 < ロード行数
        assert summary["filtered_rows"] < summary["total_rows"], (
            f"取消馬が {n_cancelled} 件存在するのにフィルタ前後で行数が変わらない"
        )


# =============================================================================
# 5. ビンの数値順ソート確認
# =============================================================================

def test_bin_sort_numeric(db_connection):
    """barei（馬齢）のビンが数値順でソートされることを確認する。

    文字列ソートだと "10" < "2" になるバグが発生する。
    """
    query = AnalysisQuery(
        name="sort_test",
        segment="GLOBAL",
        key1="barei",
        prev_race_type="none",
        data_period=_PERIOD_2024,
    )
    result = run_analysis(db_connection, query)
    df = result["segments"]["GLOBAL"]
    assert not df.empty

    # "不明" / "その他" 以外のビンを取得
    numeric_bins = df[~df["bin_label"].isin(["不明", "その他"])]["bin_label"].tolist()

    if len(numeric_bins) < 2:
        pytest.skip("ビン数が少なすぎてソート確認不可")

    # 数値に変換できるビン値が数値順になっているか確認
    numeric_vals = []
    for b in numeric_bins:
        try:
            numeric_vals.append(float(b))
        except (ValueError, TypeError):
            # 数値変換できないビンはスキップ
            pass

    if len(numeric_vals) >= 2:
        assert numeric_vals == sorted(numeric_vals), (
            f"数値順になっていない: {numeric_vals}"
        )


# =============================================================================
# 6. NULL ビンの存在確認
# =============================================================================

def test_null_bin_exists(db_connection):
    """fukusho_odds で分析した場合、"不明"ビンが存在することを確認する。

    fukusho_odds は jvd_hr（払戻テーブル）から取得するため、
    複勝的中馬（3着以内）のみ値がある。約 75-80% の行が NULL になる。
    NULLは除外せず "不明" ビンにまとめること。
    """
    query = AnalysisQuery(
        name="null_bin_test",
        segment="GLOBAL",
        key1="fukusho_odds",   # 複勝払戻: 的中馬のみ値あり（約25%）→ NULLが多い
        prev_race_type="none",
        data_period=_PERIOD_2024,
    )
    result = run_analysis(db_connection, query)
    df = result["segments"]["GLOBAL"]

    assert not df.empty
    # "不明" ビンが存在すること（約75%の行がNULL）
    assert "不明" in df["bin_label"].values, (
        f"fukusho_odds の NULL が '不明' ビンにまとめられていない。"
        f"存在するビン: {df['bin_label'].tolist()}"
    )
    # "不明" ビンのサンプル数が 0 でないこと
    unknown_row = df[df["bin_label"] == "不明"]
    assert unknown_row["tansho_count"].iloc[0] + unknown_row["fukusho_count"].iloc[0] > 0


# =============================================================================
# 7. 高カーディナリティのグルーピング
# =============================================================================

def test_high_cardinality_grouping(db_connection):
    """ketto_toroku_bango（馬の血統登録番号、年間10,000+種）で分析した場合、
    ビン数が 52 以下（上位50 + その他 + 不明）であることを確認する。
    """
    query = AnalysisQuery(
        name="high_card_test",
        segment="GLOBAL",
        key1="ketto_toroku_bango",   # 馬ID: 年間10,000+の一意な値 → 高カーディナリティ
        prev_race_type="none",
        data_period=_PERIOD_2024,
    )
    result = run_analysis(db_connection, query)
    df = result["segments"]["GLOBAL"]

    assert not df.empty
    n_bins = len(df)
    # 上位50 + "その他" + "不明" = 最大52
    assert n_bins <= 52, f"ビン数が多すぎる: {n_bins}（最大52を期待）"
    # "その他" ビンが存在すること（10,000+種類なら必ず上位50以外がある）
    assert "その他" in df["bin_label"].values, "'その他' ビンが存在しない"


# =============================================================================
# 8. SURFACE_2 セグメント
# =============================================================================

def test_surface2_segment(db_connection):
    """segment="SURFACE_2" で芝・ダートに分割されることを確認する。"""
    query = AnalysisQuery(
        name="surface2_test",
        segment="SURFACE_2",
        key1="barei",
        prev_race_type="none",
        data_period=_PERIOD_2024,
    )
    result = run_analysis(db_connection, query)
    segments = result["segments"]

    # 芝 と ダート の両セグメントが存在すること
    assert "芝" in segments, f"芝セグメントなし。存在するセグメント: {list(segments.keys())}"
    assert "ダート" in segments, f"ダートセグメントなし。存在するセグメント: {list(segments.keys())}"

    # 両セグメントにデータが存在すること
    assert not segments["芝"].empty
    assert not segments["ダート"].empty


# =============================================================================
# 9. クロスキー（key1 × key2）
# =============================================================================

def test_cross_key(db_connection):
    """key1="barei", key2="sex_code" でクロス集計し、
    bin_label が "X × Y" 形式であることを確認する。
    """
    query = AnalysisQuery(
        name="cross_test",
        segment="GLOBAL",
        key1="barei",
        key2="sex_code",
        prev_race_type="none",
        data_period=_PERIOD_2024,
    )
    result = run_analysis(db_connection, query)
    df = result["segments"]["GLOBAL"]

    assert not df.empty

    # "不明" 以外のビンは " × " を含む
    non_unknown = df[~df["bin_label"].isin(["不明", "その他"])]
    if not non_unknown.empty:
        cross_bins = non_unknown[non_unknown["bin_label"].str.contains(" × ", na=False)]
        assert len(cross_bins) > 0, (
            f"' × ' 形式のビンが存在しない。サンプル: {non_unknown['bin_label'].head(3).tolist()}"
        )


# =============================================================================
# 10. 信頼度の計算式確認
# =============================================================================

def test_confidence_formula(db_connection):
    """信頼度 = sqrt(min(N_t, N_f) / (min + 400)) の実装を全ビンで検証する。"""
    query = AnalysisQuery(
        name="confidence_test",
        segment="GLOBAL",
        key1="barei",
        prev_race_type="none",
        data_period=_PERIOD_2024,
    )
    result = run_analysis(db_connection, query)
    df = result["segments"]["GLOBAL"]
    assert not df.empty

    for _, row in df.iterrows():
        n_min = min(int(row["tansho_count"]), int(row["fukusho_count"]))
        expected = math.sqrt(n_min / (n_min + 400)) if n_min > 0 else 0.0
        actual = float(row["confidence"])
        assert abs(actual - expected) < 1e-3, (
            f"ビン '{row['bin_label']}': "
            f"confidence={actual:.6f}, expected={expected:.6f} "
            f"(N_t={row['tansho_count']}, N_f={row['fukusho_count']})"
        )

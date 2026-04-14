"""
FastAPI エンドポイントテスト
"""
import pytest


# =============================================================================
# 1. ルートエンドポイント
# =============================================================================

def test_root_endpoint(client):
    """GET / が 200 を返し、'Enable Edge Engine' を含むこと。"""
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert "Enable Edge Engine" in body.get("name", ""), (
        f"レスポンスに 'Enable Edge Engine' がない: {body}"
    )


# =============================================================================
# 2. ヘルスチェック
# =============================================================================

def test_health_endpoint(client):
    """GET /api/health が {"status": "ok"} を返すこと。"""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_db_health_endpoint(client):
    """GET /api/health/db が {"status": "ok", "database": "connected"} を返すこと。"""
    resp = client.get("/api/health/db")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("status") == "ok", f"DB health status: {body}"
    assert body.get("database") == "connected", f"DB health database: {body}"


# =============================================================================
# 4. セグメント一覧
# =============================================================================

def test_segments_endpoint(client):
    """GET /api/analysis/segments が 3つのセグメントを返すこと。"""
    resp = client.get("/api/analysis/segments")
    assert resp.status_code == 200
    body = resp.json()
    assert "segments" in body
    segments = body["segments"]
    assert len(segments) == 3, f"セグメント数が3でない: {len(segments)}"
    ids = {s["id"] for s in segments}
    assert "GLOBAL" in ids
    assert "SURFACE_2" in ids
    assert "COURSE_27" in ids


# =============================================================================
# 5. ファクター一覧
# =============================================================================

def test_factors_endpoint(client):
    """GET /api/analysis/factors が空でないリストを返すこと。"""
    resp = client.get("/api/analysis/factors")
    assert resp.status_code == 200
    body = resp.json()
    assert "factors" in body
    factors = body["factors"]
    assert len(factors) > 0, "ファクターリストが空"
    # 先頭エントリに table_name / column_name が含まれること
    first = factors[0]
    assert "table_name" in first, f"table_name がない: {first}"
    assert "column_name" in first, f"column_name がない: {first}"
    # 全2293カラム分あること
    assert body["total"] >= 2293, f"カラム数が少なすぎる: {body['total']}"


# =============================================================================
# 6. 分析エンドポイント（DB アクセスあり・低速）
# =============================================================================

def test_analyze_endpoint_basic(client):
    """POST /api/analysis/analyze で基本分析が実行できること。

    注意: DBアクセスがあるため30秒以上かかる場合がある。
    data_period を 1年に限定して高速化。
    """
    payload = {
        "name": "API test - barei GLOBAL",
        "segment": "GLOBAL",
        "key1": "barei",
        "data_period": ["2024-01-01", "2024-12-31"],
    }
    resp = client.post("/api/analysis/analyze", json=payload, timeout=120)
    assert resp.status_code == 200, f"ステータスコード異常: {resp.status_code} - {resp.text[:200]}"

    body = resp.json()
    assert body["query_name"] == "API test - barei GLOBAL"
    assert body["total_rows"] > 0
    assert "segments" in body
    assert len(body["segments"]) > 0, "segments が空"

    seg = body["segments"][0]
    assert seg["segment_name"] == "GLOBAL"
    assert seg["total_bins"] > 0, "ビンが0"
    assert len(seg["data"]) > 0, "data が空"

    # 先頭ビンの必須カラム確認
    first_bin = seg["data"][0]
    required_keys = [
        "bin_label", "tansho_count", "tansho_hit", "tansho_hit_rate", "tansho_roi",
        "fukusho_count", "fukusho_hit", "fukusho_hit_rate", "fukusho_roi",
        "tansho_corrected_roi", "fukusho_corrected_roi", "confidence",
    ]
    for key in required_keys:
        assert key in first_bin, f"レスポンスに '{key}' がない: {list(first_bin.keys())}"

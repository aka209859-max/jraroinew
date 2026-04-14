"""
分析APIエンドポイント
"""
from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.config.database import get_connection
from backend.engine.analysis_engine import AnalysisQuery, run_analysis

router = APIRouter()

# =============================================================================
# Request / Response モデル
# =============================================================================

class AnalysisRequest(BaseModel):
    name: str
    segment: str
    key1: str
    key2: Optional[str] = None
    key3: Optional[str] = None
    conditions: dict = Field(default_factory=dict)
    odds_filter: dict = Field(default_factory=lambda: {"tansho": [1.0, 100.0], "fukusho": [1.0, 17.0]})
    prev_race_type: str = "none"
    data_period: list = Field(default_factory=lambda: ["2016-01-01", "2025-12-31"])
    year_weights: dict = Field(default_factory=lambda: {
        "2016": 1, "2017": 2, "2018": 3, "2019": 4, "2020": 5,
        "2021": 6, "2022": 7, "2023": 8, "2024": 9, "2025": 10,
    })
    min_samples: int = 30
    bin_config: dict = Field(default_factory=dict)


class SegmentResult(BaseModel):
    segment_name: str
    data: list[dict]
    edge_bins_tansho: int
    edge_bins_fukusho: int
    total_bins: int


class AnalysisResponse(BaseModel):
    query_name: str
    total_rows: int
    valid_tansho_rows: int
    valid_fukusho_rows: int
    segments: list[SegmentResult]


# =============================================================================
# ヘルパー
# =============================================================================

_SCHEMA_CSV = Path(__file__).parents[3] / "docs" / "ACTUAL_DB_SCHEMA_2293_COLUMNS.csv"


def _request_to_query(req: AnalysisRequest) -> AnalysisQuery:
    """AnalysisRequest → AnalysisQuery に変換する。year_weights のキーを int に変換。"""
    year_weights_int = {int(k): v for k, v in req.year_weights.items()}
    return AnalysisQuery(
        name=req.name,
        segment=req.segment,
        key1=req.key1,
        key2=req.key2,
        key3=req.key3,
        conditions=req.conditions,
        odds_filter=req.odds_filter,
        prev_race_type=req.prev_race_type,
        data_period=req.data_period,
        year_weights=year_weights_int,
        min_samples=req.min_samples,
        bin_config=req.bin_config,
    )


def _df_to_dicts(df) -> list[dict]:
    """DataFrameを JSON シリアライズ可能な dict list に変換する。"""
    records = df.to_dict(orient="records")
    # numpy型をPython型に変換
    import math
    result = []
    for row in records:
        cleaned = {}
        for k, v in row.items():
            if hasattr(v, "item"):
                v = v.item()
            if isinstance(v, float) and math.isnan(v):
                v = None
            cleaned[k] = v
        result.append(cleaned)
    return result


# =============================================================================
# エンドポイント
# =============================================================================

@router.post("/analyze", response_model=AnalysisResponse)
def run_analysis_endpoint(request: AnalysisRequest):
    """分析を実行して結果を返す。"""
    query = _request_to_query(request)

    conn = get_connection()
    try:
        result = run_analysis(conn, query)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分析実行エラー: {e}")
    finally:
        conn.close()

    summary = result["summary"]
    segment_results = []

    for seg_name, df in result["segments"].items():
        if df.empty:
            segment_results.append(SegmentResult(
                segment_name=seg_name,
                data=[],
                edge_bins_tansho=0,
                edge_bins_fukusho=0,
                total_bins=0,
            ))
            continue

        edge_t = int(
            ((df["tansho_corrected_roi"] >= 80) & (df["confidence"] >= 0.25)).sum()
        )
        edge_f = int(
            ((df["fukusho_corrected_roi"] >= 80) & (df["confidence"] >= 0.25)).sum()
        )
        segment_results.append(SegmentResult(
            segment_name=seg_name,
            data=_df_to_dicts(df),
            edge_bins_tansho=edge_t,
            edge_bins_fukusho=edge_f,
            total_bins=len(df),
        ))

    return AnalysisResponse(
        query_name=query.name,
        total_rows=summary["total_rows"],
        valid_tansho_rows=summary["valid_tansho_rows"],
        valid_fukusho_rows=summary["valid_fukusho_rows"],
        segments=segment_results,
    )


@router.get("/factors")
def get_available_factors():
    """利用可能なファクター（カラム）一覧を返す。ACTUAL_DB_SCHEMA_2293_COLUMNS.csv から生成。"""
    if not _SCHEMA_CSV.exists():
        raise HTTPException(status_code=500, detail="スキーマCSVが見つかりません")

    factors = []
    with open(_SCHEMA_CSV, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            factors.append({
                "table_name": row.get("table_name", ""),
                "column_name": row.get("column_name", ""),
                "data_type": row.get("data_type", ""),
                "comment": row.get("column_comment", ""),
            })

    return {"factors": factors, "total": len(factors)}


@router.get("/segments")
def get_segments():
    """利用可能なセグメント一覧を返す。"""
    return {
        "segments": [
            {"id": "GLOBAL",    "name": "全体",         "description": "全データを一括集計"},
            {"id": "SURFACE_2", "name": "芝/ダート",     "description": "芝・ダートで分割集計"},
            {"id": "COURSE_27", "name": "27コース分類",  "description": "27コース分類ごとに集計"},
        ]
    }

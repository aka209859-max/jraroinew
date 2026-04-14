"""
年度別重み係数

新しい年度ほど重みが大きい線形増加設計。
Walk-Forward検証での補正回収率算出に使用する。
"""
from typing import Dict

YEAR_WEIGHTS: Dict[str, int] = {
    "2016": 1,
    "2017": 2,
    "2018": 3,
    "2019": 4,
    "2020": 5,
    "2021": 6,
    "2022": 7,
    "2023": 8,
    "2024": 9,
    "2025": 10,
}


def get_year_weight(year: str | int) -> int:
    """
    年度から重み係数を取得する。

    Args:
        year: 年度（str or int）

    Returns:
        重み係数（int）。該当なしの場合は0。
    """
    return YEAR_WEIGHTS.get(str(year), 0)

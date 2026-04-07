"""
因子基类 — 所有因子继承此类

v2: 增加 score() 方法，返回 0-100 连续评分（compute() 保持布尔兼容）
"""

from abc import ABC, abstractmethod
import pandas as pd
import numpy as np
from typing import Any


class BaseFactor(ABC):
    """因子基类"""

    name: str = "unnamed"
    description: str = ""
    weight: float = 1.0  # 默认权重，可在 settings 中覆盖

    def __init__(self, **params):
        self.params = params

    @abstractmethod
    def compute(self, df: pd.DataFrame) -> pd.Series:
        """
        计算因子值（布尔信号）

        Returns:
            布尔 Series，True = 当日满足该因子条件
        """
        ...

    def score(self, df: pd.DataFrame) -> pd.Series:
        """
        计算因子评分（0-100 连续值）

        默认实现：True=100, False=0
        子类可覆盖以提供更细粒度的评分
        """
        return self.compute(df).astype(float) * 100

    def __repr__(self):
        return f"{self.name}({self.params})"

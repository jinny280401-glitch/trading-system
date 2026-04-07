"""
量价因子 — v2 向量化

因子: 连跌缩量 — 连续 N 天下跌 + 成交量逐日萎缩
"""

import pandas as pd
import numpy as np
from .base import BaseFactor


class ConsecutiveDecline(BaseFactor):
    """
    连跌缩量

    v2: 用 groupby + cumcount 向量化，O(n) 替代 O(n*k)
    """
    name = "consecutive_decline"
    description = "连跌N天且缩量"

    def __init__(self, min_days: int = 3, max_days: int = 7, volume_shrink: bool = True):
        super().__init__(min_days=min_days, max_days=max_days, volume_shrink=volume_shrink)
        self.min_days = min_days
        self.max_days = max_days
        self.volume_shrink = volume_shrink

    def compute(self, df: pd.DataFrame) -> pd.Series:
        is_down = df["pct_chg"] < 0
        vol_shrink = df["volume"] < df["volume"].shift(1)

        # 连续下跌天数计数（向量化）
        # 原理：每次不下跌时断开分组，组内累计计数
        not_down = ~is_down
        groups = not_down.cumsum()
        down_streak = is_down.groupby(groups).cumcount() + 1
        down_streak = down_streak.where(is_down, 0)

        if self.volume_shrink:
            # 连续缩量天数（同理）
            not_shrink = ~vol_shrink
            vol_groups = not_shrink.cumsum()
            shrink_streak = vol_shrink.groupby(vol_groups).cumcount() + 1
            shrink_streak = shrink_streak.where(vol_shrink, 0)

            # 连跌 >= min_days 且 连续缩量 >= min_days - 1
            result = (down_streak >= self.min_days) & (shrink_streak >= self.min_days - 1)
        else:
            result = down_streak >= self.min_days

        return result

    def score(self, df: pd.DataFrame) -> pd.Series:
        """评分：连跌天数越多 + 缩量越明显 → 分越高（卖压衰竭越充分）"""
        is_down = df["pct_chg"] < 0
        not_down = ~is_down
        groups = not_down.cumsum()
        down_streak = is_down.groupby(groups).cumcount() + 1
        down_streak = down_streak.where(is_down, 0)

        # 连跌天数 3~7 天映射到 30~70 分
        streak_score = ((down_streak - self.min_days + 1)
                        .clip(lower=0, upper=self.max_days - self.min_days + 1)
                        / (self.max_days - self.min_days + 1) * 40 + 30)

        if self.volume_shrink:
            # 缩量比例：当日量/前日量，越小越好
            # fillna(1.0) 防止首行 shift 产生 NaN
            vol_ratio = (df["volume"] / df["volume"].shift(1)).fillna(1.0).clip(lower=0.1, upper=1.0)
            # 量比 1.0→0分, 0.1→30分
            shrink_score = (1 - vol_ratio) / 0.9 * 30
            total = streak_score + shrink_score
        else:
            total = streak_score

        signal = self.compute(df)
        return total.where(signal, 0).fillna(0)

"""
BBIBOLL 因子

BBI (多空指标) = 多条均线的均值
BBIBOLL = 对 BBI 做布林通道（通达信标准参数 N=11, M=6）

因子: 股价触及 BBIBOLL 下轨附近后反弹（黄金坑入场信号）
"""

import pandas as pd
import numpy as np
from .base import BaseFactor


def compute_bbi(close: pd.Series, periods: list = None) -> pd.Series:
    """
    计算 BBI（Bull Bear Index）

    BBI = (MA(p1) + MA(p2) + MA(p3) + MA(p4)) / len(periods)
    默认 periods = [3, 6, 12, 24]
    """
    if periods is None:
        periods = [3, 6, 12, 24]
    ma_sum = sum(close.rolling(p).mean() for p in periods)
    return ma_sum / len(periods)


def compute_bbiboll(close: pd.Series, bbi_periods: list = None,
                    boll_period: int = 11, boll_std: float = 6):
    """
    计算 BBIBOLL 三轨（通达信标准: N=11, M=6）

    BBI 本身是4条均线的均值，波动率天然被压缩，
    所以需要 M=6 才能产生有效带宽（M=3 太窄，假信号多）。

    Returns:
        (bbi, upper, lower) 三条线
    """
    bbi = compute_bbi(close, bbi_periods)
    mid = bbi
    std = bbi.rolling(boll_period).std()
    upper = mid + boll_std * std
    lower = mid - boll_std * std
    return bbi, upper, lower


class BBIBOLLLowerBounce(BaseFactor):
    """
    BBIBOLL 低轨反弹（黄金坑 Gate 4）：
    - 连续 min_days_below 天收盘 <= 下轨
    - 当天收盘 > 昨收（反弹启动）

    通达信标准参数: boll_period=11, boll_std=6
    min_days_below=1 为默认，设为 3 可提高精度（研究显示胜率~80%）
    """
    name = "bbiboll"
    description = "BBIBOLL下轨反弹"

    def __init__(self, bbi_periods: list = None, boll_period: int = 11,
                 boll_std: float = 6, min_days_below: int = 1):
        super().__init__(bbi_periods=bbi_periods, boll_period=boll_period,
                         boll_std=boll_std, min_days_below=min_days_below)
        self.bbi_periods = bbi_periods or [3, 6, 12, 24]
        self.boll_period = boll_period
        self.boll_std = boll_std
        self.min_days_below = min_days_below

    def compute(self, df: pd.DataFrame) -> pd.Series:
        close = df["close"]
        bbi, upper, lower = compute_bbiboll(
            close, self.bbi_periods, self.boll_period, self.boll_std
        )

        # 收盘 <= 下轨
        at_lower = close <= lower

        # 连续在下轨以下的天数（向量化累计）
        not_at_lower = ~at_lower
        groups = not_at_lower.cumsum()
        days_below = at_lower.groupby(groups).cumcount() + 1
        days_below = days_below.where(at_lower, 0)

        # 已连续 >= min_days_below 天在下轨（含当天或前一天）
        enough_days = days_below.shift(1) >= self.min_days_below

        # 当天反弹（收盘 > 昨收）
        bouncing = close > close.shift(1)

        return enough_days & bouncing

    def score(self, df: pd.DataFrame) -> pd.Series:
        """评分：跌破下轨越深 + 反弹力度越大 → 分越高"""
        close = df["close"]
        bbi, upper, lower = compute_bbiboll(
            close, self.bbi_periods, self.boll_period, self.boll_std
        )

        # 前日跌破下轨的深度（越深越好）
        prev_depth = ((lower.shift(1) - close.shift(1)) / lower.shift(1)).clip(lower=0)
        depth_score = (prev_depth / 0.05).clip(upper=1.0) * 50  # 跌破5%封顶50分

        # 当日反弹幅度
        bounce = ((close - close.shift(1)) / close.shift(1)).clip(lower=0)
        bounce_score = (bounce / 0.03).clip(upper=1.0) * 50  # 反弹3%封顶50分

        signal = self.compute(df)
        return (depth_score + bounce_score).where(signal, 0)

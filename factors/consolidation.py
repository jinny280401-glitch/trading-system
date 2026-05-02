"""
横盘因子 — 黄金坑 Gate 3

检测股票是否处于横盘筑底状态：
- 近 N 天振幅收窄（高低点差 / 低点 <= 阈值）
- 收盘价贴近均线（不是单边下跌）
- 成交量萎缩（确认是筑底而非出货）

全部使用 rolling window 向量化，O(n)
"""

import pandas as pd
import numpy as np
from .base import BaseFactor


class Consolidation(BaseFactor):
    """
    横盘震荡筑底

    参数:
        lookback_days: 回溯窗口（交易日），默认60（约3个月）
        max_amplitude: 最大振幅阈值，默认0.15（15%）
        ma_period: 均线周期，默认20
        ma_proximity: 收盘价偏离均线的最大比例，默认0.10（10%）
        volume_shrink_ratio: 近期均量/前期均量 <= 此值视为缩量，默认0.8
    """
    name = "consolidation"
    description = "横盘震荡筑底"

    def __init__(self, lookback_days: int = 60, max_amplitude: float = 0.15,
                 ma_period: int = 20, ma_proximity: float = 0.10,
                 volume_shrink_ratio: float = 0.8):
        super().__init__(
            lookback_days=lookback_days, max_amplitude=max_amplitude,
            ma_period=ma_period, ma_proximity=ma_proximity,
            volume_shrink_ratio=volume_shrink_ratio,
        )
        self.lookback_days = lookback_days
        self.max_amplitude = max_amplitude
        self.ma_period = ma_period
        self.ma_proximity = ma_proximity
        self.volume_shrink_ratio = volume_shrink_ratio

    def compute(self, df: pd.DataFrame) -> pd.Series:
        high = df["high"]
        low = df["low"]
        close = df["close"]
        volume = df["volume"]
        n = self.lookback_days

        # 1) 振幅：近 N 日 (最高 - 最低) / 最低
        rolling_high = high.rolling(n).max()
        rolling_low = low.rolling(n).min()
        amplitude = (rolling_high - rolling_low) / rolling_low.replace(0, np.nan).fillna(0)
        narrow_range = amplitude <= self.max_amplitude

        # 2) 收盘价贴近均线：|close - MA| / MA <= proximity
        ma = close.rolling(self.ma_period).mean()
        near_ma = (((close - ma).abs() / ma.replace(0, np.nan).fillna(0)) <= self.ma_proximity) | ma.replace(0, np.nan).isna()

        # 3) 缩量：近 N 日均量 / 前 N 日均量 <= ratio
        recent_vol = volume.rolling(n).mean()
        prior_vol = volume.shift(n).rolling(n).mean()
        vol_shrink = (recent_vol / prior_vol.replace(0, np.nan).fillna(0)) <= self.volume_shrink_ratio

        return narrow_range & near_ma & vol_shrink

    def score(self, df: pd.DataFrame) -> pd.Series:
        """
        评分：
        - 振幅紧度 0-40分（越窄越高）
        - 持续天数 0-30分（近 N 天满足振幅条件的天数占比）
        - 缩量程度 0-30分（量比越低越高）
        """
        high = df["high"]
        low = df["low"]
        close = df["close"]
        volume = df["volume"]
        n = self.lookback_days

        # 振幅紧度
        rolling_high = high.rolling(n).max()
        rolling_low = low.rolling(n).min()
        amplitude = (rolling_high - rolling_low) / rolling_low.replace(0, np.nan).fillna(0)
        # 振幅从 max_amplitude 到 0 映射到 0-40 分
        tightness = ((self.max_amplitude - amplitude) / self.max_amplitude).clip(lower=0, upper=1)
        tightness_score = tightness * 40

        # 持续天数：用较短窗口（20天）检测每天是否横盘，再统计近 N 天占比
        short_n = min(20, n)
        short_high = high.rolling(short_n).max()
        short_low = low.rolling(short_n).min()
        short_amp = (short_high - short_low) / short_low
        daily_flat = (short_amp <= self.max_amplitude).astype(float)
        flat_ratio = daily_flat.rolling(n).mean()
        duration_score = flat_ratio.clip(upper=1.0) * 30

        # 缩量程度
        recent_vol = volume.rolling(n).mean()
        prior_vol = volume.shift(n).rolling(n).mean()
        vol_ratio = (recent_vol / prior_vol.replace(0, np.nan).fillna(0)).clip(lower=0.2, upper=1.0)
        # 量比从 1.0 到 0.2 映射到 0-30 分
        shrink_score = ((1.0 - vol_ratio) / 0.8).clip(lower=0, upper=1) * 30

        signal = self.compute(df)
        total = tightness_score + duration_score + shrink_score
        return total.where(signal, 0).fillna(0)

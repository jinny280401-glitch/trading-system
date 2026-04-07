"""
涨停相关因子 — v2 向量化 + 修复涨停阈值

因子1: 涨停基因 — 过去N个交易日内有过涨停
因子2: 跌破涨停价 — 当前价低于最近一次涨停收盘价
"""

import pandas as pd
import numpy as np
from .base import BaseFactor


def get_limit_up_threshold(code: str) -> float:
    """
    根据股票代码判断涨停阈值

    主板(60xxxx/00xxxx): 10% → 阈值 9.8
    创业板(300xxx):      20% → 阈值 19.8
    科创板(688xxx):      20% → 阈值 19.8
    ST股:                5%  → 由调用方额外处理
    """
    if code.startswith('300') or code.startswith('688'):
        return 19.8
    return 9.8


def detect_limit_up(pct_chg: pd.Series, code: str = "", is_st: bool = False) -> pd.Series:
    """判断是否涨停"""
    if is_st:
        return pct_chg >= 4.8
    threshold = get_limit_up_threshold(code)
    return pct_chg >= threshold


class LimitUpGene(BaseFactor):
    """
    涨停基因：过去 lookback_days 内至少有一次涨停
    """
    name = "limit_up_gene"
    description = "半年内有涨停记录"

    def __init__(self, lookback_days: int = 120, code: str = "", is_st: bool = False):
        super().__init__(lookback_days=lookback_days)
        self.lookback_days = lookback_days
        self.code = code
        self.is_st = is_st

    def compute(self, df: pd.DataFrame) -> pd.Series:
        is_lu = detect_limit_up(df["pct_chg"], self.code, self.is_st)
        # rolling max: 窗口内有任何一个True就返回True
        has_gene = is_lu.rolling(window=self.lookback_days, min_periods=1).max().astype(bool)
        return has_gene

    def score(self, df: pd.DataFrame) -> pd.Series:
        """评分：涨停越近分越高，涨停次数越多分越高"""
        is_lu = detect_limit_up(df["pct_chg"], self.code, self.is_st)

        # 窗口内涨停次数（0~N）→ 归一化到 0~50 分
        lu_count = is_lu.astype(float).rolling(window=self.lookback_days, min_periods=1).sum()
        count_score = (lu_count.clip(upper=5) / 5) * 50  # 5次封顶

        # 距离最近涨停的天数 → 越近分越高（0~50分）
        # 用累计非涨停天数计算距离
        groups = is_lu.cumsum()
        dist = is_lu.groupby(groups).cumcount()  # 距上次涨停的天数
        recency_score = ((self.lookback_days - dist.clip(upper=self.lookback_days))
                         / self.lookback_days * 50)

        total = count_score + recency_score
        # 无涨停基因的设为0
        has_gene = self.compute(df)
        return total.where(has_gene, 0)


class BelowLimitUpPrice(BaseFactor):
    """
    跌破涨停价：当前收盘价 < 最近一次涨停的收盘价

    v2: 用 ffill 向量化，O(n) 替代 O(n²)
    """
    name = "below_limit_up_price"
    description = "当前价低于最近涨停价"

    def __init__(self, lookback_days: int = 120, code: str = "", is_st: bool = False):
        super().__init__(lookback_days=lookback_days)
        self.lookback_days = lookback_days
        self.code = code
        self.is_st = is_st

    def compute(self, df: pd.DataFrame) -> pd.Series:
        is_lu = detect_limit_up(df["pct_chg"], self.code, self.is_st)
        close = df["close"]

        # 涨停日的收盘价，非涨停日为NaN，然后前向填充
        limit_up_price = close.where(is_lu).ffill()

        # 距最近涨停的天数（向量化）
        # 每次涨停时 cumsum+1 形成新分组，组内 cumcount = 距该涨停天数
        lu_groups = is_lu.cumsum()
        days_since_lu = lu_groups.groupby(lu_groups).cumcount()
        # 首次涨停前的行 lu_groups==0，标记为超窗口
        days_since_lu = days_since_lu.where(lu_groups > 0, self.lookback_days + 1)

        in_window = (days_since_lu > 0) & (days_since_lu <= self.lookback_days)
        result = (close < limit_up_price) & in_window
        return result

    def score(self, df: pd.DataFrame) -> pd.Series:
        """评分：跌破幅度越大分越高（洗盘越充分）"""
        is_lu = detect_limit_up(df["pct_chg"], self.code, self.is_st)
        close = df["close"]
        limit_up_price = close.where(is_lu).ffill()

        # 跌破幅度 = (涨停价 - 当前价) / 涨停价
        # fillna(0) 防止无涨停历史时除零
        discount = ((limit_up_price - close) / limit_up_price.replace(0, np.nan)).fillna(0).clip(lower=0)
        # 跌破 0~20% 映射到 0~100 分
        score = (discount / 0.20).clip(upper=1.0) * 100

        signal = self.compute(df)
        return score.where(signal, 0).fillna(0)

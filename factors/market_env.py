"""
市场环境过滤 — 大盘在20日均线以下时不开仓（巴菲特建议）
"""

import pandas as pd


class MarketEnvironment:
    """沪深300指数均线过滤"""

    def __init__(self, ma_period: int = 20):
        self.ma_period = ma_period
        self._index_df = None

    def load(self, provider, start_date: str, end_date: str):
        """加载沪深300指数数据"""
        self._index_df = provider.get_index_daily("sh.000300", start_date, end_date)
        if not self._index_df.empty:
            self._index_df["ma"] = self._index_df["close"].rolling(self.ma_period).mean()

    def is_safe(self, date) -> bool:
        """大盘是否在均线以上（适合开仓）"""
        if self._index_df is None or self._index_df.empty:
            return True  # 数据不可用时默认放行

        date = pd.Timestamp(date)
        mask = self._index_df["date"] <= date
        if not mask.any():
            return True

        row = self._index_df[mask].iloc[-1]
        if pd.isna(row.get("ma")):
            return True
        return row["close"] > row["ma"]

    def get_status(self) -> dict:
        """获取当前市场状态"""
        if self._index_df is None or self._index_df.empty:
            return {"status": "未知", "safe": True}

        row = self._index_df.iloc[-1]
        ma = row.get("ma")
        close = row["close"]
        if pd.isna(ma):
            return {"status": "数据不足", "safe": True}

        above = close > ma
        return {
            "status": "均线上方（安全）" if above else "均线下方（谨慎）",
            "safe": above,
            "index_close": close,
            "ma20": ma,
            "diff_pct": (close - ma) / ma * 100,
        }

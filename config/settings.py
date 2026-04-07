"""全局配置"""

# 数据源配置
DATA_PROVIDER = "akshare"  # akshare(免费) | tushare(需Token)
TUSHARE_TOKEN = ""  # 如用 tushare 填这里

# 市场配置
MARKET = "A股"
# 股票池：None = 全市场扫描
STOCK_POOL = None

# 因子默认参数
FACTORS = {
    # 涨停基因：回溯天数
    "limit_up_gene": {
        "lookback_days": 120,  # 半年约 120 个交易日
    },
    # 跌破涨停价
    "below_limit_up_price": {
        "lookback_days": 120,
    },
    # 连跌缩量
    "consecutive_decline": {
        "min_days": 3,         # 最少连跌天数
        "max_days": 7,         # 最多连跌天数
        "volume_shrink": True, # 要求成交量逐日缩小
    },
    # BBIBOLL — 通达信标准参数 N=11, M=6
    "bbiboll": {
        "bbi_periods": [3, 6, 12, 24],
        "boll_period": 11,
        "boll_std": 6,
        "min_days_below": 1,
    },
    # 横盘震荡筑底
    "consolidation": {
        "lookback_days": 60,       # 约3个月
        "max_amplitude": 0.15,     # 振幅 <= 15%
        "ma_period": 20,
        "ma_proximity": 0.10,      # 收盘价偏离20日均线 <= 10%
        "volume_shrink_ratio": 0.8, # 近期均量/前期均量 <= 0.8
    },
}

# 信号合成：黄金坑四重门
SIGNAL_COMBO = [
    "limit_up_gene",           # Gate 1: 有涨停基因
    "below_limit_up_price",    # Gate 2: 跌破涨停价（挖坑）
    "consolidation",           # Gate 3: 横盘筑底
    "bbiboll",                 # Gate 4: BBIBOLL下轨反弹（入场信号）
]

# 因子评分权重（综合评分 = 加权平均）
FACTOR_WEIGHTS = {
    "limit_up_gene": 0.8,        # 涨停基因（二元筛选为主）
    "below_limit_up_price": 1.5, # 跌破涨停价（核心因子，折价越深潜力越大）
    "consolidation": 1.2,        # 横盘筑底（底部越扎实越可靠）
    "bbiboll": 1.0,              # BBIBOLL下轨反弹（入场时机）
}

# 回测配置
BACKTEST = {
    "start_date": "2024-01-01",
    "end_date": "2025-04-03",
    "initial_capital": 1_000_000,
    "commission_rate": 0.0003,  # 万三
    "slippage": 0.001,          # 0.1%
    "stamp_tax": 0.0005,        # 印花税 万五（卖出）
    "hold_days": 5,             # 默认持仓天数
    "stop_loss": -0.05,         # 止损线 -5%
    "take_profit": 0.10,        # 止盈线 +10%
    "max_positions": 5,         # 最大同时持仓数
}

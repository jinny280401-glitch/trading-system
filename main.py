"""
交易系统 v2 入口

用法:
    # 单股调试 — 看因子逐日信号
    python main.py debug 601127

    # 全市场扫描（两阶段过滤）
    python main.py scan

    # 单股回测
    python main.py backtest 601127

    # 多股组合回测（从缓存中选取有信号的股票）
    python main.py backtest-portfolio

    # 预热缓存（首次使用，约5分钟）
    python main.py warmup
"""

import sys
import time
import pandas as pd
from data.provider import DataProvider
from factors.limit_up import LimitUpGene, BelowLimitUpPrice
from factors.volume import ConsecutiveDecline
from factors.bbiboll import BBIBOLLLowerBounce
from factors.consolidation import Consolidation
from engine.scanner import Scanner
from backtest.backtester import Backtester
from config.settings import FACTORS, SIGNAL_COMBO, FACTOR_WEIGHTS, BACKTEST


def build_factors(code: str = "", is_st: bool = False):
    """根据配置构建因子列表，并应用权重"""
    factor_map = {
        "limit_up_gene": lambda: LimitUpGene(
            lookback_days=FACTORS["limit_up_gene"]["lookback_days"],
            code=code, is_st=is_st,
        ),
        "below_limit_up_price": lambda: BelowLimitUpPrice(
            lookback_days=FACTORS["below_limit_up_price"]["lookback_days"],
            code=code, is_st=is_st,
        ),
        "consecutive_decline": lambda: ConsecutiveDecline(
            min_days=FACTORS["consecutive_decline"]["min_days"],
            max_days=FACTORS["consecutive_decline"]["max_days"],
            volume_shrink=FACTORS["consecutive_decline"]["volume_shrink"],
        ),
        "consolidation": lambda: Consolidation(
            lookback_days=FACTORS["consolidation"]["lookback_days"],
            max_amplitude=FACTORS["consolidation"]["max_amplitude"],
            ma_period=FACTORS["consolidation"]["ma_period"],
            ma_proximity=FACTORS["consolidation"]["ma_proximity"],
            volume_shrink_ratio=FACTORS["consolidation"]["volume_shrink_ratio"],
        ),
        "bbiboll": lambda: BBIBOLLLowerBounce(
            bbi_periods=FACTORS["bbiboll"]["bbi_periods"],
            boll_period=FACTORS["bbiboll"]["boll_period"],
            boll_std=FACTORS["bbiboll"]["boll_std"],
            min_days_below=FACTORS["bbiboll"]["min_days_below"],
        ),
    }
    factors = []
    for name in SIGNAL_COMBO:
        if name in factor_map:
            f = factor_map[name]()
            f.weight = FACTOR_WEIGHTS.get(name, 1.0)
            factors.append(f)
    return factors


def cmd_debug(code: str):
    """单股调试"""
    provider = DataProvider()
    factors = build_factors(code=code)
    scanner = Scanner(provider, factors)

    print(f"\n调试股票: {code}")
    print(f"启用因子: {[f.name for f in factors]}\n")

    df = scanner.scan_single(code, "2024-06-01", "2025-04-03")
    if df.empty:
        print("无数据")
        return

    factor_cols = [f.name for f in factors]
    display_cols = ["date", "close", "pct_chg", "volume"] + factor_cols + ["signal"]
    display_cols = [c for c in display_cols if c in df.columns]

    # 计算评分
    for factor in factors:
        df[f"{factor.name}_score"] = factor.score(df)
    score_cols = [f"{f.name}_score" for f in factors]
    weights = {f.name: f.weight for f in factors}
    total_w = sum(weights.values())
    df["composite_score"] = sum(
        df[f"{name}_score"] * weights[name] for name in weights
    ) / total_w

    signal_days = df[df["signal"]]
    recent = df.tail(10)

    score_display = score_cols + ["composite_score"]
    all_display = display_cols + score_display
    all_display = [c for c in all_display if c in df.columns]

    print("=== 命中信号的交易日 ===")
    if signal_days.empty:
        print("(无)")
    else:
        print(signal_days[all_display].to_string(index=False))

    print(f"\n=== 最近 10 个交易日 ===")
    print(recent[display_cols].to_string(index=False))


def cmd_scan(scan_date: str = None):
    """全市场两阶段扫描"""
    provider = DataProvider()
    factors = build_factors()
    scanner = Scanner(provider, factors)

    t0 = time.time()
    result = scanner.scan(scan_date)
    elapsed = time.time() - t0

    hits = result["hits"]
    env = result["market_env"]
    stats = result["stats"]

    print(f"\n耗时: {elapsed:.1f}秒")
    print(f"市场环境: {env.get('status', '未知')}")

    if not env.get('safe', True):
        print("!! 大盘在20日均线下方，建议谨慎操作 !!")

    if hits.empty:
        print("今日无命中")
    else:
        print(f"\n=== 命中 {len(hits)} 只股票 ===")
        print(hits.to_string(index=False))
        filename = f"scan_result_{scan_date or 'latest'}.csv"
        hits.to_csv(filename, index=False, encoding="utf-8-sig")
        print(f"\n结果已保存: {filename}")


def cmd_backtest(codes_str: str):
    """回测"""
    codes = [c.strip() for c in codes_str.split(",")]
    provider = DataProvider()
    factors = build_factors(code=codes[0] if len(codes) == 1 else "")

    bt = Backtester(
        provider=provider,
        factors=factors,
        initial_capital=BACKTEST["initial_capital"],
        commission_rate=BACKTEST["commission_rate"],
        stamp_tax=BACKTEST["stamp_tax"],
        slippage=BACKTEST["slippage"],
        hold_days=BACKTEST["hold_days"],
        stop_loss=BACKTEST["stop_loss"],
        take_profit=BACKTEST["take_profit"],
        max_positions=BACKTEST["max_positions"],
    )

    start = BACKTEST["start_date"]
    end = BACKTEST["end_date"]

    print(f"\n回测: {codes}")
    print(f"区间: {start} ~ {end}")
    print(f"因子: {[f.name for f in factors]}\n")

    result = bt.run(codes[0], start, end)
    print(result.summary())

    if not result.trades.empty:
        print("\n=== 交易明细 ===")
        print(result.trades.to_string(index=False))


def cmd_backtest_portfolio():
    """多股组合回测：从缓存中读取所有股票，跑组合回测"""
    provider = DataProvider()
    factors = build_factors()

    # 从缓存目录获取已有股票列表
    import os
    cache_dir = os.path.join(os.path.dirname(__file__), "data", "cache")
    if not os.path.isdir(cache_dir):
        print("缓存目录不存在，请先运行 warmup")
        return

    codes = [f.replace(".parquet", "") for f in os.listdir(cache_dir) if f.endswith(".parquet")]
    if not codes:
        print("缓存为空，请先运行 warmup")
        return

    bt = Backtester(
        provider=provider,
        factors=factors,
        initial_capital=BACKTEST["initial_capital"],
        commission_rate=BACKTEST["commission_rate"],
        stamp_tax=BACKTEST["stamp_tax"],
        slippage=BACKTEST["slippage"],
        hold_days=BACKTEST["hold_days"],
        stop_loss=BACKTEST["stop_loss"],
        take_profit=BACKTEST["take_profit"],
        max_positions=BACKTEST["max_positions"],
    )

    start = BACKTEST["start_date"]
    end = BACKTEST["end_date"]

    print(f"\n组合回测: {len(codes)} 只股票")
    print(f"区间: {start} ~ {end}")
    print(f"因子: {[f.name for f in factors]}\n")

    result = bt.run_portfolio(codes, start, end)
    print(result.summary())

    if not result.trades.empty:
        print(f"\n=== 交易明细（共 {len(result.trades)} 笔）===")
        print(result.trades.to_string(index=False))
        result.trades.to_csv("portfolio_trades.csv", index=False, encoding="utf-8-sig")
        print("\n交易明细已保存: portfolio_trades.csv")


def cmd_warmup():
    """预热缓存：批量下载历史数据"""
    provider = DataProvider()
    print("获取股票列表...")
    snapshot = provider.get_market_snapshot()
    if snapshot.empty:
        print("获取失败")
        return

    codes = snapshot[
        ~snapshot['is_st']
        & ~snapshot['code'].str.startswith('8')
        & (snapshot['market_cap'].notna())
        & (snapshot['market_cap'] > 2_000_000_000)
    ]['code'].tolist()

    print(f"开始预热 {len(codes)} 只股票的历史数据...")
    t0 = time.time()
    provider.batch_load(codes, "2024-01-01", "2025-04-03")
    print(f"预热完成！耗时 {time.time()-t0:.0f}秒")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "debug":
        cmd_debug(sys.argv[2] if len(sys.argv) > 2 else "601127")
    elif cmd == "scan":
        cmd_scan(sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == "backtest":
        cmd_backtest(sys.argv[2] if len(sys.argv) > 2 else "601127")
    elif cmd == "backtest-portfolio":
        cmd_backtest_portfolio()
    elif cmd == "warmup":
        cmd_warmup()
    else:
        print(f"未知命令: {cmd}")
        print(__doc__)

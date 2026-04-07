"""
回测引擎 — 信号触发后模拟交易，计算收益率等核心指标

v2: 修复止损用close的bug，改用low/high判断；增加基准对比、Sharpe Ratio
"""

import pandas as pd
import numpy as np
from typing import List
from data.provider import DataProvider
from factors.base import BaseFactor


class BacktestResult:
    """回测结果"""
    def __init__(self, trades: pd.DataFrame, equity_curve: pd.DataFrame, stats: dict):
        self.trades = trades
        self.equity_curve = equity_curve
        self.stats = stats

    def summary(self) -> str:
        s = self.stats
        lines = [
            "=" * 55,
            "回 测 结 果",
            "=" * 55,
            f"回测区间:        {s['start_date']} ~ {s['end_date']}",
            f"初始资金:        ¥{s['initial_capital']:,.0f}",
            f"",
            f"总交易次数:      {s['total_trades']}",
            f"盈利次数:        {s['win_trades']}",
            f"亏损次数:        {s['lose_trades']}",
            f"胜率:            {s['win_rate']:.1%}",
            f"",
            f"--- 策略表现 ---",
            f"总收益率:        {s['total_return']:.2%}",
            f"年化收益率:      {s['annual_return']:.2%}",
            f"最大回撤:        {s['max_drawdown']:.2%}",
            f"Calmar比率:      {s['calmar_ratio']:.2f}",
            f"Sharpe比率:      {s['sharpe_ratio']:.2f}",
            f"",
            f"--- 基准对比（沪深300）---",
            f"基准收益率:      {s['benchmark_return']:.2%}",
            f"超额收益:        {s['excess_return']:.2%}",
            f"",
            f"--- 交易细节 ---",
            f"平均持仓天数:    {s['avg_hold_days']:.1f}",
            f"平均单笔收益:    {s['avg_return']:.2%}",
            f"最大单笔盈利:    {s['max_win']:.2%}",
            f"最大单笔亏损:    {s['max_loss']:.2%}",
            f"盈亏比:          {s['profit_loss_ratio']:.2f}",
            f"",
            f"期末资金:        ¥{s['final_capital']:,.0f}",
        ]

        # 统计意义警告
        if s['total_trades'] < 30:
            lines.append("")
            lines.append(f"!! 警告: 仅 {s['total_trades']} 笔交易，统计意义不足（建议≥30笔）!!")

        lines.append("=" * 55)
        return "\n".join(lines)


class Backtester:
    """
    回测引擎

    策略逻辑：
    - 买入：信号日次日开盘买入（T+1）
    - 卖出：持仓 hold_days 天后卖出 / 止损 / 止盈
    - 仓位：等额分仓
    """

    def __init__(
        self,
        provider: DataProvider,
        factors: List[BaseFactor],
        initial_capital: float = 1_000_000,
        commission_rate: float = 0.0003,  # 万三
        stamp_tax: float = 0.0005,         # 印花税万五（卖出）
        slippage: float = 0.001,            # 滑点 0.1%
        hold_days: int = 5,                 # 默认持仓天数
        stop_loss: float = -0.05,           # 止损 -5%
        take_profit: float = 0.10,          # 止盈 +10%
        max_positions: int = 5,             # 最大持仓数
    ):
        self.provider = provider
        self.factors = factors
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.stamp_tax = stamp_tax
        self.slippage = slippage
        self.hold_days = hold_days
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.max_positions = max_positions

    def run(self, code: str, start_date: str, end_date: str) -> BacktestResult:
        """对单只股票回测"""
        df = self.provider.get_daily(code, start_date, end_date)
        if df.empty or len(df) < 30:
            return self._empty_result(start_date, end_date)

        # 计算因子信号
        for factor in self.factors:
            df[factor.name] = factor.compute(df)
        factor_cols = [f.name for f in self.factors]
        df["signal"] = df[factor_cols].all(axis=1)

        # 模拟交易
        trades = []
        capital = self.initial_capital
        equity_records = []

        i = 0
        while i < len(df):
            row = df.iloc[i]
            equity_records.append({"date": row["date"], "equity": capital})

            if row["signal"] and i + 1 < len(df):
                # T+1 买入
                buy_row = df.iloc[i + 1]
                buy_price = buy_row["open"] * (1 + self.slippage)
                shares = int((capital / self.max_positions) / (buy_price * 100)) * 100
                if shares < 100:
                    i += 1
                    continue

                buy_cost = shares * buy_price * (1 + self.commission_rate)

                # 持仓期间寻找卖出点
                # v2修复：用 low 判断止损触发，high 判断止盈触发
                sell_idx = None
                sell_reason = ""
                actual_sell_price = None
                stop_loss_price = buy_price * (1 + self.stop_loss)
                take_profit_price = buy_price * (1 + self.take_profit)

                for j in range(i + 2, min(i + 2 + self.hold_days, len(df))):
                    hold_row = df.iloc[j]
                    # 盘中最低价触及止损线 → 按止损价成交
                    if hold_row["low"] <= stop_loss_price:
                        sell_idx = j
                        sell_reason = "止损"
                        actual_sell_price = stop_loss_price
                        break
                    # 盘中最高价触及止盈线 → 按止盈价成交
                    if hold_row["high"] >= take_profit_price:
                        sell_idx = j
                        sell_reason = "止盈"
                        actual_sell_price = take_profit_price
                        break

                if sell_idx is None:
                    sell_idx = min(i + 1 + self.hold_days, len(df) - 1)
                    sell_reason = "到期"

                sell_row = df.iloc[sell_idx]
                if actual_sell_price is not None:
                    sell_price = actual_sell_price  # 止损/止盈按触发价成交
                else:
                    sell_price = sell_row["close"] * (1 - self.slippage)  # 到期按收盘价
                sell_income = shares * sell_price * (1 - self.commission_rate - self.stamp_tax)

                pnl = sell_income - buy_cost
                ret = pnl / buy_cost
                capital += pnl
                hold_days_actual = sell_idx - (i + 1)

                trades.append({
                    "buy_date": buy_row["date"],
                    "buy_price": buy_price,
                    "sell_date": sell_row["date"],
                    "sell_price": sell_price,
                    "shares": shares,
                    "pnl": pnl,
                    "return": ret,
                    "hold_days": hold_days_actual,
                    "sell_reason": sell_reason,
                })

                # 跳过持仓期间
                i = sell_idx + 1
                continue

            i += 1

        trades_df = pd.DataFrame(trades)
        equity_df = pd.DataFrame(equity_records)
        stats = self._calc_stats(trades_df, equity_df, start_date, end_date, capital)

        return BacktestResult(trades_df, equity_df, stats)

    def run_portfolio(self, codes: List[str], start_date: str, end_date: str) -> BacktestResult:
        """
        多股票组合回测

        流程：
        1. 扫描所有股票生成信号表（含后续日线数据）
        2. 按日期排序，逐信号模拟交易
        3. 持仓期间逐日检查止损/止盈（用 low/high）
        """
        import copy

        # ── 阶段1: 扫描信号 ──
        all_signals = []
        print(f"正在计算 {len(codes)} 只股票的因子信号...")

        for idx, code in enumerate(codes):
            if idx % 50 == 0:
                print(f"  进度: {idx}/{len(codes)}")
            df = self.provider.get_daily(code, start_date, end_date)
            if df.empty or len(df) < 30:
                continue

            local_factors = [copy.copy(f) for f in self.factors]
            for factor in local_factors:
                if hasattr(factor, 'code'):
                    factor.code = code
                df[factor.name] = factor.compute(df)
            factor_cols = [f.name for f in local_factors]
            df["signal"] = df[factor_cols].all(axis=1)

            signal_indices = df.index[df["signal"]]
            for si in signal_indices:
                pos = df.index.get_loc(si)
                if pos + 1 >= len(df):
                    continue
                # 保存信号日 + 之后 hold_days 天的日线数据供止损/止盈检查
                future_slice = df.iloc[pos + 1: pos + 2 + self.hold_days].copy()
                all_signals.append({
                    "date": df.iloc[pos]["date"],
                    "code": code,
                    "next_open": df.iloc[pos + 1]["open"],
                    "future_df": future_slice,
                })

        if not all_signals:
            print("未发现任何信号")
            return self._empty_result(start_date, end_date)

        # 按信号日期排序
        all_signals.sort(key=lambda x: x["date"])
        print(f"共发现 {len(all_signals)} 个信号")

        # ── 阶段2: 模拟组合交易 ──
        capital = self.initial_capital
        positions = []
        trades = []
        equity_records = [{"date": pd.Timestamp(start_date), "equity": capital}]

        for sig in all_signals:
            sig_date = sig["date"]

            # 清算已完成的持仓（止损/止盈/到期）
            for pos in positions:
                if pos["closed"]:
                    continue
                fut = pos["future_df"]
                buy_price = pos["buy_price"]
                stop_loss_price = buy_price * (1 + self.stop_loss)
                take_profit_price = buy_price * (1 + self.take_profit)

                for j in range(len(fut)):
                    row = fut.iloc[j]
                    if pd.Timestamp(row["date"]) > pd.Timestamp(sig_date):
                        break  # 只清算到当前信号日

                    sell_price = None
                    sell_reason = ""
                    # 用 low 判断止损
                    if row["low"] <= stop_loss_price:
                        sell_price = stop_loss_price
                        sell_reason = "止损"
                    # 用 high 判断止盈
                    elif row["high"] >= take_profit_price:
                        sell_price = take_profit_price
                        sell_reason = "止盈"
                    # 到期：已遍历到 fut 的最后一天
                    elif j >= self.hold_days or j == len(fut) - 1:
                        sell_price = row["close"] * (1 - self.slippage)
                        sell_reason = "到期"

                    if sell_price is not None:
                        sell_income = pos["shares"] * sell_price * (1 - self.commission_rate - self.stamp_tax)
                        pnl = sell_income - pos["cost"]
                        capital += pnl
                        trades.append({
                            "code": pos["code"],
                            "buy_date": pos["buy_date"],
                            "buy_price": buy_price,
                            "sell_date": row["date"],
                            "sell_price": sell_price,
                            "shares": pos["shares"],
                            "pnl": pnl,
                            "return": pnl / pos["cost"],
                            "hold_days": j + 1,
                            "sell_reason": sell_reason,
                        })
                        pos["closed"] = True
                        break

            positions = [p for p in positions if not p["closed"]]

            # 是否有空闲仓位
            if len(positions) >= self.max_positions:
                continue
            if pd.isna(sig["next_open"]):
                continue

            # 买入
            buy_price = sig["next_open"] * (1 + self.slippage)
            position_size = capital / self.max_positions
            shares = int(position_size / (buy_price * 100)) * 100
            if shares < 100:
                continue
            cost = shares * buy_price * (1 + self.commission_rate)

            positions.append({
                "code": sig["code"],
                "buy_date": sig["date"],
                "buy_price": buy_price,
                "shares": shares,
                "cost": cost,
                "future_df": sig["future_df"],
                "closed": False,
            })
            equity_records.append({"date": sig_date, "equity": capital})

        # 清算剩余未平仓
        for pos in positions:
            if pos["closed"]:
                continue
            fut = pos["future_df"]
            buy_price = pos["buy_price"]
            stop_loss_price = buy_price * (1 + self.stop_loss)
            take_profit_price = buy_price * (1 + self.take_profit)

            for j in range(len(fut)):
                row = fut.iloc[j]
                if row["low"] <= stop_loss_price:
                    sell_price = stop_loss_price
                    sell_reason = "止损"
                    break
                elif row["high"] >= take_profit_price:
                    sell_price = take_profit_price
                    sell_reason = "止盈"
                    break
            else:
                # 全部持仓期内未触发，按最后一天收盘价卖出
                row = fut.iloc[-1] if len(fut) > 0 else None
                if row is not None:
                    sell_price = row["close"] * (1 - self.slippage)
                    sell_reason = "到期"
                else:
                    sell_price = buy_price
                    sell_reason = "到期"

            sell_income = pos["shares"] * sell_price * (1 - self.commission_rate - self.stamp_tax)
            pnl = sell_income - pos["cost"]
            capital += pnl
            trades.append({
                "code": pos["code"],
                "buy_date": pos["buy_date"],
                "buy_price": buy_price,
                "sell_date": row["date"] if row is not None else pos["buy_date"],
                "sell_price": sell_price,
                "shares": pos["shares"],
                "pnl": pnl,
                "return": pnl / pos["cost"],
                "hold_days": len(fut),
                "sell_reason": sell_reason,
            })

        trades_df = pd.DataFrame(trades)
        equity_df = pd.DataFrame(equity_records)
        stats = self._calc_stats(trades_df, equity_df, start_date, end_date, capital)
        return BacktestResult(trades_df, equity_df, stats)

    def _get_benchmark_return(self, start_date: str, end_date: str) -> float:
        """获取沪深300同期收益率作为基准"""
        try:
            index_df = self.provider.get_index_daily("sh.000300", start_date, end_date)
            if index_df.empty or len(index_df) < 2:
                return 0.0
            return (index_df["close"].iloc[-1] - index_df["close"].iloc[0]) / index_df["close"].iloc[0]
        except Exception:
            return 0.0

    def _calc_stats(self, trades_df, equity_df, start_date, end_date, final_capital) -> dict:
        """计算回测统计指标（含基准对比、Sharpe Ratio）"""
        total_trades = len(trades_df)
        benchmark_return = self._get_benchmark_return(start_date, end_date)

        empty_stats = {
            "start_date": start_date, "end_date": end_date,
            "initial_capital": self.initial_capital,
            "final_capital": self.initial_capital,
            "total_trades": 0, "win_trades": 0, "lose_trades": 0,
            "win_rate": 0, "total_return": 0, "annual_return": 0,
            "max_drawdown": 0, "calmar_ratio": 0, "sharpe_ratio": 0,
            "benchmark_return": benchmark_return, "excess_return": -benchmark_return,
            "avg_hold_days": 0, "avg_return": 0,
            "max_win": 0, "max_loss": 0, "profit_loss_ratio": 0,
        }

        if total_trades == 0:
            return empty_stats

        win_trades = len(trades_df[trades_df["return"] > 0])
        lose_trades = len(trades_df[trades_df["return"] < 0])
        win_rate = win_trades / total_trades if total_trades > 0 else 0

        total_return = (final_capital - self.initial_capital) / self.initial_capital
        days = (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days
        annual_return = (1 + total_return) ** (365 / max(days, 1)) - 1

        # 超额收益
        excess_return = total_return - benchmark_return

        # Sharpe Ratio（用每笔交易收益率近似）
        if total_trades >= 2:
            trade_returns = trades_df["return"]
            # 年化：假设平均持仓天数，换算年化交易频率
            avg_hold = trades_df["hold_days"].mean() if "hold_days" in trades_df else 5
            trades_per_year = 252 / max(avg_hold, 1)
            excess_per_trade = trade_returns.mean()  # 简化：无风险利率≈0
            std_per_trade = trade_returns.std()
            sharpe_ratio = (excess_per_trade * np.sqrt(trades_per_year)) / std_per_trade if std_per_trade > 0 else 0
        else:
            sharpe_ratio = 0

        # 最大回撤
        if not equity_df.empty and len(equity_df) > 1:
            eq = equity_df["equity"]
            peak = eq.cummax()
            drawdown = (eq - peak) / peak
            max_drawdown = drawdown.min()
        else:
            max_drawdown = 0

        calmar_ratio = abs(annual_return / max_drawdown) if max_drawdown != 0 else 0

        avg_return = trades_df["return"].mean()
        avg_hold_days = trades_df["hold_days"].mean() if "hold_days" in trades_df else 0
        max_win = trades_df["return"].max()
        max_loss = trades_df["return"].min()

        avg_win = trades_df[trades_df["return"] > 0]["return"].mean() if win_trades > 0 else 0
        avg_loss = abs(trades_df[trades_df["return"] < 0]["return"].mean()) if lose_trades > 0 else 1
        profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else float("inf")

        return {
            "start_date": start_date,
            "end_date": end_date,
            "initial_capital": self.initial_capital,
            "final_capital": final_capital,
            "total_trades": total_trades,
            "win_trades": win_trades,
            "lose_trades": lose_trades,
            "win_rate": win_rate,
            "total_return": total_return,
            "annual_return": annual_return,
            "max_drawdown": max_drawdown,
            "calmar_ratio": calmar_ratio,
            "sharpe_ratio": sharpe_ratio,
            "benchmark_return": benchmark_return,
            "excess_return": excess_return,
            "avg_hold_days": avg_hold_days,
            "avg_return": avg_return,
            "max_win": max_win,
            "max_loss": max_loss,
            "profit_loss_ratio": profit_loss_ratio,
        }

    def _empty_result(self, start_date, end_date):
        return BacktestResult(
            pd.DataFrame(), pd.DataFrame(),
            self._calc_stats(pd.DataFrame(), pd.DataFrame(), start_date, end_date, self.initial_capital)
        )

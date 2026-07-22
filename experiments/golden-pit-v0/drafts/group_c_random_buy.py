# ⛔ DRAFT / NOT APPROVED — 2026-07-22
# G 裁定: Implementation HOLD. 实验矩阵待 v0.1 Spec 通过后重写.
# ============================================================
# Golden Pit Simulation Experiment v0 — Group C (随机买入对照) [DRAFT]
# 相同股票池、相同日期、相同持有周期，随机选 N 只买入
# 回测频率: 日线
# ============================================================

from jqdata import *
import numpy as np
import random

# ---------- 参数 ----------

INDEX_POOL = ['000300.XSHG', '000905.XSHG']
MIN_LIST_DAYS = 120
MIN_DAILY_AMOUNT = 1e8

POSITION_PCT = 0.10
MAX_POSITIONS = 5
MAX_TOTAL_PCT = 0.50
MAX_SAME_INDUSTRY = 2

MAX_HOLD_DAYS = 10
TAKE_PROFIT = 0.12
STOP_LOSS = -0.06


def initialize(context):
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)
    set_order_cost(OrderCost(
        open_tax=0,
        close_tax=0.0005,
        open_commission=0.0003,
        close_commission=0.0003,
        min_commission=5
    ), type='stock')
    set_slippage(FixedSlippage(0.001))

    g.watchlist = {}
    g.random.seed(42)  # 固定种子，保证可复现

    # 09:31 随机选股买入 → 14:50 到期退出
    run_daily(random_buy, time='09:31')
    run_daily(check_exits, time='14:50')


def get_stock_pool(context):
    """同 Group A/B"""
    stocks = []
    for idx in INDEX_POOL:
        stocks.extend(get_index_stocks(idx))
    stocks = list(set(stocks))

    current_data = get_current_data()
    valid = []
    for s in stocks:
        if s not in current_data:
            continue
        cd = current_data[s]
        if cd.paused or cd.is_st:
            continue
        info = get_security_info(s)
        if info is None:
            continue
        days_since_list = (context.current_dt.date() - info.start_date).days
        if days_since_list < MIN_LIST_DAYS:
            continue
        valid.append(s)

    # 成交额过滤
    if valid:
        df = get_price(valid, end_date=context.previous_date, count=20,
                       frequency='daily', fields=['money'],
                       skip_paused=False, fq=None)
        avg_money = df['money'].mean()
        valid = [s for s in valid if s in avg_money.index and avg_money[s] >= MIN_DAILY_AMOUNT]

    return valid


def random_buy(context):
    """09:31 — 从标的池随机选股买入，持有 MAX_HOLD_DAYS 退出"""

    active_positions = [p for p, pos in context.portfolio.positions.items()
                        if pos.total_amount > 0]

    if len(active_positions) >= MAX_POSITIONS:
        return

    total_pct = sum(pos.value for pos in context.portfolio.positions.values()) / \
                context.portfolio.portfolio_value
    if total_pct >= MAX_TOTAL_PCT:
        return

    # 只在持仓不足时补仓
    slots = MAX_POSITIONS - len(active_positions)
    if slots <= 0:
        return

    pool = get_stock_pool(context)
    if not pool:
        return

    # 排除已持有
    available = [s for s in pool if s not in active_positions]
    if not available:
        return

    # 行业计数
    industry_count = {}
    for p in active_positions:
        try:
            ind = get_industry(p)
            if ind and 'sw_l1' in ind:
                code = ind['sw_l1']['industry_code']
                industry_count[code] = industry_count.get(code, 0) + 1
        except Exception:
            pass

    # 随机选 slots 只
    random.shuffle(available)
    current_data = get_current_data()
    cash_per_stock = context.portfolio.portfolio_value * POSITION_PCT

    bought = 0
    for s in available:
        if bought >= slots:
            break

        cd = current_data.get(s)
        if cd is None or cd.paused or cd.is_st:
            continue
        if cd.high_limit and cd.last_price >= cd.high_limit:
            continue
        if cd.low_limit and cd.last_price <= cd.low_limit:
            continue

        try:
            ind = get_industry(s)
            if ind and 'sw_l1' in ind:
                code = ind['sw_l1']['industry_code']
                if industry_count.get(code, 0) >= MAX_SAME_INDUSTRY:
                    continue
        except Exception:
            pass

        available_cash = min(cash_per_stock, context.portfolio.cash * 0.5)
        if available_cash < cd.last_price * 100:
            continue

        order_value(s, available_cash)
        active_positions.append(s)

        try:
            ind = get_industry(s)
            ind_code = ind['sw_l1']['industry_code'] if ind and 'sw_l1' in ind else 'unknown'
        except Exception:
            ind_code = 'unknown'

        g.watchlist[s] = {
            'entry_price': cd.last_price,
            'entry_date': context.current_dt.date(),
            'industry': ind_code,
        }
        bought += 1


def check_exits(context):
    """14:50 — 到期或止盈止损退出"""

    active = [s for s, pos in context.portfolio.positions.items()
              if pos.total_amount > 0 and s in g.watchlist]

    if not active:
        return

    current_data = get_current_data()

    for s in active:
        if s not in current_data:
            continue

        cd = current_data[s]
        entry = g.watchlist[s]
        entry_price = entry['entry_price']
        hold_days = (context.current_dt.date() - entry['entry_date']).days

        sell_reason = None
        current_price = cd.last_price
        profit_pct = (current_price - entry_price) / entry_price

        if cd.paused:
            continue
        if cd.low_limit and current_price <= cd.low_limit:
            continue

        # 止损
        if profit_pct <= STOP_LOSS:
            sell_reason = '止损'
        # 止盈
        elif profit_pct >= TAKE_PROFIT:
            sell_reason = '止盈'
        # 时间退出
        elif hold_days >= MAX_HOLD_DAYS:
            sell_reason = '时间退出'

        if sell_reason:
            order_target(s, 0)
            log.info('SELL %s %s | entry %.2f | exit %.2f | profit %.2f%% | days %d | reason %s',
                     s, cd.name, entry_price, current_price, profit_pct * 100,
                     hold_days, sell_reason)
            if s in g.watchlist:
                del g.watchlist[s]

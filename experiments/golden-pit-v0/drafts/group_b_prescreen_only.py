# ⛔ DRAFT / NOT APPROVED — 2026-07-22
# G 裁定: Implementation HOLD. 实验矩阵待 v0.1 Spec 通过后重写.
# ============================================================
# Golden Pit Simulation Experiment v0 — Group B (仅前置) [DRAFT]
# 四重门黄金坑前置 → 当日开盘买入 → 持有 10 日退出
# 不作早盘量价确认
# 回测频率: 日线
# ============================================================

from jqdata import *
import numpy as np
import pandas as pd

# ---------- 参数（与 Group A 相同的前置+退出参数） ----------

INDEX_POOL = ['000300.XSHG', '000905.XSHG']
MIN_LIST_DAYS = 120
MIN_DAILY_AMOUNT = 1e8

MAX_DRAWDOWN_PCT = -0.12
MA_PERIOD = 20
LOW_PROXIMITY_PCT = 0.08
VOL_SHORT = 5
VOL_LONG = 20
BBIBOLL_N = 11
BBIBOLL_M = 6

POSITION_PCT = 0.10
MAX_POSITIONS = 5
MAX_TOTAL_PCT = 0.50
MAX_SAME_INDUSTRY = 2

TAKE_PROFIT = 0.12
STOP_LOSS = -0.06
MAX_HOLD_DAYS = 10
YANG_COUNT_EXIT = 3
YANG_VOL_RATIO = 1.5
ABNORMAL_UP_PCT = 0.07
ABNORMAL_VOL_RATIO = 2.0


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
    g.daily_volumes = {}
    g.prescreened = []

    # 09:00 前置筛选 → 09:31 开盘买入 → 14:50 退出检查
    run_daily(prescreen, time='09:00')
    run_daily(execute_buys, time='09:31')
    run_daily(check_exits, time='14:50')


def get_stock_pool(context):
    """同 Group A"""
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

    if valid:
        df = get_price(valid, end_date=context.previous_date, count=MA_PERIOD,
                       frequency='daily', fields=['money'], skip_paused=False, fq=None)
        avg_money = df['money'].mean()
        valid = [s for s in valid if s in avg_money.index and avg_money[s] >= MIN_DAILY_AMOUNT]

    return valid


def prescreen(context):
    """09:00 — 黄金坑前置筛选（与 Group A 完全相同）"""
    pool = get_stock_pool(context)
    if not pool:
        g.prescreened = []
        return

    df = get_price(pool, end_date=context.previous_date, count=120,
                   frequency='daily',
                   fields=['open', 'close', 'high', 'low', 'volume'],
                   fq='pre')

    prescreened = []
    for s in pool:
        try:
            data = df.xs(s, level=1, axis=1)
        except (KeyError, AttributeError):
            continue
        if len(data) < 60:
            continue

        close = data['close'].dropna()
        high = data['high'].dropna()
        low = data['low'].dropna()
        volume = data['volume'].dropna()
        if len(close) < 60:
            continue

        # P1
        rolling_20_high = high.rolling(20).max().iloc[-1]
        drawdown = (close.iloc[-1] - rolling_20_high) / rolling_20_high
        if drawdown > MAX_DRAWDOWN_PCT:
            continue

        # P2
        ma20 = close.rolling(MA_PERIOD).mean().iloc[-1]
        if close.iloc[-1] >= ma20:
            continue

        # P3
        low_60 = low.rolling(60).min().iloc[-1]
        proximity = (close.iloc[-1] - low_60) / low_60
        if proximity > LOW_PROXIMITY_PCT:
            continue

        # P4
        ma5_vol = volume.rolling(VOL_SHORT).mean().iloc[-1]
        ma20_vol = volume.rolling(VOL_LONG).mean().iloc[-1]
        if ma5_vol >= ma20_vol:
            continue

        # P5
        ma3 = close.rolling(3).mean()
        ma6 = close.rolling(6).mean()
        ma12 = close.rolling(12).mean()
        ma24 = close.rolling(24).mean()
        bbi = (ma3 + ma6 + ma12 + ma24) / 4
        std = close.rolling(BBIBOLL_N).std()
        lower_band = bbi - BBIBOLL_M * std
        if close.iloc[-1] > lower_band.iloc[-1] * 1.02:
            continue
        if len(close) >= 4:
            decline_3d_ago = (close.iloc[-4] - close.iloc[-5]) / close.iloc[-5]
            decline_today = (close.iloc[-1] - close.iloc[-2]) / close.iloc[-2]
            if decline_today < decline_3d_ago:
                continue

        prescreened.append(s)

    g.prescreened = prescreened


def execute_buys(context):
    """09:31 — 开盘买入（无早盘确认，直接买前置通过的标的）"""
    if not hasattr(g, 'prescreened') or not g.prescreened:
        return

    active_positions = [p for p, pos in context.portfolio.positions.items()
                        if pos.total_amount > 0]

    if len(active_positions) >= MAX_POSITIONS:
        return

    total_pct = sum(pos.value for pos in context.portfolio.positions.values()) / \
                context.portfolio.portfolio_value
    if total_pct >= MAX_TOTAL_PCT:
        return

    industry_count = {}
    for p in active_positions:
        try:
            ind = get_industry(p)
            if ind and 'sw_l1' in ind:
                code = ind['sw_l1']['industry_code']
                industry_count[code] = industry_count.get(code, 0) + 1
        except Exception:
            pass

    current_data = get_current_data()
    cash_per_stock = context.portfolio.portfolio_value * POSITION_PCT

    for s in g.prescreened:
        if len(active_positions) >= MAX_POSITIONS or total_pct >= MAX_TOTAL_PCT:
            break
        if s in active_positions:
            continue

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

        available = min(cash_per_stock, context.portfolio.cash * 0.5)
        if available < cd.last_price * 100:
            continue

        order_value(s, available)
        active_positions.append(s)
        total_pct += POSITION_PCT

        try:
            ind = get_industry(s)
            ind_code = ind['sw_l1']['industry_code'] if ind and 'sw_l1' in ind else 'unknown'
        except Exception:
            ind_code = 'unknown'

        g.watchlist[s] = {
            'entry_price': cd.last_price,
            'entry_date': context.current_dt.date(),
            'industry': ind_code,
            'yang_count': 0,
            'had_volume_spike': False,
        }
        if s not in g.daily_volumes:
            g.daily_volumes[s] = {}


def check_exits(context):
    """14:50 — 退出检查（与 Group A 相同）"""
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

        try:
            today_bar = attribute_history(s, 1, unit='1d',
                                          fields=['volume', 'close', 'open'],
                                          skip_paused=True)
            if today_bar is not None and len(today_bar) > 0:
                today_vol = today_bar['volume'].iloc[-1]
                today_close = today_bar['close'].iloc[-1]
                today_open = today_bar['open'].iloc[-1]
                g.daily_volumes[s][context.current_dt.date()] = today_vol

                if today_close > today_open:
                    entry['yang_count'] = entry.get('yang_count', 0) + 1
                else:
                    entry['yang_count'] = max(0, entry.get('yang_count', 0) - 1)

                vol_ma20 = pd.Series(list(g.daily_volumes[s].values())).rolling(20).mean().iloc[-1]
                if today_vol >= vol_ma20 * YANG_VOL_RATIO:
                    entry['had_volume_spike'] = True
        except Exception:
            pass

        current_price = cd.last_price
        profit_pct = (current_price - entry_price) / entry_price

        sell_reason = None

        if cd.paused:
            continue
        if cd.low_limit and current_price <= cd.low_limit:
            continue

        if profit_pct <= STOP_LOSS:
            sell_reason = '止损'
        elif profit_pct >= TAKE_PROFIT:
            sell_reason = '止盈'
        elif entry.get('yang_count', 0) >= YANG_COUNT_EXIT and entry.get('had_volume_spike'):
            sell_reason = '放量阳线退出'
        elif profit_pct >= ABNORMAL_UP_PCT:
            try:
                today_vol = g.daily_volumes[s].get(context.current_dt.date(), 0)
                vol_ma20 = pd.Series(list(g.daily_volumes[s].values())).rolling(20).mean().iloc[-1]
                if today_vol >= vol_ma20 * ABNORMAL_VOL_RATIO:
                    sell_reason = '异常放量退出'
            except Exception:
                pass
        elif hold_days >= MAX_HOLD_DAYS:
            sell_reason = '时间退出'

        if sell_reason:
            order_target(s, 0)
            log.info('SELL %s %s | entry %.2f | exit %.2f | profit %.2f%% | days %d | reason %s',
                     s, cd.name, entry_price, current_price, profit_pct * 100,
                     hold_days, sell_reason)
            if s in g.watchlist:
                del g.watchlist[s]

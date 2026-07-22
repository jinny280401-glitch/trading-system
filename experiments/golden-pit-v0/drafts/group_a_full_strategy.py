# ⛔ DRAFT / NOT APPROVED — 2026-07-22
# G 裁定: Implementation HOLD. 实验矩阵待 v0.1 Spec 通过后重写.
# 当前仅保留现场，不运行正式回测，不作为实现进度或能力证据.
# ============================================================
# Golden Pit Simulation Experiment v0 — Group A (完整策略) [DRAFT]
# 四重门黄金坑前置 + 早盘量价确认 + 波段退出
# 回测频率: 分钟 (必须，否则 run_daily(time='10:00') 不可用)
# ============================================================

from jqdata import *
import numpy as np
import pandas as pd

# ---------- 策略参数（冻结，不回测后调整） ----------

# 标的池
INDEX_POOL = ['000300.XSHG', '000905.XSHG']  # 沪深300 + 中证500
MIN_LIST_DAYS = 120
MIN_DAILY_AMOUNT = 1e8  # 1 亿

# 黄金坑前置
MAX_DRAWDOWN_PCT = -0.12    # 20 日最大跌幅
MA_PERIOD = 20
LOW_PROXIMITY_PCT = 0.08   # 距 60 日最低价
VOL_SHORT = 5
VOL_LONG = 20
BBIBOLL_N = 11
BBIBOLL_M = 6

# 早盘确认
OPEN_GAP_MIN = -0.02
OPEN_GAP_MAX = 0.02
MORNING_MINUTES = 30       # 9:30-10:00
MORNING_VOL_RATIO = 1.5
MORNING_LOOKBACK = 5       # 近 5 日同期
MIN_CONDITIONS_MET = 4     # 至少满足 4 项早盘条件
INDEX_DECLINE_LIMIT = -0.02  # 大盘系统性下跌阈值

# 仓位
POSITION_PCT = 0.10
MAX_POSITIONS = 5
MAX_TOTAL_PCT = 0.50
MAX_SAME_INDUSTRY = 2

# 退出
TAKE_PROFIT = 0.12
STOP_LOSS = -0.06
MAX_HOLD_DAYS = 10
YANG_COUNT_EXIT = 3
YANG_VOL_RATIO = 1.5
ABNORMAL_UP_PCT = 0.07
ABNORMAL_VOL_RATIO = 2.0

def initialize(context):
    """策略初始化"""
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

    # 全局状态
    g.watchlist = {}         # {code: {entry_price, entry_date, industry, yang_count, had_volume_spike}}
    g.daily_volumes = {}     # {code: {date: volume}} 用于退出量比检查
    g.prescreened = []       # 当日通过前置的标的
    g.prescreen_date = None  # 前置筛选日期

    # 09:00 — 盘前筛选（仅用 T-1 数据）
    run_daily(prescreen, time='09:00')
    # 10:00 — 早盘确认
    run_daily(morning_confirm, time='10:00')
    # 10:05 — 执行买入
    run_daily(execute_buys, time='10:05')
    # 14:50 — 检查退出条件
    run_daily(check_exits, time='14:50')

def get_stock_pool(context):
    """获取并过滤标的池"""
    stocks = []
    for idx in INDEX_POOL:
        stocks.extend(get_index_stocks(idx))

    stocks = list(set(stocks))  # 去重

    # 过滤：上市不足 120 日、停牌
    current_data = get_current_data()
    valid = []
    for s in stocks:
        if s not in current_data:
            continue
        cd = current_data[s]
        if cd.paused or cd.is_st:
            continue
        # 上市时间
        info = get_security_info(s)
        if info is None:
            continue
        days_since_list = (context.current_dt.date() - info.start_date).days
        if days_since_list < MIN_LIST_DAYS:
            continue
        valid.append(s)

    # 过滤：过去 20 日平均成交额 < 1 亿
    if valid:
        df = get_price(valid,
                       end_date=context.previous_date,
                       count=MA_PERIOD,
                       frequency='daily',
                       fields=['money'],
                       skip_paused=False,
                       fq=None)
        avg_money = df['money'].mean()
        valid = [s for s in valid if s in avg_money.index and avg_money[s] >= MIN_DAILY_AMOUNT]

    return valid


def prescreen(context):
    """09:00 — 黄金坑前置筛选，仅使用 T-1 数据"""

    pool = get_stock_pool(context)
    if not pool:
        g.prescreened = []
        g.prescreen_date = context.current_dt.date()
        return

    # 获取 120 日数据（覆盖所有前置计算）
    df = get_price(pool,
                   end_date=context.previous_date,
                   count=120,
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

        # --- P1: 20 日最大跌幅 >= 12% ---
        rolling_20_high = high.rolling(20).max().iloc[-1]
        drawdown = (close.iloc[-1] - rolling_20_high) / rolling_20_high
        if drawdown > MAX_DRAWDOWN_PCT:
            continue

        # --- P2: 收盘 < MA20 ---
        ma20 = close.rolling(MA_PERIOD).mean().iloc[-1]
        if close.iloc[-1] >= ma20:
            continue

        # --- P3: 距 60 日最低价 <= 8% ---
        low_60 = low.rolling(60).min().iloc[-1]
        proximity = (close.iloc[-1] - low_60) / low_60
        if proximity > LOW_PROXIMITY_PCT:
            continue

        # --- P4: 5 日均量 < 20 日均量 ---
        ma5_vol = volume.rolling(VOL_SHORT).mean().iloc[-1]
        ma20_vol = volume.rolling(VOL_LONG).mean().iloc[-1]
        if ma5_vol >= ma20_vol:
            continue

        # --- P5: BBIBOLL 下轨区域 + 不再加速下跌 ---
        ma3 = close.rolling(3).mean()
        ma6 = close.rolling(6).mean()
        ma12 = close.rolling(12).mean()
        ma24 = close.rolling(24).mean()
        bbi = (ma3 + ma6 + ma12 + ma24) / 4
        std = close.rolling(BBIBOLL_N).std()
        lower_band = bbi - BBIBOLL_M * std

        if close.iloc[-1] > lower_band.iloc[-1] * 1.02:
            continue

        # 3 日跌幅未扩大 (rate of decline not accelerating)
        if len(close) >= 4:
            decline_3d_ago = (close.iloc[-4] - close.iloc[-5]) / close.iloc[-5]
            decline_today = (close.iloc[-1] - close.iloc[-2]) / close.iloc[-2]
            if decline_today < decline_3d_ago:
                continue

        prescreened.append(s)

    g.prescreened = prescreened
    g.prescreen_date = context.current_dt.date()


def morning_confirm(context):
    """10:00 — 早盘量价确认"""

    if not g.prescreened or g.prescreen_date != context.current_dt.date():
        g.confirmed_buys = []
        return

    # 大盘环境检查
    csi300 = get_price('000300.XSHG',
                        end_date=context.current_dt,
                        count=MA_PERIOD + 1,
                        frequency='daily',
                        fields=['close'],
                        fq='pre')
    csi300_ma20 = csi300['close'].rolling(MA_PERIOD).mean().iloc[-1]
    csi300_today = csi300['close'].iloc[-1]
    csi300_prev = csi300['close'].iloc[-2]
    csi300_day_change = (csi300_today - csi300_prev) / csi300_prev

    market_crash = (csi300_day_change <= INDEX_DECLINE_LIMIT) or (csi300_today < csi300_ma20)

    confirmed = []

    # 批量取分钟数据 — 09:30-10:00
    current_data = get_current_data()

    for s in g.prescreened:
        if s not in current_data:
            continue
        cd = current_data[s]
        if cd.paused or cd.is_st:
            continue

        # 获取当日分钟线和近 5 日分钟线
        try:
            bars_today = attribute_history(s, MORNING_MINUTES, unit='1m',
                                           fields=['open', 'close', 'high', 'low', 'volume'],
                                           skip_paused=True)
            if bars_today is None or len(bars_today) < 5:
                continue
        except Exception:
            continue

        open_price = bars_today['open'].iloc[0]
        price_10_00 = bars_today['close'].iloc[-1]
        high_30m = bars_today['high'].max()
        vol_30m = bars_today['volume'].sum()

        # 昨日数据
        yesterday = attribute_history(s, 1, unit='1d',
                                      fields=['close', 'high'],
                                      skip_paused=True)
        if yesterday is None or len(yesterday) == 0:
            continue
        prev_close = yesterday['close'].iloc[-1]
        prev_high = yesterday['high'].iloc[-1]

        # 近 5 日同期均量
        try:
            hist_vol = get_price(s,
                                 end_date=context.previous_date,
                                 count=MORNING_LOOKBACK,
                                 frequency='daily',
                                 fields=['volume'],
                                 fq=None)
            if hist_vol is None or len(hist_vol) == 0:
                continue
            avg_hist_vol = hist_vol['volume'].mean()
            # 用日量的 1/8 近似 30 分钟量（4 小时交易 = 8 个 30 分钟）
            expected_vol = avg_hist_vol / 8
        except Exception:
            continue

        # --- 检查早盘条件 ---
        conditions_met = 0

        # M1: 开盘涨幅 -2% 至 +2%
        open_gap = (open_price - prev_close) / prev_close
        if OPEN_GAP_MIN <= open_gap <= OPEN_GAP_MAX:
            conditions_met += 1

        # M2: 10:00 价 > 开盘价
        if price_10_00 > open_price:
            conditions_met += 1

        # M3: 10:00 价 > 昨收
        if price_10_00 > prev_close:
            conditions_met += 1

        # M4: 9:30-10:00 量 >= 近 5 日同期 1.5 倍
        if expected_vol > 0 and vol_30m >= expected_vol * MORNING_VOL_RATIO:
            conditions_met += 1

        # M5: 突破昨日最高价 or 早盘 30 分高点
        if high_30m > prev_high:
            conditions_met += 1

        # M6: 大盘非系统性下跌
        if not market_crash:
            conditions_met += 1

        if conditions_met >= MIN_CONDITIONS_MET:
            confirmed.append(s)

    g.confirmed_buys = confirmed


def execute_buys(context):
    """10:05 — 执行买入"""

    if not hasattr(g, 'confirmed_buys') or not g.confirmed_buys:
        return

    current_positions = list(context.portfolio.positions.keys())
    active_positions = [p for p, pos in context.portfolio.positions.items()
                        if pos.total_amount > 0]

    # 仓位上限检查
    if len(active_positions) >= MAX_POSITIONS:
        return

    total_pct = sum(pos.value for pos in context.portfolio.positions.values()) / \
                context.portfolio.portfolio_value

    if total_pct >= MAX_TOTAL_PCT:
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

    current_data = get_current_data()
    cash_per_stock = context.portfolio.portfolio_value * POSITION_PCT

    for s in g.confirmed_buys:
        if len(active_positions) >= MAX_POSITIONS:
            break
        if total_pct >= MAX_TOTAL_PCT:
            break
        if s in active_positions:
            continue

        cd = current_data.get(s)
        if cd is None or cd.paused or cd.is_st:
            continue

        # 涨跌停检查
        if cd.high_limit and cd.last_price >= cd.high_limit:
            continue
        if cd.low_limit and cd.last_price <= cd.low_limit:
            continue

        # 行业检查
        try:
            ind = get_industry(s)
            if ind and 'sw_l1' in ind:
                code = ind['sw_l1']['industry_code']
                if industry_count.get(code, 0) >= MAX_SAME_INDUSTRY:
                    continue
        except Exception:
            pass

        # 可用资金
        available = min(cash_per_stock, context.portfolio.cash * 0.5)
        if available < cd.last_price * 100:
            continue

        order_value(s, available)
        active_positions.append(s)
        total_pct += POSITION_PCT

        # 记录买入信息
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
    """14:50 — 检查退出条件"""

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

        # 更新日成交量记录
        try:
            today_bar = attribute_history(s, 1, unit='1d',
                                          fields=['volume', 'close', 'open'],
                                          skip_paused=True)
            if today_bar is not None and len(today_bar) > 0:
                today_vol = today_bar['volume'].iloc[-1]
                today_close = today_bar['close'].iloc[-1]
                today_open = today_bar['open'].iloc[-1]
                g.daily_volumes[s][context.current_dt.date()] = today_vol

                # 更新阳线计数
                if today_close > today_open:
                    entry['yang_count'] = entry.get('yang_count', 0) + 1
                else:
                    entry['yang_count'] = max(0, entry.get('yang_count', 0) - 1)

                # 检查量能是否达到 20 日均量 1.5 倍
                vol_ma20 = pd.Series(list(g.daily_volumes[s].values())).rolling(20).mean().iloc[-1]
                if today_vol >= vol_ma20 * YANG_VOL_RATIO:
                    entry['had_volume_spike'] = True
        except Exception:
            pass

        current_price = cd.last_price
        profit_pct = (current_price - entry_price) / entry_price

        # --- 优先级退出一 ---
        sell_reason = None

        # 0. 无法成交检查（停牌/涨跌停卖不出）
        if cd.paused:
            continue
        if cd.low_limit and current_price <= cd.low_limit:
            continue  # 跌停卖不出，明天再试

        # 1. 止损 -6%
        if profit_pct <= STOP_LOSS:
            sell_reason = '止损'

        # 2. 止盈 +12%
        elif profit_pct >= TAKE_PROFIT:
            sell_reason = '止盈'

        # 3. 放量阳线退出
        elif entry.get('yang_count', 0) >= YANG_COUNT_EXIT and entry.get('had_volume_spike'):
            sell_reason = '放量阳线退出'

        # 4. 异常放量退出 (单日涨 >= 7% + 量 >= 20日均量2倍)
        elif profit_pct >= ABNORMAL_UP_PCT:
            try:
                today_vol = g.daily_volumes[s].get(context.current_dt.date(), 0)
                vol_ma20 = pd.Series(list(g.daily_volumes[s].values())).rolling(20).mean().iloc[-1]
                if today_vol >= vol_ma20 * ABNORMAL_VOL_RATIO:
                    sell_reason = '异常放量退出'
            except Exception:
                pass

        # 5. 时间退出
        elif hold_days >= MAX_HOLD_DAYS:
            sell_reason = '时间退出'

        if sell_reason:
            order_target(s, 0)
            log.info('SELL %s %s | entry %.2f | exit %.2f | profit %.2f%% | days %d | reason %s',
                     s, cd.name, entry_price, current_price, profit_pct * 100,
                     hold_days, sell_reason)
            if s in g.watchlist:
                del g.watchlist[s]

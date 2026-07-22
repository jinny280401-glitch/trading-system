# ============================================================
# Platform Smoke #3 — 分钟回测下单验证  (v0.2.1)
# ============================================================
# 回测: 频率=分钟, 2021-06-01~2021-06-07, 资金=1000000
# PASS: data_cutoff_time < signal_time < order_time <= fill_time
#       ORDER_ACCEPTED 和 FILL_VERIFIED 分开判定
# ============================================================

from jqdata import *
from datetime import datetime

def initialize(context):
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)
    set_order_cost(OrderCost(
        open_tax=0, close_tax=0.0005,
        open_commission=0.0003, close_commission=0.0003,
        min_commission=5
    ), type='stock')
    set_slippage(FixedSlippage(0.001))

    g.status = 'NOT_RUN'
    g.order_status = 'NOT_RUN'
    g.fill_status = 'NOT_RUN'
    g.data_cutoff_time = None
    g.signal_time = None
    g.order_time = None
    g.test_done = False

    run_daily(set_data_cutoff, time='10:00')
    run_daily(generate_signal, time='10:01')     # ← 信号生成，不下单
    run_daily(place_order, time='10:05')          # ← 读取已冻结信号，下单
    run_daily(check_fills, time='10:06')

def _ts(context):
    return context.current_dt.strftime('%Y-%m-%d %H:%M:%S')

def set_data_cutoff(context):
    if g.data_cutoff_time is None:
        g.data_cutoff_time = _ts(context)

def generate_signal(context):
    """10:01 — 生成信号，记录 signal_time，不下单"""
    g.data_cutoff_time = g.data_cutoff_time or _ts(context)
    g.signal_time = _ts(context)
    g.status = 'PENDING'
    log.info('[SMOKE-3] SIGNAL_GENERATED at %s', g.signal_time)

def place_order(context):
    """10:05 — 读取已冻结信号，下单"""
    if g.test_done:
        return
    if g.signal_time is None:
        log.error('[SMOKE-3] No signal — skipping order')
        return

    g.order_status = 'ORDER_REQUESTED'
    g.order_time = _ts(context)

    cd = get_current_data()
    pool = get_index_stocks('000300.XSHG')

    if not pool:
        g.order_status = 'FAIL'; g.status = 'FAIL'
        log.error('[SMOKE-3] ORDER FAILED: empty index pool')
        g.test_done = True; return

    test_stock = pool[0]
    if test_stock not in cd:
        g.order_status = 'FAIL'; g.status = 'FAIL'
        log.error('[SMOKE-3] ORDER FAILED: no current_data for %s', test_stock)
        g.test_done = True; return

    c = cd[test_stock]
    failure_reason = None

    if c.last_price >= c.high_limit:
        failure_reason = 'limit_up'; g.order_status = 'FAIL'
    elif c.last_price <= c.low_limit:
        failure_reason = 'limit_down'; g.order_status = 'FAIL'
    elif c.paused:
        failure_reason = 'paused'; g.order_status = 'FAIL'
    elif c.is_st:
        failure_reason = 'is_st'; g.order_status = 'FAIL'

    if failure_reason:
        g.status = 'FAIL'
        log.error('[SMOKE-3] ORDER FAILED: %s for %s', failure_reason, test_stock)
        g.test_done = True; return

    available = context.portfolio.cash
    if available < c.last_price * 100:
        failure_reason = 'insufficient_cash (available=%.2f need=%.2f)' % (available, c.last_price * 100)
        g.order_status = 'FAIL'; g.status = 'FAIL'
        log.error('[SMOKE-3] ORDER FAILED: %s', failure_reason)
        g.test_done = True; return

    try:
        order_value(test_stock, 50000)
        g.order_status = 'ORDER_ACCEPTED'
        g.test_stock = test_stock
        g.requested_value = 50000
        log.info('[SMOKE-3] ORDER_ACCEPTED: %s value=50000 signal=%s order=%s',
                 test_stock, g.signal_time, g.order_time)
    except Exception as e:
        g.order_status = 'FAIL'; g.status = 'FAIL'
        log.error('[SMOKE-3] ORDER REJECTED: %s', str(e))

    g.test_done = True

def check_fills(context):
    if not hasattr(g, 'test_stock'):
        return
    if g.order_status != 'ORDER_ACCEPTED':
        return

    g.fill_status = 'PENDING'
    trades = get_trades()
    orders = get_orders()

    fill_time = None; fill_price = None; fill_amount = None
    order_id = None; order_detail_status = 'UNKNOWN'

    if orders:
        for o in orders:
            if o.security == g.test_stock:
                order_id = str(o.order_id)
                order_detail_status = str(o.status) if hasattr(o, 'status') else 'UNKNOWN'
                log.info('[SMOKE-3] ORDER_STATUS: id=%s price=%.2f amount=%d status=%s',
                         order_id, o.price, o.amount, order_detail_status)

    if trades:
        for t in trades:
            if t.security == g.test_stock:
                fill_time = str(t.time)
                fill_price = t.price
                fill_amount = t.amount

                log.info('[SMOKE-3] FILL_VERIFIED: %s price=%.2f amount=%d time=%s',
                         t.security, fill_price, fill_amount, fill_time)

                # 严格时间链: cutoff < signal < order <= fill
                if g.data_cutoff_time and g.signal_time and g.order_time:
                    c1 = _compare_times(g.data_cutoff_time, g.signal_time)  # cutoff < signal
                    c2 = _compare_times(g.signal_time, g.order_time)        # signal < order
                    c3 = _compare_times(g.order_time, fill_time)            # order <= fill

                    if c1 < 0 and c2 < 0 and c3 <= 0:
                        g.fill_status = 'FILL_VERIFIED'
                        g.status = 'PASS'
                        log.info('[SMOKE-3] TIME_CHAIN: PASS '
                                 '(cutoff=%s < signal=%s < order=%s <= fill=%s)',
                                 g.data_cutoff_time, g.signal_time,
                                 g.order_time, fill_time)
                    else:
                        g.fill_status = 'FAIL'; g.status = 'FAIL'
                        log.error('[SMOKE-3] TIME_CHAIN: FAIL '
                                  '(c1=%d c2=%d c3=%d)', c1, c2, c3)
                else:
                    log.warn('[SMOKE-3] TIME_CHAIN: PARTIAL (missing timestamps)')
                break

    log.info('[SMOKE-3] SUMMARY: data_cutoff=%s signal=%s order=%s fill=%s '
             'order_id=%s fill_price=%s fill_amount=%s status=%s',
             g.data_cutoff_time, g.signal_time, g.order_time, fill_time,
             order_id, fill_price, fill_amount, g.fill_status)

def _compare_times(t1, t2):
    """Return -1/0/1. 解析失败返回 1 (视为不满足 '<' 要求)"""
    try:
        d1 = datetime.strptime(t1[:19], '%Y-%m-%d %H:%M:%S')
        d2 = datetime.strptime(t2[:19], '%Y-%m-%d %H:%M:%S')
    except Exception:
        return 1  # 解析失败 → 不通过
    return -1 if d1 < d2 else (1 if d1 > d2 else 0)

def handle_data(context, data):
    pass

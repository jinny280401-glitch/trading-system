# ============================================================
# Platform Smoke #5c — 滑点验证: PriceRelatedSlippage 比例偏移
# ============================================================
# 回测: 频率=分钟, 2021-06-01~2021-06-03, 资金=1000000
# 用途: 验证 PriceRelatedSlippage 产生价格比例偏移（非固定价差）
# ============================================================
# 冻结参数（三脚本统一）:
#   股票: 000300.XSHG (沪深300)
#   日期: 2021-06-01
#   时间: signal 10:01, order 10:05
#   数量: order_value(50000)
#   方向: BUY
#   基准价格: last_price at 10:01
# ============================================================

from jqdata import *
from datetime import datetime

MODEL_NAME = 'PriceRelatedSlippage'
MODEL_PARAMETER = 0.001  # 0.1% proportional slippage

def initialize(context):
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)
    set_order_cost(OrderCost(
        open_tax=0, close_tax=0.0005,
        open_commission=0.0003, close_commission=0.0003,
        min_commission=5
    ), type='stock')
    set_slippage(PriceRelatedSlippage(MODEL_PARAMETER))

    g.status = 'NOT_RUN'
    g.model_name = MODEL_NAME
    g.parameter = MODEL_PARAMETER
    g.side = 'BUY'
    g.test_done = False
    g.reference_price = None
    g.fill_price = None
    g.fill_amount = None
    g.order_status = 'NOT_RUN'
    g.trade_id = None

    run_daily(generate_signal, time='10:01')
    run_daily(place_order, time='10:05')
    run_daily(check_fills, time='10:06')

def _ts(context):
    return context.current_dt.strftime('%Y-%m-%d %H:%M:%S')

def generate_signal(context):
    if g.test_done:
        return
    g.status = 'PENDING'

    cd = get_current_data()
    pool = get_index_stocks('000300.XSHG')
    if not pool:
        log.error('[SMOKE-5c] FAIL: empty index pool')
        g.status = 'FAIL'
        g.test_done = True
        return

    test_stock = pool[0]
    if test_stock not in cd:
        log.error('[SMOKE-5c] FAIL: no current_data for %s', test_stock)
        g.status = 'FAIL'
        g.test_done = True
        return

    c = cd[test_stock]
    g.reference_price = c.last_price
    g.test_stock = test_stock
    g.signal_time = _ts(context)
    g.order_status = 'ORDER_REQUESTED'

    log.info('[SMOKE-5c] SIGNAL: %s ref_price=%.2f time=%s',
             test_stock, g.reference_price, g.signal_time)

def place_order(context):
    if g.test_done or g.order_status != 'ORDER_REQUESTED':
        return

    try:
        order_value(g.test_stock, 50000)
        g.order_status = 'ORDER_ACCEPTED'
        g.order_time = _ts(context)
        log.info('[SMOKE-5c] ORDER_ACCEPTED: %s value=50000 time=%s',
                 g.test_stock, g.order_time)
    except Exception as e:
        g.order_status = 'FAIL'
        g.status = 'FAIL'
        log.error('[SMOKE-5c] ORDER REJECTED: %s', str(e))
        g.test_done = True

def check_fills(context):
    if g.test_done or g.order_status != 'ORDER_ACCEPTED':
        return

    trades = get_trades()
    orders = get_orders()

    if orders:
        for o in orders:
            if o.security == g.test_stock:
                g.trade_id = str(o.order_id)
                g.order_status_detail = str(o.status) if hasattr(o, 'status') else 'UNKNOWN'

    if trades:
        for t in trades:
            if t.security == g.test_stock:
                g.fill_time = str(t.time)
                g.fill_price = t.price
                g.fill_amount = t.amount
                g.absolute_gap = g.fill_price - g.reference_price if g.reference_price else None
                g.gap_ratio = (g.absolute_gap / g.reference_price) if g.reference_price and g.absolute_gap is not None else None

                log.info('[SMOKE-5c] FILL: price=%.2f amount=%d time=%s gap=%.4f ratio=%.6f',
                         g.fill_price, g.fill_amount, g.fill_time,
                         g.absolute_gap or 0, g.gap_ratio or 0)

                # 时间链验证
                if g.signal_time and g.order_time:
                    ok = _compare_times(g.signal_time, g.order_time) <= 0 \
                     and _compare_times(g.order_time, g.fill_time) <= 0
                    if ok and g.fill_amount > 0:
                        g.status = 'PASS'
                        log.info('[SMOKE-5c] PASS: %s(%.4f) fill_price=%.2f ref_price=%.2f gap=%.4f ratio=%.6f',
                                 MODEL_NAME, MODEL_PARAMETER,
                                 g.fill_price, g.reference_price,
                                 g.absolute_gap or 0, g.gap_ratio or 0)
                    else:
                        g.status = 'FAIL'
                        log.error('[SMOKE-5c] FAIL: time chain broken or zero fill')
                g.test_done = True
                break

    # 输出结构化结果
    log.info('[SMOKE-5c] RESULT: model=%s param=%s ref=%.2f fill=%.2f gap=%.4f ratio=%.6f '
             'side=%s status=%s trade_id=%s',
             MODEL_NAME, MODEL_PARAMETER,
             g.reference_price or 0, g.fill_price or 0,
             g.absolute_gap or 0, g.gap_ratio or 0,
             g.side, g.status, g.trade_id or 'N/A')

def _compare_times(t1, t2):
    """Return -1/0/1 — safe compare of ISO-like timestamps."""
    try:
        d1 = datetime.strptime(t1[:19], '%Y-%m-%d %H:%M:%S')
        d2 = datetime.strptime(t2[:19], '%Y-%m-%d %H:%M:%S')
    except Exception:
        return 0
    return -1 if d1 < d2 else (1 if d1 > d2 else 0)

def handle_data(context, data):
    pass

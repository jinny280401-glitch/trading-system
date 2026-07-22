# ============================================================
# Platform Smoke #5 — Slipage Model: FixedSlippage(0.001)
# ============================================================
# 回测: 频率=分钟, 2021-06-01~2021-06-03, 资金=100000
# ============================================================
from jqdata import *

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
    g.result = None
    g.test_done = False
    run_daily(run_test, time='09:31')

def run_test(context):
    if g.test_done:
        return
    g.test_done = True
    g.status = 'PENDING'

    pool = get_index_stocks('000300.XSHG')
    if not pool:
        g.status = 'FAIL'
        log.error('[SMOKE-5] FAIL: empty pool')
        return

    stock = pool[0]
    cd = get_current_data()
    if stock not in cd:
        g.status = 'FAIL'
        log.error('[SMOKE-5] FAIL: no current_data')
        return

    ref_price = cd[stock].last_price
    try:
        order(stock, 100)
        log.info('[SMOKE-5] MODEL=FixedSlippage stock=%s ref_price=%.2f shares=100', stock, ref_price)
    except Exception as e:
        g.status = 'FAIL'
        log.error('[SMOKE-5] FAIL: %s', str(e))
        return

    g.ref_price = ref_price
    g.stock = stock
    run_daily(check_fill, time='09:32')

def check_fill(context):
    if g.result is not None:
        return
    trades = get_trades()
    if not trades:
        return

    for t in trades:
        if t.security != g.stock:
            continue
        gap = t.price - g.ref_price
        bps = (gap / g.ref_price) * 10000 if g.ref_price > 0 else 0
        g.result = {
            'model': 'FixedSlippage',
            'parameter': '0.001 (fixed price offset)',
            'stock': t.security,
            'ref_price': g.ref_price,
            'fill_price': t.price,
            'gap_abs': gap,
            'gap_bps': bps,
            'side': 'buy',
            'order_status': 'filled',
            'trade_id': str(t.time),
        }
        g.status = 'PASS'
        log.info('[SMOKE-5] MODEL=FixedSlippage stock=%s ref=%.2f fill=%.2f gap=%+.4f (%+.1f bps) side=buy status=filled',
                 t.security, g.ref_price, t.price, gap, bps)
        break

def handle_data(context, data):
    pass

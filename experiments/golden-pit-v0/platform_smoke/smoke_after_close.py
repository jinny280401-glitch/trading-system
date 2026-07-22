# ============================================================
# Platform Smoke #1 — after_close 调度验证
# ============================================================
# 回测: 频率=分钟, 2021-06-01~2021-06-07, 资金=100000
# PASS: >=3 个不同交易日, 每个交易日仅触发 1 次, 无缺失无重复
# ============================================================

from jqdata import *

REQUIRED_TRADE_DAYS = 3

def initialize(context):
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)
    g.status = 'NOT_RUN'
    g.triggers = []
    run_daily(after_close_check, time='after_close')

def after_close_check(context):
    dt = context.current_dt
    g.status = 'PENDING'

    entry = {
        'trade_date': dt.strftime('%Y-%m-%d'),
        'callback_name': 'after_close',
        'callback_time': dt.strftime('%H:%M:%S'),
        'context_dt': str(dt),
        'signal_count': len(g.triggers) + 1,
    }
    g.triggers.append(entry)

    log.info('[SMOKE-1] after_close #%d: trade_date=%s callback_time=%s',
             entry['signal_count'], entry['trade_date'], entry['callback_time'])

    # 每日 after_close 后检查汇总
    from collections import Counter
    dates_seen = set(t['trade_date'] for t in g.triggers)
    trade_days = len(dates_seen)
    date_counts = Counter(t['trade_date'] for t in g.triggers)
    duplicates = {d: c for d, c in date_counts.items() if c > 1}

    log.info('[SMOKE-1] SUMMARY: trade_days=%d total_triggers=%d duplicates=%s',
             trade_days, len(g.triggers),
             str(duplicates) if duplicates else 'NONE')

    if trade_days >= REQUIRED_TRADE_DAYS:
        if duplicates:
            g.status = 'FAIL'
            log.warn('[SMOKE-1] FAIL: duplicates on %s', list(duplicates.keys()))
        else:
            g.status = 'PASS'
            log.info('[SMOKE-1] PASS: %d trade days, exactly 1 per day', trade_days)
    else:
        g.status = 'PENDING'
        log.info('[SMOKE-1] PENDING: %d/%d trade days', trade_days, REQUIRED_TRADE_DAYS)

def handle_data(context, data):
    pass  # 报告由 after_close 自身负责

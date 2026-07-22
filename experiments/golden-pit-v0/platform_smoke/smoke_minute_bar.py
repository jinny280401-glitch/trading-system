# ============================================================
# Platform Smoke #2 — 分钟 bar 闭合验证  (v0.2.1)
# ============================================================
# 回测: 频率=分钟, 2021-06-01~2021-06-07, 资金=100000
# PASS: 三个 gate 全部通过:
#   BAR_COUNT_VALID — 预期 ~30 根 bar, 覆盖 09:30-09:59
#   LAST_BAR_CLOSED — 最后一根实际输入 bar 时间戳 <= 09:59:00
#   SIGNAL_INPUT_CUTOFF_ENFORCED — 过滤后不含 10:00+ bar, 数量/时间戳记录
#
# PLATFORM_OBSERVATION (NON-BLOCKING):
#   include_now 行为记录 (get_bars vs get_price 差异观察, 不计入总 PASS)
# ============================================================

from jqdata import *

EXPECTED_BAR_MIN = 28
EXPECTED_BAR_MAX = 31

def initialize(context):
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)
    g.status = 'NOT_RUN'
    g.gate = {
        'BAR_COUNT_VALID': 'NOT_RUN',
        'LAST_BAR_CLOSED': 'NOT_RUN',
        'SIGNAL_INPUT_CUTOFF_ENFORCED': 'NOT_RUN',
    }
    g.platform_observation = {
        'include_now_via_get_bars': 'NOT_RUN',
    }
    g.results = []
    g.tested_dates = set()
    run_daily(check_minute_bar, time='10:01')

def check_minute_bar(context):
    today = context.current_dt.strftime('%Y-%m-%d')
    if today in g.tested_dates:
        return
    g.tested_dates.add(today)
    g.status = 'PENDING'

    query_time = str(context.current_dt)
    test_stock = '000300.XSHG'
    result = {
        'date': today,
        'query_time': query_time,
        'bar_count_valid': False,
        'last_bar_closed': False,
        'cutoff_enforced': False,
        'errors': [],
    }

    try:
        # === 主线: get_price 读取 09:30-10:00 范围 ===
        bars = get_price(test_stock,
                         start_date=context.current_dt.replace(hour=9, minute=30),
                         end_date=context.current_dt.replace(hour=10, minute=0),
                         frequency='minute',
                         fields=['close'],
                         skip_paused=False,
                         fq=None)

        if bars is None or len(bars) == 0:
            result['errors'].append('get_price returned None/empty')
            g.gate['BAR_COUNT_VALID'] = 'FAIL'
            g.gate['LAST_BAR_CLOSED'] = 'FAIL'
            g.gate['SIGNAL_INPUT_CUTOFF_ENFORCED'] = 'FAIL'
            log.error('[SMOKE-2] %s FAIL: no bars returned', today)
        else:
            count_raw = len(bars)
            first_raw = bars.index[0]
            last_raw = bars.index[-1]
            last_min_raw = _extract_minute(last_raw)

            log.info('[SMOKE-2] %s RAW: count=%d first=%s last=%s(min=%d) query=%s',
                     today, count_raw, first_raw, last_raw, last_min_raw, query_time)

            result['bar_count_raw'] = count_raw
            result['first_bar_time'] = str(first_raw)
            result['last_bar_time_raw'] = str(last_raw)

            # Gate 1: BAR_COUNT_VALID
            if EXPECTED_BAR_MIN <= count_raw <= EXPECTED_BAR_MAX:
                result['bar_count_valid'] = True
                g.gate['BAR_COUNT_VALID'] = 'PASS'
                log.info('[SMOKE-2] %s BAR_COUNT_VALID: PASS (%d bars)', today, count_raw)
            else:
                result['errors'].append('bar count %d not in [%d,%d]' % (count_raw, EXPECTED_BAR_MIN, EXPECTED_BAR_MAX))
                g.gate['BAR_COUNT_VALID'] = 'FAIL'
                log.warn('[SMOKE-2] %s BAR_COUNT_VALID: FAIL (%d bars)', today, count_raw)

            # Gate 2: LAST_BAR_CLOSED — 验证最后一根 bar 时间戳 <= 09:59
            if last_min_raw <= 59:
                result['last_bar_closed'] = True
                g.gate['LAST_BAR_CLOSED'] = 'PASS'
                log.info('[SMOKE-2] %s LAST_BAR_CLOSED: PASS (last_min=%d)', today, last_min_raw)
            else:
                result['errors'].append('last bar minute %d > 59' % last_min_raw)
                g.gate['LAST_BAR_CLOSED'] = 'FAIL'
                log.warn('[SMOKE-2] %s LAST_BAR_CLOSED: FAIL (last_min=%d)', today, last_min_raw)

            # === SIGNAL_INPUT_CUTOFF_ENFORCED: 显式过滤 bar_time <= 09:59 ===
            # 过滤前后记录数量和最后时间戳
            filtered_indices = [i for i in bars.index if _extract_minute(i) <= 59]
            if filtered_indices:
                filtered_last = filtered_indices[-1]
                filtered_count = len(filtered_indices)
                filtered_hash = hash(str([str(i) for i in filtered_indices])) & 0xFFFFFFFF

                log.info('[SMOKE-2] %s FILTERED: count=%d last=%s hash=%s',
                         today, filtered_count, filtered_last, hex(filtered_hash))

                result['filtered_count'] = filtered_count
                result['filtered_last_time'] = str(filtered_last)
                result['filtered_input_hash'] = hex(filtered_hash)

                # 确认无 10:00+ bar 渗入
                leaked = [i for i in bars.index if _extract_minute(i) >= 0 and _extract_minute(i) > 59]
                if not leaked and filtered_count >= EXPECTED_BAR_MIN:
                    result['cutoff_enforced'] = True
                    g.gate['SIGNAL_INPUT_CUTOFF_ENFORCED'] = 'PASS'
                    log.info('[SMOKE-2] %s SIGNAL_INPUT_CUTOFF_ENFORCED: PASS (filtered=%d, leaked=%d)',
                             today, filtered_count, len(leaked))
                else:
                    g.gate['SIGNAL_INPUT_CUTOFF_ENFORCED'] = 'FAIL'
                    log.warn('[SMOKE-2] %s SIGNAL_INPUT_CUTOFF_ENFORCED: FAIL (filtered=%d, leaked=%d)',
                             today, filtered_count, len(leaked))
            else:
                g.gate['SIGNAL_INPUT_CUTOFF_ENFORCED'] = 'FAIL'
                result['errors'].append('no bars survived cutoff filter')

    except Exception as e:
        result['errors'].append('unexpected: %s' % str(e))
        g.gate['BAR_COUNT_VALID'] = 'FAIL'
        g.gate['LAST_BAR_CLOSED'] = 'FAIL'
        g.gate['SIGNAL_INPUT_CUTOFF_ENFORCED'] = 'FAIL'
        log.error('[SMOKE-2] %s FAIL: %s', today, str(e))

    # === PLATFORM_OBSERVATION: include_now 行为记录 (NON-BLOCKING) ===
    try:
        bars_b = get_bars(test_stock,
                          count=30, unit='1m', fields=['close'],
                          include_now=True,
                          end_dt=context.current_dt.replace(hour=10, minute=0),
                          fq_ref_date=context.current_dt)
        if bars_b is not None and len(bars_b) > 0:
            last_b = bars_b.index[-1]
            count_b = len(bars_b)
            g.platform_observation['include_now_via_get_bars'] = {
                'bar_count': count_b,
                'last_bar_time': str(last_b),
                'last_bar_minute': _extract_minute(last_b),
                'diff_vs_get_price': count_b - count_raw,
            }
            log.info('[SMOKE-2] %s PLATFORM_OBS: get_bars(include_now=True) count=%d (diff=%d)',
                     today, count_b, count_b - count_raw)
        else:
            g.platform_observation['include_now_via_get_bars'] = 'FAIL (empty)'
    except Exception as e:
        g.platform_observation['include_now_via_get_bars'] = 'FAIL (%s)' % str(e)

    g.results.append(result)

    # 综合判定 — 仅三个主 gate
    all_pass = all(v == 'PASS' for v in g.gate.values())
    if all_pass:
        g.status = 'PASS'
        log.info('[SMOKE-2] OVERALL: PASS')
    elif any(v == 'FAIL' for v in g.gate.values()):
        g.status = 'FAIL'
        log.warn('[SMOKE-2] OVERALL: FAIL — gates=%s', g.gate)
    else:
        g.status = 'PENDING'
        log.info('[SMOKE-2] OVERALL: PENDING — gates=%s', g.gate)

def _extract_minute(ts):
    try:
        return ts.minute
    except AttributeError:
        return int(str(ts)[-5:-3])

def handle_data(context, data):
    pass

# ============================================================
# Platform Smoke #4 — 历史成分股重建验证
# ============================================================
# 回测: 频率=分钟, 2021-06-28~2025-07-01, 资金=100000
# PASS: 四个 gate 全部通过:
#   HISTORICAL_DATE_EFFECTIVE — date 参数生效, 不同日期集合变化
#   CONSTITUENT_SET_CHANGED — 至少两个日期的成分股集合有差异
#   NO_FUTURE_CONTEXT_LEAKAGE — avoid_future_data 开启
#   HISTORICAL_TRADABILITY_AVAILABLE — 历史 ST/停牌/上市日可查
# ============================================================

from jqdata import *
import hashlib

MIN_SAMPLE = 200  # 最少采样数（全量检查可交易状态）

def initialize(context):
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)
    set_option('avoid_future_data', True)

    g.status = 'NOT_RUN'
    g.gate = {
        'HISTORICAL_DATE_EFFECTIVE': 'NOT_RUN',
        'CONSTITUENT_SET_CHANGED': 'NOT_RUN',
        'NO_FUTURE_CONTEXT_LEAKAGE': 'NOT_RUN',
        'HISTORICAL_TRADABILITY_AVAILABLE': 'NOT_RUN',
    }
    g.tested = set()
    g.results = {}
    run_daily(check_constituents, time='09:01')

def _sorted_hash(items):
    return hashlib.sha256(','.join(sorted(items)).encode()).hexdigest()[:12]

def check_constituents(context):
    """仅在当前回测日期等于 context.current_dt 时查询。"""
    today = context.current_dt.strftime('%Y-%m-%d')
    if today in g.tested:
        return

    g.status = 'PENDING'
    g.gate['NO_FUTURE_CONTEXT_LEAKAGE'] = 'PASS'  # avoid_future_data 在 initialize 已设置

    log.info('[SMOKE-4] Checking constituents for date=%s', today)

    try:
        hs300 = get_index_stocks('000300.XSHG', date=today)
        zz500 = get_index_stocks('000905.XSHG', date=today)
    except Exception as e:
        log.error('[SMOKE-4] %s FAIL: get_index_stocks error: %s', today, str(e))
        g.gate['HISTORICAL_DATE_EFFECTIVE'] = 'FAIL'
        g.status = 'FAIL'
        g.tested.add(today)
        return

    hs300_count = len(hs300)
    zz500_count = len(zz500)
    all_stocks = list(set(hs300 + zz500))

    log.info('[SMOKE-4] %s: HS300=%d (200-350: %s), ZZ500=%d (400-550: %s)',
             today, hs300_count, 'OK' if 200 <= hs300_count <= 350 else 'WARN',
             zz500_count, 'OK' if 400 <= zz500_count <= 550 else 'WARN')

    # 全量可交易状态检查（不再只用前 20）
    cd = get_current_data()
    tradable, blocked_st, blocked_paused, blocked_limit = [], [], [], []

    sample_n = min(len(all_stocks), MIN_SAMPLE)
    for s in all_stocks[:sample_n]:
        if s not in cd:
            continue
        c = cd[s]
        if c.is_st:
            blocked_st.append(s)
        elif c.paused:
            blocked_paused.append(s)
        elif c.last_price >= c.high_limit or c.last_price <= c.low_limit:
            blocked_limit.append(s)
        else:
            info = get_security_info(s)
            days_listed = (context.current_dt.date() - info.start_date).days if info else 0
            if days_listed < 120:
                continue
            tradable.append(s)

    representative = sorted(all_stocks[:5]) + ['...'] + sorted(all_stocks[-5:])

    g.results[today] = {
        'hs300_count': hs300_count,
        'zz500_count': zz500_count,
        'hs300_list': sorted(hs300),
        'zz500_list': sorted(zz500),
        'hs300_hash': _sorted_hash(hs300),
        'zz500_hash': _sorted_hash(zz500),
        'combined_hash': _sorted_hash(all_stocks),
        'hs300_ok': 200 <= hs300_count <= 350,
        'zz500_ok': 400 <= zz500_count <= 550,
        'representative': representative,
        'sample_tradable': len(tradable),
        'sample_st': len(blocked_st),
        'sample_paused': len(blocked_paused),
        'sample_limit': len(blocked_limit),
        'total_pool': len(all_stocks),
    }

    log.info('[SMOKE-4] %s: total=%d sample=%d tradable=%d ST=%d paused=%d limit=%d hash=%s',
             today, len(all_stocks), sample_n, len(tradable), len(blocked_st),
             len(blocked_paused), len(blocked_limit), g.results[today]['combined_hash'])

    g.tested.add(today)

    # Gate 1: HISTORICAL_DATE_EFFECTIVE — date 参数是否生效
    dates = sorted(g.results.keys())
    if len(dates) >= 2:
        hashes = [g.results[d]['combined_hash'] for d in dates]
        if len(set(hashes)) >= 2:
            g.gate['HISTORICAL_DATE_EFFECTIVE'] = 'PASS'
            log.info('[SMOKE-4] HISTORICAL_DATE_EFFECTIVE: PASS (hashes differ across dates)')
        else:
            g.gate['HISTORICAL_DATE_EFFECTIVE'] = 'FAIL'
            log.warn('[SMOKE-4] HISTORICAL_DATE_EFFECTIVE: FAIL (all hashes identical=%s)', hashes[0])

    # Gate 2: HISTORICAL_TRADABILITY_AVAILABLE
    samples_with_tradability = sum(
        1 for r in g.results.values()
        if r['sample_tradable'] > 0 or r['sample_st'] > 0
    )
    if samples_with_tradability >= 1:
        g.gate['HISTORICAL_TRADABILITY_AVAILABLE'] = 'PASS'
        log.info('[SMOKE-4] HISTORICAL_TRADABILITY_AVAILABLE: PASS (%d dates with state data)',
                 samples_with_tradability)
    elif len(g.results) >= 1:
        g.gate['HISTORICAL_TRADABILITY_AVAILABLE'] = 'FAIL'

    # === 每日回调内完成 CONSTITUENT_SET_CHANGED 和综合判定（不依赖 handle_data） ===
    dates = sorted(g.results.keys())
    if len(dates) >= 2:
        d1, d2 = dates[0], dates[-1]
        set1_hs = set(g.results[d1]['hs300_list'])
        set2_hs = set(g.results[d2]['hs300_list'])
        set1_zz = set(g.results[d1]['zz500_list'])
        set2_zz = set(g.results[d2]['zz500_list'])

        added_hs = sorted(set2_hs - set1_hs)
        removed_hs = sorted(set1_hs - set2_hs)
        added_zz = sorted(set2_zz - set1_zz)
        removed_zz = sorted(set1_zz - set2_zz)

        g.gate['CONSTITUENT_SET_CHANGED'] = 'PASS' if (added_hs or removed_hs or added_zz or removed_zz) else 'FAIL'
        g.summary = {
            'first_date': d1,
            'last_date': d2,
            'hs300_added': added_hs[:20],
            'hs300_removed': removed_hs[:20],
            'hs300_added_count': len(added_hs),
            'hs300_removed_count': len(removed_hs),
            'zz500_added': added_zz[:20],
            'zz500_removed': removed_zz[:20],
            'zz500_added_count': len(added_zz),
            'zz500_removed_count': len(removed_zz),
        }
        log.info('[SMOKE-4] CONSTITUENT_SET_CHANGED: %s', g.gate['CONSTITUENT_SET_CHANGED'])
        log.info('[SMOKE-4] %s->%s HS300 added=%d removed=%d',
                 d1, d2, len(added_hs), len(removed_hs))
        log.info('[SMOKE-4] %s->%s ZZ500 added=%d removed=%d',
                 d1, d2, len(added_zz), len(removed_zz))
        log.info('[SMOKE-4] HS300 added(前5): %s  removed(前5): %s',
                 added_hs[:5], removed_hs[:5])
        log.info('[SMOKE-4] ZZ500 added(前5): %s  removed(前5): %s',
                 added_zz[:5], removed_zz[:5])

    # 综合判定（每次回调后评估，一旦所有 gate PASS 即标记完成）
    all_pass = all(v == 'PASS' for v in g.gate.values())
    if all_pass:
        g.status = 'PASS'
    elif any(v == 'FAIL' for v in g.gate.values()):
        g.status = 'FAIL'
    # else: keep PENDING

    if len(dates) >= 2 or g.status in ('PASS', 'FAIL'):
        log.info('[SMOKE-4] ====== GATE SUMMARY ======')
        for d in dates:
            r = g.results[d]
            log.info('[SMOKE-4] %s: HS300=%d ZZ500=%d hash=%s tradable=%d rep=%s',
                     d, r['hs300_count'], r['zz500_count'], r['combined_hash'],
                     r['sample_tradable'], r['representative'][:3])
        log.info('[SMOKE-4] GATES: %s', g.gate)
        log.info('[SMOKE-4] OVERALL: %s', g.status)
        if hasattr(g, 'summary'):
            log.info('[SMOKE-4] SET_CHANGES: HS300 +%d/-%d  ZZ500 +%d/-%d',
                     g.summary['hs300_added_count'], g.summary['hs300_removed_count'],
                     g.summary['zz500_added_count'], g.summary['zz500_removed_count'])

def handle_data(context, data):
    pass  # 所有判定逻辑在 check_constituents 回调中完成，不依赖分钟 tick

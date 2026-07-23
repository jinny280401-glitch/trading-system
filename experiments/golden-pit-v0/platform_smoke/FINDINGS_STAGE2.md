# Golden Pit Platform Smoke — Stage 2 Findings

## BF-GP-001: Minute cutoff hour-aware validation missing

**Severity**: Medium  
**Gate**: SIGNAL_INPUT_CUTOFF_ENFORCED  
**Status**: PARTIAL (not FAIL, detection worked but validation incomplete)

### Evidence

```
RAW: count=30, last=2021-06-01 10:00:00 (min=0)
FILTERED: count=30, last=2021-06-01 10:00:00 (leaked=0)
```

`_extract_minute(ts)` only checks `ts.minute`，不检查 `ts.hour`。结果：
- `09:00` → minute=0 → pass
- `10:00` → minute=0 → pass（**错误**）

Cutoff filter intended to reject bars ≥ 10:00, but `10:00` bar (minute=0) passed `<= 59` check.

### Root Cause

```python
def _extract_minute(ts):
    try:
        return ts.minute
    except AttributeError:
        return int(str(ts)[-5:-3])
```

Hour component not validated. `10:00` and `09:00` indistinguishable.

### Impact

Signal input cutoff enforcement is **partial** — rejects bars with minute ≥ 60 (impossible), but accepts 10:00 bar. This is a **validation design gap**, not a platform limitation.

### Classification

- **Layer**: Consumer (Golden Pit Signal Input Validation)
- **Not a platform issue**: JoinQuant `get_price(end_date=10:00)` correctly returns bars including 10:00
- **Provider behavior**: ✅ as expected
- **Consumer validation**: ❌ incomplete

### Recommendation

Add hour-aware check:
```python
filtered_indices = [i for i in bars.index 
                    if i.hour < 10 or (i.hour == 9 and i.minute <= 59)]
```

Do NOT fix until after Stage 2/3 evidence collection complete.

---

## BF-GP-002: Intraday smoke symbol selection fragile

**Severity**: High (blocks Gate validation)  
**Gate**: Intraday-order execution (ORDER_ACCEPTED / FILL_VERIFIED)  
**Status**: FAIL (no order execution evidence)

### Evidence

```
2021-06-01 10:05:00 - ERROR - [SMOKE-3] ORDER FAILED: no current_data for 000001.XSHE
2021-06-02~07: SIGNAL_GENERATED, but no ORDER/FILL logs
```

`pool[0]` = `000001.XSHE`, unavailable in `get_current_data()` at 10:05 分钟回测. Script sets `g.test_done = True` immediately, blocking all subsequent days.

### Root Cause

```python
pool = get_index_stocks('000300.XSHG')
test_stock = pool[0]  # ← hard-coded, no fallback
if test_stock not in cd:
    g.order_status = 'FAIL'
    g.test_done = True  # ← blocks retry
    return
```

Smoke depends on **single symbol availability**. One unavailable symbol → entire order chain untested.

### Impact

Cannot verify:
- ORDER_REQUESTED → ORDER_ACCEPTED → FILL_VERIFIED
- data_cutoff_time < signal_time < order_time <= fill_time

**No execution evidence produced.**

### Classification

- **Layer**: Smoke test design (not platform limitation)
- **Current evidence**: Only proves `000001.XSHE` unavailable in this context
- **Platform-wide limitation**: Not proven (need more symbols tested)

### Recommendation

Iterate over pool until `get_current_data()` returns non-empty:
```python
for stock in pool[:10]:
    if stock in cd and not cd[stock].paused:
        test_stock = stock
        break
```

Do NOT fix until after Stage 2/3 evidence collection complete.

---

## Stage 2 Evidence Verdict

| Gate | Status | Rationale |
|------|:--:|-----------|
| Minute-bar availability | ⚠️ PARTIAL PASS | Provider data ✅; cutoff validation incomplete (BF-GP-001) |
| Intraday-order execution | ❌ FAIL | No order/fill evidence (BF-GP-002) |
| **Stage 2** | **PARTIAL / NOT VERIFIED** | Data chain partially proven; execution chain not proven |

### Why PARTIAL not FAIL

- Minute bar **data availability** confirmed (5 days × 30 bars)
- Signal cutoff **intent correct**, implementation gap detected
- Order execution **capability blocked**, not proven unavailable

### Next Window

After Stage 3 evidence collection, batch-fix BF-GP-001 + BF-GP-002, re-run Stage 2 only.

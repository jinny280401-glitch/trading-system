# Platform Smoke Gate Manifest — v0.2.1

```
REQUIRED_GATES = [
    "after_close",
    "minute_bar",
    "intraday_order",
    "historical_constituents",
    "slippage",
]
```

## 总判定规则

```python
# 先验证 manifest 完整
assert set(REQUIRED_GATES) == set(gate_status.keys())   # 无缺失、无额外
assert all(gate_status[g] in ALLOWED_STATUS for g in REQUIRED_GATES)

# 总 PASS 条件
platform_smoke_pass = all(gate_status[g] == "PASS" for g in REQUIRED_GATES)
```

`ALLOWED_STATUS = {NOT_RUN, PENDING, PASS, PARTIAL, FAIL, BLOCKED}`
任一 gate 非 PASS → 总状态非 PASS。

## 各 Gate 内部子判定

| Gate | 子判定 | 阻塞? |
|------|--------|:--:|
| after_close | ≥3 交易日 + 每日 1 次 + 无重复 | — |
| **minute_bar** | BAR_COUNT_VALID + LAST_BAR_CLOSED + **SIGNAL_INPUT_CUTOFF_ENFORCED** | 三项全阻塞 |
| minute_bar (obs) | include_now via get_bars | **NON-BLOCKING** (PLATFORM_OBSERVATION) |
| intraday_order | ORDER_ACCEPTED + FILL_VERIFIED + 严格时间链 (cutoff<signal<order≤fill) | 阻塞 |
| historical_constituents | HISTORICAL_DATE_EFFECTIVE + CONSTITUENT_SET_CHANGED + NO_FUTURE_CONTEXT_LEAKAGE + HISTORICAL_TRADABILITY_AVAILABLE | 四项全阻塞 |
| slippage | 3 脚本各 PASS + compare 模板 READY FOR COMPARISON | 阻塞 |

## v0.2.1 变更

- minute_bar: `INCLUDE_NOW_BEHAVIOR_OBSERVED` → 拆为 `SIGNAL_INPUT_CUTOFF_ENFORCED`(阻塞) + `include_now`(观察/非阻塞)
- intraday_order: signal 与 order 时间分离 (10:01 / 10:05)，严格 `<` 比较
- slippage: 补 trade_id + compare_slippage_results.md

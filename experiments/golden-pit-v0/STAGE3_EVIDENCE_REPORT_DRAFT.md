# Golden Pit Stage 3 Evidence Report Draft

> Window: `D23 Stage 3 Evidence Collection`  
> Recorded: `2026-07-23` (Asia/Shanghai)  
> Mode: `EVIDENCE ONLY`  
> Scope: execution status, Atomic Gates, evidence, failure/caveat  
> Non-scope: finding repair, cutoff change, stock-pool change, tuning, hypothesis or metric change, and strategy-validity conclusions

## 1. Run Matrix

| Smoke | Frozen script SHA-256 | Platform setup | Execution | Atomic Gate result |
|---|---|---|---|---|
| `SMOKE-4` historical constituents | `a2f0716183185ca11fe0c3b9e48785aa43f347969aa35521d169b429d7f94df3` | 2021-06-28 to 2025-07-02; minute; CNY 100,000; Python 3 | Platform run completed in 01:31 | `PARTIAL / NOT FULLY VERIFIED` |
| `SMOKE-5a` NoSlippage | `3a8ecbba17071c1185aa27669f4ed5fd1084befd360e053a902a6d59a8eda55b` | 2021-06-01 to 2021-06-03; minute; CNY 100,000; Python 3 | Platform run completed in 00:03 | `FAIL` |
| `SMOKE-5b` FixedSlippage | `e7e1d1395ad849dc6641fddb02e63c671856ee10150ec20391dfb929aca36edc` | 2021-06-01 to 2021-06-03; minute; CNY 100,000; Python 3 | Platform run completed in 00:03 | `FAIL` |
| `SMOKE-5c` PriceRelatedSlippage | `26ec56ada160fb057485b706d467a475e728ade96a270ac18a3141a51aaeb875` | 2021-06-01 to 2021-06-03; minute; CNY 100,000; Python 3 | Platform run completed in 00:03 | `FAIL` |

`Execution completed` means that the JoinQuant backtest process reached its completed state. It does not mean that the script's Atomic Gates passed.

## 2. SMOKE-4 — Historical Constituents

### Execution

`SUCCESS` at the platform-process level. The requested date range, minute frequency, and CNY 100,000 capital were shown on the completed backtest.

### Atomic Gates

| Atomic Gate | Status | Evidence |
|---|---|---|
| `HISTORICAL_DATE_EFFECTIVE` | `PASS` | The completed log exposes different combined constituent hashes across historical dates, including `a58a37c95a53` and `bf8bb8bf0c39`. |
| `CONSTITUENT_SET_CHANGED` | `PASS` | The combined historical constituent hash changes between observed periods; the frozen gate derives set change from the first and latest stored HS300/ZZ500 sets. |
| `NO_FUTURE_CONTEXT_LEAKAGE` | `PASS` | Frozen code executes `set_option('avoid_future_data', True)` before collection and records this Atomic Gate as PASS. |
| `HISTORICAL_TRADABILITY_AVAILABLE` | `NOT VERIFIED` | Retrieved platform log lines repeatedly show `tradable=0`; the UI did not expose a conclusive final Gate Summary line in the retained log view. |

### Evidence

- JoinQuant backtest ID: `09c2e37ab46e3365b0f7eeab629aaa22`.
- Platform state: `回测完成`; actual time `01分31秒`.
- Platform settings: `2021-06-28 到 2025-07-02，￥100000，分钟`.
- Observed constituent counts: HS300 `300`; ZZ500 `500`.
- Observed hash transition: `a58a37c95a53` to `bf8bb8bf0c39`.
- Observed caveat samples repeatedly report `tradable=0`.

### Failure / Caveat

The platform's retained log view did not expose the final `[SMOKE-4] GATES` and `[SMOKE-4] OVERALL` lines. Because historical tradability evidence is not affirmatively visible, SMOKE-4 is not promoted to overall PASS. No repair or reinterpretation is made in this window.

## 3. SMOKE-5a — NoSlippage

### Execution

`SUCCESS` at the platform-process level; `FAIL` at the Atomic Gate level.

### Atomic Gates

| Atomic Gate | Status | Evidence |
|---|---|---|
| Reference price captured | `FAIL` | No current-data object was available for the selected symbol at 10:01. |
| Order accepted | `NOT REACHED` | Execution exited before order placement. |
| Fill verified | `NOT REACHED` | No order/fill chain was created. |
| Strict time chain | `NOT VERIFIED` | No order or fill timestamp existed. |
| Model result | `FAIL` | Required NoSlippage result line was not emitted. |

### Evidence

- JoinQuant backtest ID: `0628a38c27af13d0f26697e1c878de02`.
- Platform state: `回测完成`; actual time `00分03秒`.
- Log: `2021-06-01 10:01:00 - ERROR - [SMOKE-5a] FAIL: no current_data for 000001.XSHE`.

### Failure / Caveat

The run did not reach order or fill verification. This report records the failure only and does not modify the frozen stock-pool logic.

## 4. SMOKE-5b — FixedSlippage

### Execution

`SUCCESS` at the platform-process level; `FAIL` at the Atomic Gate level.

### Atomic Gates

| Atomic Gate | Status | Evidence |
|---|---|---|
| Reference price captured | `FAIL` | No current-data object was available for the selected symbol at 10:01. |
| Order accepted | `NOT REACHED` | Execution exited before order placement. |
| Fill verified | `NOT REACHED` | No order/fill chain was created. |
| Strict time chain | `NOT VERIFIED` | No order or fill timestamp existed. |
| Fixed offset verified | `NOT VERIFIED` | No fill price existed for comparison. |
| Model result | `FAIL` | Required FixedSlippage result line was not emitted. |

### Evidence

- JoinQuant backtest ID: `4f84c8182f1ebee74d9bc8af85a7a4e6`.
- Platform state: `回测完成`; actual time `00分03秒`.
- Log: `2021-06-01 10:01:00 - ERROR - [SMOKE-5b] FAIL: no current_data for 000001.XSHE`.

### Failure / Caveat

The run did not reach order, fill, or fixed-offset verification. No parameter or selection-logic change is made.

## 5. SMOKE-5c — PriceRelatedSlippage

### Execution

`SUCCESS` at the platform-process level; `FAIL` at the Atomic Gate level.

### Atomic Gates

| Atomic Gate | Status | Evidence |
|---|---|---|
| Reference price captured | `FAIL` | No current-data object was available for the selected symbol at 10:01. |
| Order accepted | `NOT REACHED` | Execution exited before order placement. |
| Fill verified | `NOT REACHED` | No order/fill chain was created. |
| Strict time chain | `NOT VERIFIED` | No order or fill timestamp existed. |
| Proportional offset verified | `NOT VERIFIED` | No fill price existed for comparison. |
| Model result | `FAIL` | Required PriceRelatedSlippage result line was not emitted. |

### Evidence

- JoinQuant completed-run page: strategy `这是一个简单的策略-12`.
- Platform state: `回测完成`; actual time `00分03秒`.
- Platform settings: `2021-06-01 到 2021-06-03，￥100000，分钟`.
- Log: `2021-06-01 10:01:00 - ERROR - [SMOKE-5c] FAIL: no current_data for 000001.XSHE`.

### Failure / Caveat

The run did not reach order, fill, or proportional-offset verification. No parameter or selection-logic change is made.

## 6. Stage 3 Draft Status

| Item | Status |
|---|---|
| Four requested platform executions | `COMPLETED` |
| SMOKE-4 overall Atomic Gate | `PARTIAL / NOT FULLY VERIFIED` |
| SMOKE-5 three-script gate | `FAIL` |
| Slippage comparison readiness | `BLOCKED` |
| BF-GP-001 remediation | `NOT PERFORMED` |
| BF-GP-002 remediation | `NOT PERFORMED` |
| Experiment definition changes | `NONE` |
| Strategy-validity conclusion | `NOT MADE` |

This draft is an evidence record, not an authorization to repair or rerun Stage 2 and not a Platform Smoke PASS report.

# Golden Pit Experiment v0.2 — Final Smoke Evidence Report

> Date: `2026-07-23` (Asia/Shanghai)  
> Status: `FINAL / WINDOW CLOSED`  
> Overall Platform Smoke: `PARTIAL / NOT VERIFIED`  
> Final Claim: `NOT MADE`

## 1. Purpose

This report closes the authorized Golden Pit Smoke evidence window. It records what the frozen experiment demonstrated, what it did not demonstrate, and which findings remain open.

It does not repair the experiment, redefine a gate, or make a strategy-effectiveness claim.

## 2. Final Gate Summary

| Gate | Final status | Evidence boundary |
|---|---|---|
| After-close scheduling | `VERIFIED` | Stage 1 evidence established the scheduled after-close callback within its recorded test scope. |
| Minute-data availability | `VERIFIED` | Five trading days each returned 30 minute bars from `09:31:00` through `10:00:00`. This verifies availability, not the cutoff rule. |
| Signal-input cutoff enforcement | `PARTIAL / NOT VERIFIED` | The frozen minute-only validator accepted the `10:00:00` bar; hour-aware enforcement was not proved. |
| Historical constituent date handling | `VERIFIED` | SMOKE-4 observed different constituent hashes across historical periods, establishing that historical date selection affected the returned set. |
| Historical tradability reconstruction | `NOT VERIFIED` | Retained SMOKE-4 evidence repeatedly showed `tradable=0` and did not expose a conclusive final Atomic Gate summary. |
| Intraday order execution | `NOT VERIFIED` | The selected `pool[0]` symbol, `000001.XSHE`, was unavailable from `get_current_data()`; no order request was reached. |
| Fill chain | `NOT VERIFIED` | No accepted order, fill, or fill timestamp evidence exists. |
| Strict execution time chain | `NOT VERIFIED` | `data_cutoff < signal < order <= fill` could not be evaluated without order/fill evidence. |
| Slippage comparison | `NOT VERIFIED / BLOCKED` | None, fixed, and price-related runs all stopped at the same unavailable-symbol condition before fill comparison. |
| Strategy effectiveness | `NOT VERIFIED` | Smoke evidence is operational evidence and contains no valid return, alpha, profitability, or trading-effectiveness proof. |

## 3. Verified Evidence

### After-close scheduling

The previously accepted Stage 1 gate remains PASS within its original scope. This report does not broaden that scope.

### Minute-data availability

Across `2021-06-01`, `2021-06-02`, `2021-06-03`, `2021-06-04`, and `2021-06-07`, the runtime returned:

```text
count=30
first=09:31:00
last=10:00:00
```

This establishes that minute data was returned. It does not establish that the `10:00:00` bar was legally eligible as signal input.

### Historical constituent date handling

The completed SMOKE-4 run covered `2021-06-28` through `2025-07-02` at minute frequency with CNY 100,000. Observed HS300 and ZZ500 counts were `300` and `500`, and the combined constituent hash changed between observed historical periods, including:

```text
a58a37c95a53
bf8bb8bf0c39
```

This verifies historical date handling and set change only. It does not verify historical tradability reconstruction or absence of every form of future leakage.

## 4. Not Verified

The following capabilities remain outside the verified boundary:

- hour-aware cutoff enforcement;
- complete absence of time leakage;
- historical tradability reconstruction;
- intraday order request and acceptance;
- fill completion and fill timestamp ordering;
- none/fixed/price-related slippage comparison;
- Golden Pit strategy effectiveness, profitability, alpha, or production readiness.

## 5. Findings

### BF-GP-001 — Minute cutoff hour-aware validation missing

| Field | Final value |
|---|---|
| Status | `OPEN / UNFIXED` |
| Severity | `MEDIUM` |
| Gate impact | Signal-input cutoff `PARTIAL / NOT VERIFIED` |

The validator compared only the minute component. `09:00` and `10:00` both resolve to minute `0`, allowing the `10:00:00` bar to pass a rule intended to enforce an hour-aware boundary.

### BF-GP-002 — Intraday smoke symbol selection fragile

| Field | Final value |
|---|---|
| Status | `OPEN / UNFIXED` |
| Severity | `HIGH` |
| Gate impact | Execution and slippage chains `NOT VERIFIED` |

The frozen scripts depend on `pool[0]`, which resolved to `000001.XSHE`. The runtime returned no current-data object for that symbol, so the experiment did not reach order or fill verification.

The three SMOKE-5 executions reproduced the same blocking condition:

```text
[SMOKE-5a] FAIL: no current_data for 000001.XSHE
[SMOKE-5b] FAIL: no current_data for 000001.XSHE
[SMOKE-5c] FAIL: no current_data for 000001.XSHE
```

Additional unchanged runs would test the same fixed selection and therefore add little new evidence.

## 6. Evidence References

| Artifact | Role |
|---|---|
| `STAGE2_SMOKE_EVIDENCE_CLOSE_CARD.md` | Stage 2 observed evidence, boundary, and findings |
| `STAGE3_EVIDENCE_REPORT_DRAFT.md` | SMOKE-4/5 execution records and Atomic Gate evidence |
| `platform_smoke/GATE_MANIFEST.md` | Frozen gate contract |
| `platform_smoke/FINDINGS_STAGE2.md` | Finding definitions and impact |

Stage 3 platform references recorded in the draft include:

- SMOKE-4 backtest: `09c2e37ab46e3365b0f7eeab629aaa22`
- SMOKE-5a backtest: `0628a38c27af13d0f26697e1c878de02`
- SMOKE-5b backtest: `4f84c8182f1ebee74d9bc8af85a7a4e6`
- SMOKE-5c: completed strategy-12 run, `2021-06-01` to `2021-06-03`, minute, CNY 100,000

## 7. Final Claim

```text
Golden Pit Experiment v0.2
Overall Platform Smoke: PARTIAL / NOT VERIFIED
BF-GP-001: OPEN / UNFIXED
BF-GP-002: OPEN / UNFIXED
Strategy effectiveness: NOT VERIFIED
Final Claim: NOT MADE
```

The valid conclusion is not that the strategy works or fails. The valid conclusion is:

> Until the complete data-to-signal-to-order-to-fill chain is evidenced, Golden Pit does not make a strategy-validity claim.

## 8. Window Closure

The Golden Pit Smoke evidence window is now `CLOSED`.

- No additional unchanged smoke runs are authorized by this report.
- No finding is reclassified or closed.
- Any repair or rerun requires a separately authorized research window.
- This closure records experiment governance; it is not a Platform Smoke PASS.

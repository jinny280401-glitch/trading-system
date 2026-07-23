# Stage 2 Smoke Evidence Close Card

**Date**: 2026-07-23  
**Mode**: Evidence close only  
**Stage verdict**: `PARTIAL / NOT VERIFIED`

## 1. Observed Evidence

### Smoke 2: Minute Bar Boundary

Across five trading days (`2021-06-01`, `2021-06-02`, `2021-06-03`, `2021-06-04`, `2021-06-07`), the runtime returned the same shape:

```text
count=30
first=09:31:00
last=10:00:00
last_min=0
filtered_count=30
leaked=0
```

The `10:00:00` bar passed both `LAST_BAR_CLOSED` and `SIGNAL_INPUT_CUTOFF_ENFORCED`. The emitted `PASS` labels are script outputs and are not accepted as final Evidence Gate conclusions.

### Smoke 3: Intraday Execution

```text
2021-06-01 10:01:00 - INFO  - [SMOKE-3] SIGNAL_GENERATED at 2021-06-01 10:01:00
2021-06-01 10:05:00 - ERROR - [SMOKE-3] ORDER FAILED: no current_data for 000001.XSHE
2021-06-02 10:01:00 - INFO  - [SMOKE-3] SIGNAL_GENERATED at 2021-06-02 10:01:00
2021-06-03 10:01:00 - INFO  - [SMOKE-3] SIGNAL_GENERATED at 2021-06-03 10:01:00
2021-06-04 10:01:00 - INFO  - [SMOKE-3] SIGNAL_GENERATED at 2021-06-04 10:01:00
2021-06-07 10:01:00 - INFO  - [SMOKE-3] SIGNAL_GENERATED at 2021-06-07 10:01:00
```

Observed execution boundary:

```text
SIGNAL_GENERATED: observed
ORDER_REQUESTED: not observed
ORDER_ACCEPTED: not observed
FILL_VERIFIED: not observed
```

## 2. Gate Status

| Gate | Status | Evidence boundary |
|---|---|---|
| Minute-bar availability | `PARTIAL PASS` | Five trading days returned 30 minute bars. The returned interval included `10:00:00`. |
| Signal cutoff enforcement | `PARTIAL` | The script reported no leak, but its minute-only comparison accepted the `10:00:00` bar. |
| Intraday order execution | `FAIL` | Candidate `000001.XSHE` was unavailable from `get_current_data()`; no order request was reached. |
| Fill verification | `NOT VERIFIED` | No accepted order or fill evidence exists. |

Stage 2 remains `PARTIAL / NOT VERIFIED`. It is neither accepted as `PASS` nor generalized as a complete platform failure.

## 3. Findings

### BF-GP-001: Minute cutoff hour-aware validation missing

| Field | Value |
|---|---|
| Category | Signal Input Boundary |
| Status | `OPEN` |
| Severity | `MEDIUM` |
| Capability impact | Signal boundary `NOT VERIFIED` |

**Evidence**

Five trading days produced the same boundary result: `count=30`, `first=09:31`, `last=10:00`. The `10:00` bar passed cutoff validation.

**Root cause**

`_extract_minute()` evaluates only the minute field. Both `10:00` and `09:00` resolve to minute `0`, so the current filter cannot enforce an hour-aware `<= 09:59` boundary.

**Impact**

`SIGNAL_INPUT_CUTOFF_ENFORCED` cannot be considered fully verified. A post-cutoff bar may be treated as valid signal input.

### BF-GP-002: Intraday smoke symbol selection fragile

| Field | Value |
|---|---|
| Category | Execution Validation |
| Status | `OPEN` |
| Severity | `HIGH` |
| Capability impact | Intraday execution chain `NOT VERIFIED` |

**Evidence**

```text
pool[0]=000001.XSHE
get_current_data() unavailable during minute backtest
ORDER_REQUESTED not observed
ORDER_ACCEPTED not observed
FILL_VERIFIED not observed
```

**Root cause**

The smoke depends on a single candidate selected as `pool[0]`. It does not discover a symbol that is executable in the current backtest context.

**Impact**

The runtime did not reach order acceptance or fill verification. No conclusion can be made about the intraday execution chain beyond signal generation.

## 4. Current Capability Boundary

Stage 2 currently proves only that the minute callback runs and minute-bar data is returned for the tested dates. It does not prove:

- an hour-aware signal-input cutoff;
- absence of time leakage;
- intraday order acceptance;
- fill completion or fill timestamp ordering;
- Golden Pit strategy effectiveness or profitability.

The current result is a governance finding, not a return-performance result. The experiment remains focused on proving that the signal chain has no time leakage and that the execution chain has no false appearance of completion.

## 5. Next Window Scope

Record only; no repair is authorized by this close card.

### Priority 1: BF-GP-001

Required:

- use hour-aware full timestamp comparison;
- verify the accepted input boundary against `09:59:00` explicitly.

Forbidden:

- continue using a minute-only parser for cutoff enforcement.

### Priority 2: BF-GP-002

Required:

- discover an executable symbol in the current runtime context;
- do not assume `pool[0]` is available or tradable.

Any repair, rerun, or expanded sample requires a separate authorized window.

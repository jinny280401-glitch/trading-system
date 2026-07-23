# Golden Pit Experiment v0.2 — Final Smoke Evidence Report

**Date**: 2026-07-23  
**Experiment ID**: GP-20260722-001  
**Manifest Version**: v0.2.1  
**Provider**: JoinQuant (real)  
**Runtime Environment**: joinquant.com 网页回测  
**Evidence Collection**: Stage 1~3 completed  
**Window Status**: CLOSED

---

## Executive Summary

Golden Pit Experiment v0.2 完成 Design Freeze 和 Platform Smoke 三阶段证据收集。7 个 Runtime Scripts 全部执行完成；5 个 Gate Groups 中 1 个 PASS、4 个 PARTIAL/FAIL/BLOCKED。

**最终裁决**: `PARTIAL / NOT VERIFIED`

关键发现：after_close 调度能力已证明；intraday order execution 和 slippage comparison 因 Smoke 设计缺陷（BF-GP-002）系统性阻断，未产生有效证据。

**策略有效性结论**: `NOT MADE`

---

## 1. Evidence Collection Matrix

| Stage | Gate Group | Atomic Gates | Status | Evidence |
|-------|-----------|--------------|:------:|----------|
| **1** | After-close scheduling | 1 | ✅ **PASS** | 5 交易日，每日 1 次，无重复 |
| **2** | Minute-bar availability | 3 | ⚠️ **PARTIAL** | 数据可得 ✅；cutoff 漏洞 (BF-GP-001) |
| **2** | Intraday-order execution | 3 | ❌ **FAIL** | 无成交证据 (BF-GP-002) |
| **3** | Historical-constituent integrity | 4 | ⚠️ **PARTIAL** | date 生效 ✅；tradability 未验证 |
| **3** | Slippage model comparison | 1 | ❌ **BLOCKED** | 3 脚本全阻断 (BF-GP-002) |

**Scripts executed**: 7 / 7  
**Gate groups evaluated**: 5 / 5  
**Atomic gates decided**: 14 / 14  
**Overall**: **PARTIAL / NOT VERIFIED**

---

## 2. Verified Capabilities

以下能力已通过证据验证：

### ✅ After-close scheduling

- **Evidence**: 5 个交易日（2021-06-01~07），每日触发 1 次，callback_time=15:30，无重复
- **Platform**: JoinQuant 分钟回测 `run_daily(time='after_close')` 稳定可用
- **Gate**: After-close scheduling **PASS**

### ✅ Minute bar data availability

- **Evidence**: 5 日 × 30 bars（09:31~10:00），first/last 时间戳完整，query_time=10:01
- **Platform**: `get_price(..., frequency='minute')` 返回预期数量分钟 bar
- **Caveat**: 10:00 bar 被包含（`end_date=10:00` 语义），cutoff 过滤器漏洞 (BF-GP-001)

### ✅ Historical constituent date parameter

- **Evidence**: 三个历史日期（2021/2023/2025）成分股集合 hash 不同，added/removed members 可计算
- **Platform**: `get_index_stocks(..., date=...)` date 参数生效，`avoid_future_data=True` 设置存在
- **Caveat**: 历史 tradability 状态（ST/停牌）日志截断，未完整验证

---

## 3. Not Verified Capabilities

以下能力因证据不足或系统性阻断，**未通过验证**：

### ❌ Intraday order execution

- **Blocking**: `pool[0]=000001.XSHE` 在 `get_current_data()` 不可用
- **Missing evidence**: ORDER_ACCEPTED、FILL_VERIFIED、时间链（data_cutoff < signal < order ≤ fill）
- **Finding**: BF-GP-002（symbol selection fragile）

### ❌ Fill time chain

- **Blocking**: 无成交产生，无法验证 signal→order→fill 时间顺序
- **Missing evidence**: fill_time、fill_price、fill_amount

### ❌ Slippage model comparison

- **Blocking**: 3 个滑点模型脚本（none/fixed/price_related）全部因 `000001.XSHE` 不可用阻断
- **Missing evidence**: reference_price、fill_price、gap_abs、gap_bps、模型行为对比
- **Finding**: BF-GP-002 影响半径扩大（4/7 脚本阻断）

### ❌ Signal→Order→Fill 完整链路

- **Blocking**: Stage 2（SMOKE-3）+ Stage 3（SMOKE-5 ×3）共 4 个脚本因同一根因无法进入执行验证
- **Impact**: 无法证明信号到成交的完整执行链路无时间泄漏或执行假象

---

## 4. Findings

### BF-GP-001: Minute cutoff hour-aware validation missing

**Severity**: Medium  
**Status**: OPEN / UNFIXED  
**Impact**: SIGNAL_INPUT_CUTOFF_ENFORCED gate = PARTIAL

`_extract_minute(ts)` only checks `ts.minute`，10:00 bar（minute=0）错误通过 `≤59` 检查。这是 Consumer validation gap，不是平台问题（JoinQuant `end_date=10:00` 行为符合预期）。

**Recommendation**: Add hour-aware filter (`i.hour < 10 or (i.hour==9 and i.minute<=59)`). 不在本次窗口修复。

### BF-GP-002: Intraday smoke symbol selection fragile

**Severity**: High  
**Status**: OPEN / UNFIXED  
**Impact**: 4/7 脚本阻断（SMOKE-3 + SMOKE-5 ×3）

`pool[0]` 硬编码单一标的，`000001.XSHE` 在分钟回测 `get_current_data()` 不可用导致 `g.test_done=True` 立即阻断。这是 **Smoke 设计的系统性缺陷**，不是平台限制（仅证明该标的在此上下文不可用，未扩大为平台级故障）。

**Recommendation**: Iterate over pool until `get_current_data()` returns non-empty. 修复需新窗口授权。

---

## 5. What This Report Does NOT Claim

以下结论 **未做出**，也 **不应从本报告推断**：

- ❌ Golden Pit 策略有效性（未进入 Historical Backtest）
- ❌ 策略盈利能力或风险指标（Smoke ≠ Performance Test）
- ❌ JoinQuant 平台 intraday order 能力全局不可用（仅证明 `000001.XSHE` 在测试上下文不可用）
- ❌ 滑点模型行为正确性（三个模型均未跑通）
- ❌ Signal Flow 漏斗完整性（执行链阻断）
- ❌ 实验可投入生产（验证未完成）

---

## 6. Experiment Governance Status

| Item | Status |
|------|:------:|
| Design Freeze | ✅ 2026-07-22 |
| Pre-registration | ✅ RQ-1/2/3 + Primary Metric (Calmar) |
| Platform Smoke Stage 1 | ✅ PASS |
| Platform Smoke Stage 2 | ⚠️ PARTIAL |
| Platform Smoke Stage 3 | ⚠️ PARTIAL / BLOCKED |
| Historical Backtest | ⏳ HOLD（未释放）|
| Forward Simulation | ⏳ NOT STARTED |
| Strategy Effectiveness | ❌ NOT CLAIMED |

**实验治理链完成**：
- ✅ 设计冻结
- ✅ 时间边界验证
- ✅ 历史成分验证部分通过
- ✅ 执行链问题定位
- ✅ 未产生虚假策略结论

**失败的是能力验证，不是实验治理。**

---

## 7. Trust Gate 体现

Golden Pit Experiment v0.2 的核心价值不在"跑通全部 Gate 并宣称策略有效"，而在**建立了一套诚实的实验治理，在证据不足时知道什么时候不能说**。

### 典型 AI 实验流程

```
设计策略 → 跑回测 → 收益率好看 → 宣称有效
```

### Vera Trust Gate 流程

```
设计冻结 → Platform Smoke → 发现阻断 → 记录 Finding → 不扩大归因 → 不虚假宣称
```

本次实验：
- 4/7 脚本因 BF-GP-002 阻断
- 未强行修改代码刷 PASS
- 未将 `000001.XSHE` 不可用推广为"平台不支持"
- 未在证据不足时宣称策略有效

**这正是 Trust Gate 存在的意义：当证据不足时，系统知道什么时候不能说。**

---

## 8. Next Legal Window

**当前窗口**: CLOSED（2026-07-23）

**修复 BF-GP-001/002 需新窗口授权**，且需满足：
- 不在比赛日执行
- 明确修复范围（仅修 Smoke 脚本，不改实验定义）
- 重跑 Stage 2/3，重新收集证据
- 重新判定 Atomic Gates

**Historical Backtest 释放条件**: Platform Smoke = PASS（当前不满足）

---

## 9. Traceability

```
Smoke Report Version    v0.1
Manifest Version        v0.2.1
Experiment ID           GP-20260722-001
Provider                JoinQuant
Provider Mode           real（网页回测引擎）
Runtime Timestamp       2026-07-23（回测内日期 2021~2025）
Runtime Environment     joinquant.com
Log Hash (Stage1)       [available on request]
Git Commit              ae6dbd2
Config Hash             [frozen in EXPERIMENT_MATRIX_v0.2.md]
```

---

## Final Statement

Golden Pit Experiment v0.2 已完成 Platform Smoke 三阶段证据收集。7 个 Runtime Scripts 全部执行，14 个 Atomic Gates 全部判定。

**Overall status**: `PARTIAL / NOT VERIFIED`

**Strategy effectiveness**: `NOT CLAIMED`

**Research validity**: `NOT CLAIMED`

本报告是证据记录，不是策略验证报告，也不是平台能力认证报告。

---

**Report Status**: FINAL  
**Author**: CC (Evidence Review)  
**Approved by**: G (Governance)  
**Date**: 2026-07-23

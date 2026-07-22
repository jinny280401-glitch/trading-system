# SIGNAL_FORMULA_MAP v0.2

**Status**: FROZEN (2026-07-22)
**Rule**: 不在此映射中的条件不得进入实验。

## A. 黄金坑前置 P1-P5（S1 和 S3 使用）

| # | 条件 | 公式 | 字段 | 回看 | 已知时间 |
|---|------|------|------|------|----------|
| P1 | 20 日最大跌幅 ≥ 12% | `(min(close,20) - max(high,20)) / max(high,20) ≤ -0.12` | close, high | 20d | T 收盘 |
| P2 | 收盘 < MA20 | `close.iloc[-1] < MA(close,20).iloc[-1]` | close | 20d | T 收盘 |
| P3 | 距 60 日最低 ≤ 8% | `(close - min(low,60)) / min(low,60) ≤ 0.08` | close, low | 60d | T 收盘 |
| P4 | 5 日均量 < 20 日均量 | `MA(vol,5) < MA(vol,20)` | volume | 20d | T 收盘 |
| P5 | BBIBOLL 下轨 + 不加速跌 | `close ≤ lower×1.02 AND |ret_3d| ≤ |ret_1d|` | OHLC | 24d+11 | T 收盘 |

**BBIBOLL**: BBI = (MA3+MA6+MA12+MA24)/4, σ = std(close,11), band = 6σ

## B. 原始四重门 G1-G4（S2 使用）

从 `~/trading-system/config/settings.py` SIGNAL_COMBO 提取，参数不变：

| Gate | 条件 | 逻辑摘要 | 源码 |
|------|------|------|------|
| G1 | 涨停基因 | 近 120 日至少 1 次涨停（按板块 10%/20%/5% 阈值） | `factors/limit_up.py: LimitUpGene` |
| G2 | 回调充分 | 当前收盘价 < 最近一次涨停收盘价 | `factors/limit_up.py: BelowLimitUpPrice` |
| G3 | 整理充分 | 60 日振幅 ≤ 15% AND `|close-MA20|/MA20 ≤ 0.10` AND 5日量/前5日量 ≤ 0.80 | `factors/consolidation.py: Consolidation` |
| G4 | BBIBOLL 反弹 | 触及 BBIBOLL(N=11,M=6) 下轨 ≥ 1 日，当日 close > prev close | `factors/bbiboll.py: BBIBOLLLowerBounce` |

**注意**：G1-G4 ≠ P1-P5。G1/G2 包含涨停基因和回调确认，P1/P2 是纯跌幅和均线。

## C. 早盘确认 M1-M5（S3 使用）

| # | 条件 | 公式 | 数据源 | 判定时间 |
|---|------|------|------|------|
| M1 | 开盘涨幅 -2%~+2% | `(open - prev_close)/prev_close` | 09:25 开盘 + T-1 close | 10:01 |
| M2 | 价 > 开盘价 | `bar_10_close > open` | 09:30-09:59 min bars | 10:01 |
| M3 | 价 > 昨收 | `bar_10_close > prev_close` | min + T-1 close | 10:01 |
| M4 | ~~量比~~ 已移除 | — | — | — |
| M5 | 突破昨高 | `max(high,09:30-09:59) > prev_high` | min high + T-1 high | 10:01 |
| M6 | DEGRADED 市场环境 | `CSI300_T-1_close > CSI300_MA20` | T-1 index close | 09:00 |

**触发**: M1-M5 至少 3 项 AND M6 = True（不过滤只标注）。

## D. 退出 Exit-A / Exit-B（第二阶段使用）

| 退出 | 规则 | 执行 |
|------|------|------|
| Exit-A | 累计 3 阳线(close>open) + 至少 1 根量>MA20vol×1.5 + T+1 开盘 | after_close 判定 |
| Exit-B | 累计 4 阳线(close>open) + T+1 开盘 | after_close 判定 |

## E. 第一阶段退出（S0-S3 共用）

**Pure Fixed Hold 10 Trading Days**。不含止损、止盈、放量阳线或异常放量。

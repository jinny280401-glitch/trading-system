# Slipage Comparison Results

**Status**: PENDING EXECUTION（三份 Smoke 均未运行）

## Comparison Rules

| 条件 | 状态 |
|------|------|
| 三份结果均存在 AND 控制变量一致 | READY FOR COMPARISON |
| 三份结果缺任一份 | PARTIAL / NOT RUN |
| 控制变量不一致（股票/日期/时间/数量/方向/下单方式） | FAIL / NOT COMPARABLE |

## Control Variables (FROZEN)

| 变量 | 值 |
|------|-----|
| stock | `000300.XSHG` first constituent |
| date range | 2021-06-01 ~ 2021-06-03 |
| time | 09:31 |
| shares | 100 |
| side | buy |
| order method | `order(stock, 100)` |
| ref_price source | `get_current_data()[stock].last_price` |

## Results

| # | model_name | parameter | security | trade_date | order_time | side | amount | ref_price | fill_price | gap_abs | gap_bps | order_status | trade_id | evidence_present |
|---|-----------|-----------|----------|------------|------------|------|--------|-----------|------------|---------|---------|-------------|----------|:---:|
| 1 | NoSlippage | 0 | — | — | — | buy | 100 | — | — | — | — | — | — | ❌ |
| 2 | FixedSlippage | 0.001 (fixed price) | — | — | — | buy | 100 | — | — | — | — | — | — | ❌ |
| 3 | PriceRelatedSlippage | 0.001 (proportional) | — | — | — | buy | 100 | — | — | — | — | — | — | ❌ |

**Overall**: NOT RUN

## Interpretation Guide

After all three scripts have been run:

1. **NoSlippage**: gap should be ~0 (or very small, representing market microstructure noise)
2. **FixedSlippage(0.001)**: gap should be approximately 0.001 yuan per share (fixed price offset)
3. **PriceRelatedSlippage(0.001)**: gap should be approximately 0.1% of ref_price (proportional)

If NoSlippage ≈ 0 AND FixedSlippage ≈ 0.001 AND PriceRelatedSlippage ≈ ref_price × 0.001:
→ **SLIPPAGE MODEL VERIFIED** — 行为与参数语义一致

If any model's behavior contradicts its expected semantics:
→ **PARTIAL / FAIL** — 标注具体偏差

# Slippage Comparison Results

**用途**: 汇总 3 次独立回测结果，验证三种滑点模型的行为差异。
**状态**: TEMPLATE — 未填充（脚本尚未运行）

---

## 冻结参数（三次回测必须完全一致）

| 参数 | 值 |
|------|-----|
| 股票 | 000300.XSHG 成分股 pool[0] |
| 回测区间 | 2021-06-01 ~ 2021-06-03 |
| 频率 | 分钟 |
| 资金 | 1,000,000 |
| Signal 时间 | 10:01 |
| Order 时间 | 10:05 |
| 下单方式 | order_value(50000) |
| 方向 | BUY |
| 基准价格口径 | last_price at 10:01 (signal 时刻) |
| use_real_price | True |
| OrderCost | 统一（open_commission=0.0003 等） |

**唯一变量**: 滑点模型

---

## 结果表（运行后填充）

| 脚本 | model_name | parameter | reference_price | fill_price | absolute_gap | gap_ratio | side | order_status | trade_id | status |
|------|-----------|-----------|-----------------|-----------|--------------|-----------|------|--------------|----------|--------|
| smoke_slippage_none.py | NoSlippage | 0.0 | _TBD_ | _TBD_ | _TBD_ | _TBD_ | BUY | _TBD_ | _TBD_ | NOT_RUN |
| smoke_slippage_fixed.py | FixedSlippage | 0.01 | _TBD_ | _TBD_ | _TBD_ | _TBD_ | BUY | _TBD_ | _TBD_ | NOT_RUN |
| smoke_slippage_price_related.py | PriceRelatedSlippage | 0.001 | _TBD_ | _TBD_ | _TBD_ | _TBD_ | BUY | _TBD_ | _TBD_ | NOT_RUN |

---

## 验证断言（三份结果齐备后判定）

### Gate: SLIPPAGE_MODELS_DISTINCT

三个条件全部成立才可判 PASS：

1. **NoSlippage 基准**: `absolute_gap ≈ 0`（fill_price ≈ reference_price，仅受成交价格本身影响）
2. **FixedSlippage 为固定价偏移**: `absolute_gap ≈ parameter`（BUY 时 fill_price = base + fixed/2，与价格绝对值无关）
   - 判据: FixedSlippage 的 gap 不随 reference_price 变化，是固定值
3. **PriceRelatedSlippage 为比例偏移**: `gap_ratio ≈ parameter/2`（BUY 时按价格比例）
   - 判据: PriceRelatedSlippage 的 gap_ratio 稳定，absolute_gap 随价格线性变化
4. **方向符合预期**: BUY 时 fill_price ≥ reference_price（买入滑点向上）

### 判定规则

```
IF (none 三份 status 均为 PASS)
   AND (none.absolute_gap ≈ 0)
   AND (fixed.absolute_gap 为固定值且 > none.absolute_gap)
   AND (price_related.gap_ratio ≈ 0.0005)
   AND (三份 fill_price ≥ reference_price)
THEN SLIPPAGE_COMPARISON = PASS
ELSE SLIPPAGE_COMPARISON = FAIL / PARTIAL
```

**注意**: 聚宽 FixedSlippage(x) 表示买卖价差为 x，实际单边偏移为 x/2。
PriceRelatedSlippage(x) 表示买卖价差为 price*x，单边偏移为 price*x/2。
填充结果时需据此校验。

---

## 尚未验证声明

- [ ] 三份结果尚未产生（脚本 SCRIPT_READY_FOR_EXECUTION，未运行）
- [ ] 无法宣称 SLIPPAGE PASS
- [ ] 需在聚宽平台分别运行三个脚本，回填本表后才能判定

**当前 Gate 状态**: `SLIPPAGE_COMPARISON = NOT_RUN`

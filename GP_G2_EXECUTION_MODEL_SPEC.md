# GP_G2_EXECUTION_MODEL_SPEC — 交易执行模型规格

**TASK**: GP-G2-REMEDIATION-DESIGN-PRE3 · CC002/MAC-002 · STRICT_READ_ONLY · 2026-11-18  
**性质**: 执行模型缺口分析与最小修复规格。不修改代码。

---

## 一、涨跌停可成交性模型修订

### 1.1 PRE2 的简化假设及其问题

PRE2 中建议"用固定涨跌幅阈值等同于不可成交"，Owner 要求修订此方案。原因：

1. 涨停≠封板：涨停板被打开时当日可买卖
2. 跌停≠必须卖：持仓遇跌停可等次日
3. 竞价成交：集合竞价高开/低开不受涨跌停限制（如一字板开盘后第一笔成交）
4. 科创板/创业板规则不同：首日无涨跌停限制，之后 20% 限制

### 1.2 修订后的可成交性判断框架

```
买入可成交判断（T+1 开盘）：

  条件 A：tradestatus(T+1) == 1（非停牌）→ 基本可交易
  条件 B：open(T+1) 是否为涨停一字板
           = open(T+1) >= prev_close(T+1) × (1 + limit_pct − 0.001)
           limit_pct = 10% 主板 / 20% 创业板科创板 / 5% ST
  
  处理规则：
    若条件 A = False（停牌）：订单挂起，次日重试，最多 N 日
    若条件 A = True, 条件 B = False（非封板）：按 open 买入
    若条件 A = True, 条件 B = True（一字涨停板）：
      → 保守模式：跳过（无法成交）
      → 激进模式：排队申报，当日若有打开则按打开价成交
      → 建议：保守模式用于回测基准；激进模式作为敏感性对照

卖出可成交判断（持仓期）：

  条件 A：tradestatus == 1（非停牌）
  条件 B：当日是否为跌停一字板
           = open <= prev_close × (1 − limit_pct + 0.001)
  
  处理规则：
    若条件 A = False（停牌）：持仓延长，不计持仓天数，次日继续检查
    若条件 A = True, 条件 B = False：正常止损/止盈/到期卖出
    若条件 A = True, 条件 B = True（一字跌停板）：
      → 保守模式：持仓延长一天，次日重新判断
      → 最大延长天数：hold_days + 3（超过视为强制平仓，按次日 open 卖出）
```

### 1.3 涨跌停阈值定义（修订）

不使用固定 pctChg 阈值，改用价格比较：

```python
# 伪代码：不修改代码，仅作规格设计

def is_limit_up_board(open_price, prev_close, board_type):
    """判断是否为涨停一字板（开盘价 >= 涨停价）"""
    if board_type == 'STAR' or board_type == 'GEM':
        limit_pct = 0.20
    elif board_type == 'ST':
        limit_pct = 0.05
    else:
        limit_pct = 0.10
    limit_price = round(prev_close * (1 + limit_pct), 2)
    return open_price >= limit_price

def is_limit_down_board(open_price, prev_close, board_type):
    """判断是否为跌停一字板"""
    # 对称逻辑
    ...
```

此方案依赖 `preclose` 字段（当前缓存中不存在）。**这是 GAP 修复的前提数据需求之一。**

### 1.4 G2 特有风险：信号本身来自涨停事件

G2 要求过去 120 日内有涨停，T+1 买入时当日股票很可能仍处于强势，出现连续涨停的概率高于普通股票。因此 GAP-1（涨跌停可成交判断）对 G2 的影响**显著高于**G3（横盘筑底）和 G4（BBIBOLL 下轨）。

未建模此约束的后果：回测信号数虚高（实际部分信号无法成交），策略收益被系统性高估。

---

## 二、停牌处理

### 2.1 现有问题

`cache.py:73` 以 `volume>0` 过滤停牌日，把停牌日直接从 DataFrame 中删除。结果：
- 停牌期间行数缺失，日期序列不连续
- `consecutive_decline`（G3）的 rolling 计算会把停牌前后的行当做连续交易日处理，可能产生错误的连跌天数
- 持仓期遇停牌时，`hold_days` 天数计算按实际行数而非自然交易日

### 2.2 修订方案

```
方案：tradestatus 字段显式记录，不删除停牌日

  - 保留停牌日行，tradestatus=0
  - 停牌日：close/open/pctChg 填充为前收，volume=0
  - 信号计算时，停牌日信号强制设为 False（无法发出信号）
  - 持仓期计数按自然交易日计，停牌日不计为可交易日（持仓延长）
  - rolling 计算时，停牌日参与窗口计数但不参与信号产生

需要的字段：
  tradestatus（BaoStock 有，当前缓存无）
```

---

## 三、G2 状态信号向独立事件信号的转换

### 3.1 现有问题

`BelowLimitUpPrice.compute(df)` 是**状态信号**：只要价格低于最近涨停价且在窗口内，每日都输出 True。这导致：

- 一次"跌破涨停价"事件可持续触发 30~60 个信号日
- 回测中对同一波段重复买入（`run_portfolio` 在每个信号日都尝试开仓）
- 实际是一次连续持仓，但在回测统计中变成多笔交易，严重高估交易笔数和胜率

### 3.2 状态信号→独立事件信号的转换规则

```
事件定义：首次满足条件的交易日（前一日不满足，当日满足）

伪代码：
  signal_state = factor.compute(df)         # 现有的状态信号
  signal_event = signal_state & ~signal_state.shift(1).fillna(False)
  # signal_event = True 仅在状态从 False → True 的第一日

附加条件（避免极短暂穿越产生的假信号）：
  entry_cooldown = 20                        # 上一次同一股票信号后的冷却期（交易日）
  若距上次信号 < entry_cooldown，本次信号忽略

在组合回测中：
  对同一只股票，若已持仓，不重复买入
  对同一只股票，若上次卖出距今 < entry_cooldown，不重新买入
```

### 3.3 转换对回测结果的影响预估

| 维度 | 状态信号回测 | 事件信号回测 |
|---|---|---|
| 信号数量 | 大量重复 | 大幅减少 |
| 交易笔数 | 虚高 | 真实 |
| 胜率统计 | 失真（连续持仓拆成多笔） | 真实 |
| 持仓期 | 人工截断 | 自然持仓至止损/止盈/到期 |
| 统计意义 | 样本膨胀 | 独立样本，推断有效 |

---

## 四、成交价格模型

### 4.1 买入价格

| 情形 | 现有模型 | 修订模型 |
|---|---|---|
| 正常开盘 | T+1 open × (1 + slippage) | 同，合理 |
| 涨停一字板 | 未处理（仍按 open 买入） | 跳过或按打开价 |
| 低开（高开）跳空 | 按 open × (1+slippage) 买入 | 同，合理（open 已反映跳空） |
| 停牌 | 未处理 | 挂起，次日重试 |

### 4.2 卖出价格

| 情形 | 现有模型 | 修订模型 |
|---|---|---|
| 到期平仓 | close × (1 - slippage) | 改为 next_open，更保守 |
| 止损触发（`low <= stop_loss_price`） | 按 stop_loss_price 成交 | 若 open < stop_loss_price（跳空），按 open 成交 |
| 止盈触发（`high >= take_profit_price`） | 按 take_profit_price 成交 | 若 open > take_profit_price（跳空高开），按 open 成交 |
| 跌停一字板 | 未处理 | 持仓延长，次日重试，最多延长 3 日 |
| 退市 | 未处理 | 按退市前最后一个交易日收盘价强制平仓 |

---

## 五、执行模型缺口修复优先级清单

| ID | 缺口 | 对 G2 的影响 | 修复优先级 | 前提数据需求 |
|---|---|---|---|---|
| GAP-1 | 涨跌停一字板可成交判断 | 高（G2 信号源自涨停） | P0 | `preclose`, `tradestatus` |
| GAP-2 | 停牌期持仓延长 | 中 | P0 | `tradestatus` |
| GAP-3 | 跳空止损按 open 成交 | 高 | P0 | 无新需求 |
| GAP-4 | 状态信号→事件信号转换 | 高（消除信号重复） | P0 | 无新需求（逻辑修改） |
| GAP-5 | 组合回测每日清算 | 中 | P1 | 无新需求 |
| GAP-6 | 退市强制平仓 | 低（短窗口回测） | P2 | 退市日历 |
| GAP-7 | 到期平仓改用 next_open | 低 | P2 | 无新需求 |

---

## 六、最终状态

```
EXECUTION_MODEL_ANALYZED   = YES
GAP_COUNT                  = 7（P0×4 / P1×1 / P2×2）
DATA_DEPENDENCY_FOR_P0     = preclose + tradestatus（均在 BaoStock 有但未缓存）
SPEC_FOR_OWNER_REVIEW       = READY
EXECUTION_REMEDIATION_READY = PARTIAL（规格完整；实现需 Owner 授权独立任务卡）
CODE_MODIFIED              = NO
```

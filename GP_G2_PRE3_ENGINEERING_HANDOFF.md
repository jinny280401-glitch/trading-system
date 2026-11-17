# GP_G2_PRE3_ENGINEERING_HANDOFF

**生成**: CC002 / MAC-002 · 2026-11-18  
**仓库**: `trading-system` HEAD `05a54ad`  
**任务**: GP-G2-REMEDIATION-DESIGN-PRE3 Handoff 收口  
**上游状态**: PRE3_REPORT = RECEIVED_PENDING_REVIEW · BACKTEST_AUTHORIZED = NO

---

## 一、PRE2 → PRE3 修订记录

| 修订项 | PRE2 结论 | PRE3 修正 | 依据 |
|---|---|---|---|
| pctChg 字段语义 | 预设前视污染已发生（前复权破坏涨停检测） | **撤回**：pctChg 为独立原始字段，不随 adjustflag 变化 | BaoStock demo 字段列表；pctChg 由原始 close/preclose 推导 |
| 前视风险来源 | pctChg 阈值检测前视 | **修正为口径漂移**：`limit_up_price = close_adj.where(is_lu).ffill()` 用前复权 close 保存锚点，新除权事件回溯修改 close → 信号位置随下载时点漂移 | 前复权机制分析 |
| 涨跌停成交判断 | 固定 pctChg 阈值直接判断不可成交 | **废弃**：改为 `open >= prev_close × (1 + limit_pct)` 价格比较 | Owner 要求"不得简单使用固定涨跌幅阈值等同于不可成交" |
| 状态信号处理 | 未设计（持续状态信号直接用于回测） | **新增**：首次触发 + 20 日冷却期的事件信号转换规则 | Owner 要求"设计 G2 状态信号向独立事件信号的转换规则" |
| IS/OOS | 基础 9M/6M 切分，无预热 | **修订**：加入 120 日预热期、等权基准、参数稳定性、四个负控 | Owner 要求"加入历史预热、市场 Beta、行业 Beta、参数稳定性和负控" |

---

## 二、pctChg 字段语义证据及尚未验证事项

### 已确认（代码级证据）

- **来源**：BaoStock 官方 demo `demo_A_stock_k_data.py` 中，`pctChg` 与 `adjustflag` 同时作为独立参数出现在 fields 列表中，demo 以 `adjustflag="3"`（不复权）请求数据时仍返回 `pctChg`
- **推导基础**：BaoStock 文档及 demo 表明 `pctChg = (close_raw - preclose_raw) / preclose_raw × 100`，基于原始（不复权）价格
- **当前缓存**：`cache.py:54` 以 `adjustflag="2"`（前复权）请求同时获取 `pctChg`，但 `pctChg` 值本身不受复权模式影响

### 尚未验证（待授权后执行）

| 验证项 | 方法 | 预期结果 |
|---|---|---|
| VERIFY-1 | 同一 ticker 以 adjustflag="1"/"2"/"3" 分别拉取，对比 pctChg 值 | 三版本完全相同（±浮点误差） |
| VERIFY-2 | 除权日对比 `close_adj.pct_change() × 100` 与 `pctChg` 的差值 | 除权日 `close_adj.pct_change()` 偏离 `pctChg`，证明 close 确已前复权 |

若 VERIFY-1 显示 pctChg 随 adjustflag 变化 → 需重新评估涨停检测前视风险。

---

## 三、前复权锚点漂移的验证方案

### 问题描述

```
limit_up_price = close_adj.where(is_lu).ffill()
```

`close_adj` 在每次新除权事件发生后会回溯修改历史值，导致：
- 同一历史日期的 `limit_up_price` 在不同下载时点计算结果不同
- 信号触发位置（`close < limit_up_price`）发生漂移
- 回测结果不可复现

### 验证方案

```
步骤：
  1. 对一只在回测窗口内有明确除权事件的股票，以当前时间拉取前复权日线
  2. 记录除权事件发生前 10 日的 close_adj 值（snapshot A）
  3. 等待下一次除权事件（或模拟：手工修改调整因子）后重新拉取
  4. 对比同一历史日期的 close_adj（snapshot B vs A）
  5. 若 snapshot A ≠ snapshot B → 锚点漂移已确认

判定标准：
  - 漂移 < 0.1%：可接受，视为数值稳定
  - 漂移 ≥ 0.1%：需切换到不复权 close 保存锚点
```

### 解决方案（已设计）

**方案 A（推荐）**：改用 `adjustflag="3"`（不复权）的 `close_raw` 保存涨停价锚点：
```python
# 伪代码
close_raw = df["close_raw"]           # 不复权 close（需补拉）
limit_up_price_raw = close_raw.where(is_lu).ffill()
signal = (close_raw < limit_up_price_raw) & in_window  # 两边同口径
```

**方案 B（次选）**：固定复权基准日并冻结数据（不再增量更新）。

---

## 四、PIT 股票池补齐需求

### 现状

4,919 只 parquet 均为当前存续股（2026-11 时点），三条缓存构建路径均无历史 PIT 逻辑：
- `cmd_warmup`：东财实时快照（当日活跃股）
- `cmd_backtest_portfolio`：读磁盘文件名
- Scanner 降级：`query_stock_basic(status='1')` 仅返回当前上市股

### 补齐方案

| 组件 | BaoStock 接口 | 说明 |
|---|---|---|
| PIT 每日股票池 | `query_all_stock(day=<date>)` | 任意历史交易日的完整可交易列表，包含退市前股票 |
| 退市股行情 | `query_history_k_data_plus(code=<delisted>)` | BaoStock 保留退市股历史数据（覆盖率需实测） |
| 停牌日历 | `fields="tradestatus"` | tradestatus=0 为停牌 |
| ST 历史 | `fields="isST"` | isST=1 为 ST |

### 工作量估算

| 任务 | 调用次数 | 预估耗时 |
|---|---|---|
| PIT 股票池（300 交易日） | 300 次 | < 10 分钟 |
| 退市股行情（估 200-500 只） | 200-500 次 | 5-15 分钟 |
| 现有 4919 只补拉 tradestatus/isST/preclose | 4919 次 | 30-60 分钟 |

---

## 五、状态信号与事件信号的区别

### 现有状态信号（`BelowLimitUpPrice.compute()`）

```
日期   信号
T      False
T+1    True   ← 首次触发
T+2    True   ← 状态持续（同一波段）
T+3    True   ← 状态持续
...
T+45   True   ← 仍在状态中（45 天后仍低于涨停价）
```

问题：回测中，T+1、T+2、T+3…T+45 每天都可能开新仓，把一次连续下跌/横盘拆成 45 笔独立交易，严重膨胀样本数，胜率计算失真。

### 事件信号（PRE3 新设计）

```
signal_event = signal_state & ~signal_state.shift(1).fillna(False)

日期   状态信号   事件信号
T      False      False
T+1    True       True   ← 仅此日触发
T+2    True       False  ← 冷却中
...
T+45   True       False  ← 冷却中（距 T+1 未满 20 日仍压制）
T+22   False→True True   ← 若状态中断后重新触发，且距上次 ≥ 20 日则允许
```

---

## 六、20 日冷却期的待验证属性

冷却期 20 个交易日（≈1 个月）是**设计假设**，尚未经过数据验证：

| 待验证项 | 验证方法 | 判定标准 |
|---|---|---|
| 20 日内同一波段是否确实连续触发 | 对历史 parquet 统计：触发信号后，状态持续的中位数天数 | 若中位数 < 20 日，冷却期过长；若 > 20 日，冷却期合适 |
| 冷却期对信号数量的影响 | 分别以 5/10/20/30 日冷却期统计 IS 段有效信号数 | 信号数 ≥ 30 以保证统计意义 |
| 20 日内是否有独立新机会 | 分析冷却期内股价走势，是否有不同涨停事件产生的新信号 | 若冷却期屏蔽了真实独立机会，需缩短或改为基于事件的冷却逻辑 |

**冷却期的正确定义待验证后确认，20 日为初始设计值。**

---

## 七、涨跌停价格状态与真实成交假设的区别

| 判断维度 | 现有引擎（PRE2） | PRE3 修订方案 |
|---|---|---|
| 涨停判断方式 | pctChg 阈值（9.8%/19.8%） | `open >= prev_close × (1 + limit_pct)` |
| 一字板定义 | 无 | 开盘价等于或高于涨停价（无法自由买入） |
| 一字板买入处理 | 未处理（仍按 open 买入） | 保守模式跳过；激进模式按打开价成交 |
| 跌停持仓处理 | 未处理 | 延长持仓，次日重试，最多 +3 日 |
| 停牌处理 | volume=0 过滤行，日期序列不连续 | tradestatus=0 保留行，持仓延长 |
| 跳空止损 | 按 stop_loss_price 成交（乐观） | `min(open, stop_loss_price)` 成交（真实） |
| 数据依赖 | close, pct_chg | 新增需求：preclose, tradestatus |

**涨停价格状态**（`pctChg >= 9.8%`）：只判断"当日是否有涨停事件"，不能判断"明日是否能买入"。

**真实成交假设**：需要 T+1 的 open 与 prev_close 比较，才能判断 T+1 是否为一字板。这要求买入时已知 T+1 open，属于已知（T+1 开盘是确定的交易事实，不是未来信息）。

---

## 八、七项执行模型缺口

| ID | 缺口描述 | 优先级 | 前提数据需求 | 影响 |
|---|---|---|---|---|
| GAP-1 | 涨跌停一字板可成交判断 | **P0** | preclose, tradestatus | 高：G2 信号源自涨停，T+1 封板概率大 |
| GAP-2 | 停牌期持仓延长（不截断持仓日数） | **P0** | tradestatus | 中：短窗口策略（hold_days=5）影响明显 |
| GAP-3 | 跳空止损按 open 成交（非 stop_loss_price） | **P0** | 无新数据 | 高：当前乐观假设高估止损精度 |
| GAP-4 | 状态信号→事件信号转换 + 冷却期 | **P0** | 无新数据 | 高：消除信号重复，统计有效性关键 |
| GAP-5 | 组合回测每日（非信号日）清算持仓 | P1 | 无新数据 | 中：止损/止盈可能在非信号日触发 |
| GAP-6 | 退市股强制平仓（持仓期遇退市） | P2 | 退市日历 | 低：短窗口回测窗口内退市概率低 |
| GAP-7 | 到期平仓改用 next_open（替代 close） | P2 | 无新数据 | 低：方向保守，不影响信号有效性 |

P0 四项中，GAP-3/4 仅需逻辑修改，无新数据依赖，实现成本最低。

---

## 九、IS/OOS、预热期和负控设计

### 时间切分

```
预热期   2023-07-01 → 2023-12-29（约 120 交易日，不产生信号，仅预热因子窗口）
IS 段    2024-01-02 → 2024-09-30（约 189 交易日）
OOS 段   2024-10-01 → 2025-04-03（约 120 交易日，OOS 长度 = 一个完整因子窗口）

注：当前缓存始于 2024-01-02，无 2023 年数据
    若无法补拉预热数据，IS 段后移至 2024-05-23 起（89 个有效交易日，偏短）
```

### 基准

| 基准 | 可行性 | 用途 |
|---|---|---|
| 等权全市场（同一 parquet 池） | FEASIBLE | 主基准；消除有偏池 market effect |
| 沪深 300 | PARTIAL（依赖 BaoStock 实时拉取） | 辅助基准 |
| 行业等权 | NOT_FEASIBLE（无行业字段） | P2，补充行业数据后启用 |

### 参数网格

```
lookback_days ∈ {60, 90, 120, 180}
hold_days     ∈ {3, 5, 10}
stop_loss     ∈ {-3%, -5%, -8%}
take_profit   ∈ {8%, 10%, 15%}
总组合数 = 4×3×3×3 = 108 组
```

### 四个负控

| 负控 | 目的 | 预期结果（若因子有效） |
|---|---|---|
| NC-1：pctChg VERIFY-1/2 | 确认 pctChg 不受 adjustflag 影响 | 三版本 pctChg 完全一致 |
| NC-2：前 120 日边界 | 确认因子无边界前视 | 前 120 日信号全为 False |
| NC-3：随机打乱 close | 确认 G2 有时序信息 | 打乱后胜率显著低于正常序列 |
| NC-4：信号反转 | 确认 G2 方向正确 | 反转版本收益显著低于正向 |

---

## 十、后续开发任务拆分与依赖关系

```
                        ┌─────────────────────────┐
                        │  Owner 授权后             │
                        └──────────┬──────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
        [TASK-D1]           [TASK-E1]            [TASK-V1]
       数据补齐任务         引擎修复任务          验证实验任务
       (独立任务卡)         (独立任务卡)          (独立任务卡)

TASK-D1 数据补齐（前提：Owner 授权）
  D1-a  补拉 tradestatus, isST, preclose 字段（4919 只）
  D1-b  BaoStock query_all_stock PIT 股票池（300 交易日）
  D1-c  退市股行情补拉（需先确定退市股名单）
  D1-d  预热期数据补拉（2023-07-01 → 2023-12-29）
  D1-e  数据指纹更新（manifest pin 新字段）

TASK-E1 引擎修复（前提：Owner 授权 + D1-a 完成）
  E1-a  GAP-3 跳空止损（无数据依赖，可先行）
  E1-b  GAP-4 状态→事件信号转换（无数据依赖，可先行）
  E1-c  GAP-1 涨跌停可成交判断（依赖 D1-a preclose）
  E1-d  GAP-2 停牌期持仓延长（依赖 D1-a tradestatus）
  E1-e  GAP-5 组合回测每日清算

TASK-V1 验证实验（前提：Owner 授权 + D1-a 完成）
  V1-a  VERIFY-1/2 pctChg 语义实证
  V1-b  NC-1 至 NC-4 四个负控执行
  V1-c  前复权锚点漂移实证（snapshot A vs B）

TASK-BT 正式回测（前提：BLK-1~BLK-5 全部缓解 + Owner 授权书）
  BT-1  G2 单因子 IS 段参数优化
  BT-2  G2 单因子 OOS 验证
  BT-3  G1-G4 四重门联合回测

依赖关系：
  TASK-D1 → TASK-E1（D1-a 完成后 E1-c/d 可执行）
  TASK-D1 → TASK-V1（D1-a 完成后 V1-a/b/c 可执行）
  TASK-E1 + TASK-V1 → 阻塞项缓解评估
  阻塞项缓解 → Owner 授权书 → TASK-BT
```

---

## 文件清单

| 文件 | 性质 | SHA256（本机实测） |
|---|---|---|
| `GP_G2_REMEDIATION_DESIGN_PRE3.md` | 主报告（六项修订落实） | 见 commit |
| `GP_G2_DATA_REQUIREMENTS.md` | 数据补齐规格 + pctChg 核验 | 见 commit |
| `GP_G2_EXECUTION_MODEL_SPEC.md` | 执行模型规格 + 7 项缺口 | 见 commit |
| `GP_G2_PRE3_ENGINEERING_HANDOFF.md` | 本文档 | 见 commit |

---

*本文档仅用于工程交接。不包含任何凭据、行情数据、策略代码或其他项目的资产。*  
*CODE_MODIFICATION = NO · DATA_DOWNLOAD = NO · BACKTEST_EXECUTION = NO*

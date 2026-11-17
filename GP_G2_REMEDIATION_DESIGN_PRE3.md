# GP_G2_REMEDIATION_DESIGN_PRE3

**TASK**: GP-G2-REMEDIATION-DESIGN-PRE3 · CC002/MAC-002 · STRICT_READ_ONLY · 2026-11-18  
**上游**: PRE2 ACCEPTED_WITH_LIMITATIONS  
**模式**: STRICT_READ_ONLY — 仅设计，不修改代码/数据/策略

---

## 执行摘要

PRE3 对 PRE2 的六项 Owner 修订意见逐一落实：

| 修订项 | PRE2 状态 | PRE3 结论 |
|---|---|---|
| 1. PIT 历史股票池 | BLOCKED（无设计） | 完整方案设计完成（见 DATA_REQUIREMENTS） |
| 2. pctChg 字段语义核验 | 预设前视污染 | 修正：pctChg 为独立字段，不随 adjustflag 变化 |
| 3. 涨跌停成交模型 | 固定阈值判断 | 修订为价格比较 + 保守/激进两模式 |
| 4. 状态信号→事件信号 | 未设计 | 转换规则完整（首次触发 + 冷却期） |
| 5. IS/OOS 方案修订 | 基础切分 | 加入预热、Beta 控制、参数稳定性、负控（见下） |
| 6. 引擎缺口修复清单 | 分散描述 | 独立规格文件，7 项缺口优先级清单（见 EXECUTION_MODEL_SPEC） |

---

## 一、pctChg 语义核验结论（修正 PRE2）

**证据**：BaoStock 官方 demo（`demo_A_stock_k_data.py`）的字段列表中，`pctChg` 与 `adjustflag` 是独立并列字段。demo 以 `adjustflag="3"`（不复权）请求数据时仍返回 `pctChg`，说明：

- `pctChg` 由交易所原始收盘价 / 前收盘价（`preclose`）推导，不经过复权因子
- `pctChg` 的值与调用时使用 `adjustflag="1"/"2"/"3"` 无关
- 当前缓存用 `adjustflag="2"` 拉取的 `pctChg` 与用不复权拉取的 `pctChg` **理论上相同**

**修正 PRE2 结论**：

```
原 PRE2：LOOKAHEAD_CONTROL = NOT_PROVEN（前复权 pct_chg 含未来除权信息破坏涨停检测）
修正后：pctChg 为独立原始字段，涨停检测（G2 信号核心）不直接继承前复权前视污染

残留前视风险（性质为口径一致性，非涨停检测前视）：
  limit_up_price = close_adj.where(is_lu).ffill()
  前复权 close 在新除权事件发生后会回溯修改 → anchor 漂移 → 信号位置不可复现
  这是数据口径问题，解决方案见 DATA_REQUIREMENTS §4

待验证（需 Owner 授权后执行）：
  VERIFY-1：同一 ticker 三种 adjustflag 下 pctChg 值是否完全一致
  VERIFY-2：除权日 close_adj.pct_change() vs pctChg 的偏差幅度
```

---

## 二、PIT 历史股票池补齐设计

（详见 `GP_G2_DATA_REQUIREMENTS.md` §二）

核心结论：

- BaoStock `query_all_stock(day=<date>)` 可对任意历史交易日返回完整 PIT 股票列表，无需新数据源
- BaoStock `query_history_k_data_plus(fields="tradestatus,isST")` 可重建停牌日历和 ST 历史
- 退市股行情：BaoStock 保留，需实测覆盖率
- 工作量估算：PIT 池 300 次调用 < 10 分钟；退市股行情 5-15 分钟；字段补拉 30-60 分钟

---

## 三、涨跌停成交模型修订

（详见 `GP_G2_EXECUTION_MODEL_SPEC.md` §一）

核心修订：

```
PRE2 方案（已废弃）：pctChg >= 9.8% → 不可成交（直接用涨跌幅判断封板）

PRE3 方案：
  判断是否为一字板 = open >= prev_close × (1 + limit_pct)
  limit_pct 由股票类型决定：10% / 20% / 5%
  
  一字涨停板：
    保守模式（回测基准）：跳过，视为无法买入
    激进模式（敏感性对照）：排队申报，当日若有打开则按打开价成交
  
  一字跌停板（持仓期）：
    持仓延长，次日重试，最多延长 3 日
    超时强制按次日 open 卖出
  
  依赖 preclose 字段（当前缓存无，需补齐）
```

G2 特有说明：G2 信号本身因涨停产生，T+1 买入遭遇封板概率显著高于 G3/G4，此缺口对 G2 策略影响最大。

---

## 四、G2 状态信号→独立事件信号转换

（详见 `GP_G2_EXECUTION_MODEL_SPEC.md` §三）

```
现有问题：BelowLimitUpPrice.compute() 是连续状态信号
         一次跌破涨停价事件可持续触发 30~60 个信号日
         → 回测中重复买入，交易笔数虚高，胜率失真

转换规则：
  signal_event = signal_state & ~signal_state.shift(1)
  仅取状态从 False→True 的首日作为事件信号

冷却期：
  同一股票上次信号后 20 个交易日内忽略新信号
  防止价格短暂回升后再次跌破产生的伪独立信号

组合回测：
  已持仓的股票不重复建仓
  平仓后冷却期内不重新建仓
```

---

## 五、IS/OOS 方案修订

### 5.1 历史预热期

```
G2 因子计算依赖 lookback_days=120 的历史窗口。
IS 段起点前需要 120 个交易日的预热数据：

  预热期：2023-07-01 → 2023-12-29（约 120 个交易日）
  IS 段：2024-01-02 → 2024-09-30（约 189 个交易日）
  OOS 段：2024-10-01 → 2025-04-03（约 120 个交易日）

  注：当前缓存最早数据为 2024-01-02，预热期数据需补拉
  若无法补拉预热数据，IS 段起点后移至 2024-05-23（2024-01-02 起的第 121 个交易日）
  → 有效 IS 段：2024-05-23 → 2024-09-30（约 89 个交易日，偏短）
```

### 5.2 市场 Beta 控制

```
目的：区分 G2 的 Alpha（涨停后回调的反转效应）与市场 Beta（牛市整体上涨）

方案：
  基准 1：同期沪深 300（sh.000300）简单持有收益
  基准 2：同一 parquet 池等权全市场日收益（消除有偏池影响）
  基准 3（可选，需行业数据）：行业等权收益

  超额收益 = 策略收益 − 基准 2 收益（主基准，因幸存者偏差限制使用同一有偏池）
  Beta 中性 IC：Spearman IC of (G2_signal × return) after removing beta factor cross-section
```

### 5.3 行业 Beta 控制

```
现状：当前缓存无行业字段（NOT_FEASIBLE）

BaoStock 可提供：query_stock_industry() 返回股票的行业分类
补充后可做：
  - 行业等权基准（每个信号减去同行业当日均值）
  - 行业中性 IC
  
此项作为 P2 优先级，不阻塞 IS/OOS 基础回测
```

### 5.4 参数稳定性

```
主参数网格（IS 段优化）：
  lookback_days ∈ {60, 90, 120, 180}
  hold_days ∈ {3, 5, 10}
  stop_loss ∈ {-0.03, -0.05, -0.08}
  take_profit ∈ {0.08, 0.10, 0.15}

稳定性判定：
  IS 最优参数组合在 OOS 是否保持前四名 → 若跌出前四，视为过拟合
  相邻参数（±1 档）的 IS 收益差异 < 2% → 参数鲁棒
  相邻参数收益差异 > 5% → 参数敏感，需降低置信度
```

### 5.5 修订后的四个负控

```
NC-1  pctChg 语义验证（VERIFY-1/2，见 DATA_REQUIREMENTS §1.4）
      → 核验 adjustflag 是否影响 pctChg，确认无影响后 NC-1 PASS

NC-2  边界行为：前 120 日 G2 信号是否全为 False
      → 确认因子无边界前视

NC-3  随机打乱负控
      → 将 close 序列在日期轴上随机打乱
      → 重算 G2 信号和回测收益
      → 若胜率与正常序列接近 → G2 无时序信息 → 策略无效

NC-4  信号反转负控
      → 对 BelowLimitUpPrice=False 的股票执行相同交易逻辑
      → 若反转版本收益更好 → G2 方向可能读反
      → 参考：RL0 审计确认 G2_refA/B 方向为 DIRECTIONALLY_SUPPORTIVE（跌深未来好）
            Teacher canonical G2 应与此一致，但需独立核验
```

---

## 六、引擎缺口修复清单

（详见 `GP_G2_EXECUTION_MODEL_SPEC.md` §五）

汇总七项缺口：

| ID | 缺口 | 优先级 | 前提数据 |
|---|---|---|---|
| GAP-1 | 涨跌停一字板可成交判断 | P0 | preclose, tradestatus |
| GAP-2 | 停牌期持仓延长 | P0 | tradestatus |
| GAP-3 | 跳空止损按 open 成交 | P0 | 无新需求 |
| GAP-4 | 状态信号→事件信号转换 | P0 | 无新需求 |
| GAP-5 | 组合回测每日清算 | P1 | 无新需求 |
| GAP-6 | 退市强制平仓 | P2 | 退市日历 |
| GAP-7 | 到期平仓改用 next_open | P2 | 无新需求 |

P0 四项均不阻塞于新数据（GAP-3/4 仅需逻辑修改），但 GAP-1/2 的完整实现依赖 `preclose` 和 `tradestatus` 字段。

---

## 七、依赖关系图

```
DATA_REQUIREMENTS         EXECUTION_MODEL_SPEC
      │                          │
      ├── pctChg 语义核验 ─────── VERIFY-1/2 → NC-1
      ├── PIT 股票池补齐           │
      ├── tradestatus 补拉 ──────→ GAP-1（涨跌停）
      │                           GAP-2（停牌）
      ├── preclose 补拉 ─────────→ GAP-1（涨跌停价格比较）
      └── isST 补拉 ─────────────→ ST 涨停阈值修正
                                  │
                        IS/OOS DESIGN（本文件）
                                  │
                        [Owner 授权后] → 执行
```

---

## 最终状态

```
DATA_REMEDIATION_READY     = PARTIAL
  ├── pctChg 语义：REVISED（原始字段，不受复权影响；anchor 漂移为口径问题）
  ├── PIT 方案：DESIGNED（BaoStock PIT 接口可用，工作量可控）
  ├── 字段补齐：DESIGNED（preclose/tradestatus/isST/adjustflag）
  └── 执行前提：需 Owner 授权独立任务卡

EXECUTION_REMEDIATION_READY = PARTIAL
  ├── 涨跌停模型：REVISED（价格比较 + 保守/激进两模式）
  ├── 状态→事件转换：DESIGNED
  ├── 缺口清单：COMPLETE（7 项，优先级已定）
  └── 执行前提：需 Owner 授权代码修改任务卡

LOOKAHEAD_TEST_READY       = PARTIAL
  ├── VERIFY-1/2：DESIGNED（待授权执行）
  ├── NC-1 至 NC-4：DESIGNED（待授权执行）
  └── anchor 漂移：解决方案已设计（方案 A：不复权分离；方案 B：固定基准日）

BACKTEST_AUTHORIZED        = NO
FINAL_STATUS               = READY_FOR_OWNER_REVIEW
NEXT_GATE                  = OWNER_REVIEW
```

---

*本报告仅执行读取和分析操作。未修改任何代码、数据、策略或 Finance Suite 文件。  
未提交 Git。未执行任何回测。未修改 GOLDEN_PIT_AUTHORITY_HOLD.md。*

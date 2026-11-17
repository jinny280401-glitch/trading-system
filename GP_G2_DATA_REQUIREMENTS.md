# GP_G2_DATA_REQUIREMENTS — 数据补齐与字段语义核验

**TASK**: GP-G2-REMEDIATION-DESIGN-PRE3 · CC002/MAC-002 · STRICT_READ_ONLY · 2026-11-18  
**上游裁决**: PRE2 ACCEPTED_WITH_LIMITATIONS；Owner 纠正"不预设前视污染已经发生"

---

## 一、BaoStock pctChg 与 adjustflag 字段语义核验

### 1.1 证据来源

BaoStock `query_history_k_data_plus` 的字段列表（来自官方 demo `demo_A_stock_k_data.py`）：

```
date, code, open, high, low, close, preclose, volume, amount,
adjustflag, turn, tradestatus, pctChg, peTTM, pbMRQ, psTTM, pcfNcfTTM, isST
```

本仓库 `data/cache.py:54` 实际请求的字段：

```
date, open, high, low, close, volume, amount, pctChg
```

**缓存丢弃了**：`code`, `preclose`, `adjustflag`, `turn`, `tradestatus`, `peTTM`, `pbMRQ`, `psTTM`, `pcfNcfTTM`, `isST`。

### 1.2 pctChg 字段语义判定

| 判定维度 | 证据 | 结论 |
|---|---|---|
| 是否独立字段 | 在 `query_history_k_data_plus` 的 fields 参数中作为独立字段请求，不依赖 close 计算 | **独立字段** |
| 是否随 adjustflag 变化 | 官方 demo 用 `adjustflag="3"`（不复权）请求 pctChg；`cache.py` 用 `adjustflag="2"`（前复权）请求 pctChg——同一字段在不同复权模式下均可请求 | **语义上为交易所原始涨跌幅**，不随复权模式改变 |
| 与 preclose 的关系 | BaoStock 同时返回 `preclose`（前收盘价，原始未复权），`pctChg = (close_raw − preclose_raw) / preclose_raw × 100` | pctChg 基于**原始价格**计算 |
| 与缓存中 close 的关系 | 缓存 close 为前复权价（`adjustflag="2"`），`pctChg` 为原始涨跌幅——两者**口径不同** | `close.pct_change() ≠ pctChg`（除权日会不同） |

### 1.3 结论（修正 PRE2）

```
pctChg 字段性质    = 独立涨跌幅字段（交易所原始值，不随 adjustflag 变化）
pctChg 与复权的关系 = 无关——pctChg 基于原始 close/preclose，不受复权因子影响
前视污染是否已发生  = NOT_PROVEN（不预设已发生）

PRE2 修正：
  原 PRE2 结论"前复权 pct_chg 含未来除权信息破坏涨停检测"
  → 修正为"pctChg 为独立原始字段，涨停检测不直接继承前复权前视污染"
  
残留风险（非前视，为口径一致性）：
  G2 的 limit_up_price = close.where(is_lu).ffill() 使用前复权 close
  当前 close 与 limit_up_price 的比较在前复权口径内自洽
  但跨除权事件时，前复权 anchor 与原始涨停收盘价不同
  这是口径一致性问题，不是前视污染
```

### 1.4 待验证项（需授权后执行）

```
VERIFY-1  对同一 ticker 分别以 adjustflag="1"/"2"/"3" 拉取数据，
          对比三个版本的 pctChg 值是否完全一致
          预期：完全一致（证明 pctChg 独立于复权）
          若不一致：pctChg 受复权影响，需重新评估前视风险

VERIFY-2  对比 pctChg 与 (close_adj.pct_change() × 100) 在除权日的差异
          预期：除权日 close_adj.pct_change() 偏离 pctChg
          若除权日两者一致：说明 close 未真正前复权，或 pctChg 已被复权
```

---

## 二、PIT 历史股票池补齐设计

### 2.1 现状

| 项 | 现状 | 证据 |
|---|---|---|
| 股票池来源 | 当前存续股实时快照（`cmd_warmup`）或磁盘文件名（`cmd_backtest_portfolio`） | `main.py:230,191` |
| 退市股 | 不包含 | 三条路径均无退市逻辑 |
| PIT 重建能力 | 不存在 | `query_all_stock(day=)` 从未被调用 |
| 上市/退市/停牌日历 | 不存在 | 缓存 schema 无这些字段 |

### 2.2 BaoStock 已有 PIT 能力（无需新数据源）

| BaoStock 接口 | 功能 | PIT 能力 |
|---|---|---|
| `query_all_stock(day=<date>)` | 返回指定交易日的全部可交易股票列表 | **PIT 完整**——含当日上市、当日尚未退市的股票 |
| `query_stock_basic(code=)` | 返回个股的上市日期、退市日期、类型、状态 | 退市股可查（status=0 为退市） |
| `query_history_k_data_plus(code=, fields="tradestatus")` | 逐日交易状态（1=正常, 0=停牌） | 停牌日历可重建 |
| `query_history_k_data_plus(code=, fields="isST")` | 逐日 ST 标记（1=ST, 0=非ST） | ST 历史可重建 |
| `query_adjust_factor(code=, start_date=, end_date=)` | 逐次除权除息的复权因子 | 可用于不复权/前复权/后复权切换 |

### 2.3 PIT 股票池重建方案

```
对回测窗口内的每个交易日 T：

  1. 调用 query_all_stock(day=T) 获取 T 日全部可交易股票列表 U(T)
  2. U(T) 即为 T 日的 PIT 股票池
  3. 对 U(T) 中的每只股票，使用其历史日线数据计算因子信号
  4. 信号判定仅在 U(T) 范围内进行（不引入 T 日后才能知道是否存续的股票）

退市处理：
  - query_all_stock(day=T) 自动包含 T 日尚未退市的股票
  - 退市股在退市前最后一天的信号可正常计算
  - 退市后不再出现在 U(T) 中，不产生新信号
  - 退市时持仓的处理见执行模型_spec

停牌处理：
  - tradestatus=0 的日期标记为停牌
  - 停牌日不出信号（无 close 可用）
  - 持仓期遇停牌的处理见执行模型_spec

ST 历史：
  - isST=1 的日期标记为 ST
  - G2 因子的涨停阈值在 ST 期间应使用 4.8% 而非 9.8%/19.8%
  - ST 状态变化历史可完整重建
```

### 2.4 数据缺失处理

| 缺失类型 | 处理方式 | 说明 |
|---|---|---|
| 退市股行情缺失 | 调用 `query_history_k_data_plus` 补拉 | BaoStock 保留退市股历史数据（不保证完整，需核验） |
| 停牌日 | `tradestatus=0` 标记，不补数据 | 停牌日本身无行情，不参与信号计算 |
| 上市首日前 | 不纳入股票池 | `query_all_stock` 只返回当日已上市的股票 |
| 新股次新股 | 依赖 `query_all_stock` 的返回 | PIT 自动排除未上市股票 |
| 数据拉取失败 | 记录失败 ticker，标注覆盖率 | 不以部分缺失否定整体，但须报告 |

### 2.5 补齐工作量估算

```
PIT 股票池：
  回测窗口 2024-01-02 → 2025-04-03 ≈ 300 个交易日
  每日调用 query_all_stock(day=) 1 次
  共 300 次调用，预计 < 10 分钟

退市股行情：
  需先确定退市股名单（对比 U(T_first) 与 U(T_last) 的差集）
  预估退市股 200-500 只（需实测）
  每只拉取历史日线，并发 8 线程，预计 5-15 分钟

tradestatus / isST：
  需重新拉取现有 4919 只 + 退市股的历史日线（含 tradestatus, isST 字段）
  或对现有缓存补拉这两个字段
  预计 30-60 分钟（全量重拉）

复权因子：
  query_adjust_factor 用于 VERIFY-1/2 和不复权平行跑
  预计 30 分钟
```

---

## 三、可用但未缓存的字段清单

| 字段 | BaoStock 可提供 | 当前缓存 | 回测所需 | 补齐方式 |
|---|---|---|---|---|
| `preclose` | 是 | 否 | VERIFY-2 需要 | 重拉或补拉 |
| `tradestatus` | 是 | 否 | 停牌判断必须 | 重拉或补拉 |
| `isST` | 是 | 否 | ST 涨停阈值必须 | 重拉或补拉 |
| `adjustflag` | 是 | 否 | 复权核验必须 | 重拉或补拉 |
| `turn` | 是 | 否 | 换手率因子（可选） | 按需 |
| `peTTM/pbMRQ/psTTM` | 是 | 否 | 估值因子（非 G2 必需） | 按需 |

**最小补齐集**（G2 回测必须）：`preclose`, `tradestatus`, `isST`, `adjustflag`。

---

## 四、复权口径与不可复现性

### 4.1 前复权的不可复现机制

前复权系数在数据下载时刻 T_download 计算，取决于 T_download 之前发生的所有除权事件。**每次重新拉取**，若有新的除权事件发生，历史前复权价会变化。

对回测的影响：
- `close`（前复权）在每次拉取后可能变化 → 信号位置可能漂移
- `pctChg`（独立字段）不变 → 涨停检测不受影响
- `limit_up_price = close.where(is_lu).ffill()` 使用前复权 close → anchor 可能漂移

### 4.2 解决方案

```
方案 A（推荐）：改用不复权价格 + 复权因子分离计算
  - close_raw = query(adjustflag="3") 的 close
  - 信号计算用 close_raw 和 pctChg（均为原始值，可复现）
  - 回撤深度计算用复权因子还原真实涨跌
  - 涨停检测用 pctChg（已为原始值）

方案 B（次选）：固定前复权基准日
  - 以回测起始日 T_start 为前复权基准
  - 所有数据在该基准日拉取并冻结
  - 不增量更新（避免新除权事件改变历史价）
  - 缺点：基准日之后发生的除权事件不被反映，影响后续信号
```

---

## 五、最终状态

```
PCTCHG_SEMANTICS           = INDEPENDENT_FIELD（交易所原始涨跌幅，不随 adjustflag 变化）
LOOKAHEAD_PRESUMPTION      = WITHDRAWN（不预设前视已发生；待 VERIFY-1/2 验证）
PIT_UNIVERSE_FEASIBILITY    = FEASIBLE（BaoStock query_all_stock 可用，无需新数据源）
DELISTED_STOCK_COVERAGE    = PARTIAL（BaoStock 保留部分退市股数据，需实测覆盖率）
SUSPEND_CALENDAR           = FEASIBLE（tradestatus 字段可用）
ST_HISTORY                 = FEASIBLE（isST 字段可用）
REPRODUCIBILITY_SOLUTION    = DESIGNED（方案 A：不复权 + 复权因子分离；方案 B：固定基准日）
DATA_REMEDIATION_READY     = PARTIAL（方案完整，需 Owner 授权执行任务卡）
```

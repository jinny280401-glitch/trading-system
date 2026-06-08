# Trading System - 黄金坑四重门量化扫描系统

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

A quantitative stock screening system based on the "Golden Pit" 4-Gate strategy for A-share market analysis.

黄金坑四重门量化扫描系统 - 基于涨停基因、深度回调、横盘筑底、技术反弹的 A 股量化选股工具。

---

## 📋 目录

- [核心功能](#核心功能)
- [四重门策略](#四重门策略)
- [安装方法](#安装方法)
- [使用方式](#使用方式)
- [MCP 工具](#mcp-工具)
- [数据源](#数据源)
- [项目结构](#项目结构)
- [免责声明](#免责声明)
- [许可证](#许可证)

---

## 🎯 核心功能

- **全市场扫描**：4900+ 只 A 股票池，秒级完成扫描
- **四重门因子**：涨停基因 → 跌破涨停价 → 横盘筑底 → BBIBOLL 下轨反弹
- **两阶段引擎**：粗筛（市值/PE）+ 精筛（因子计算）
- **本地缓存**：Parquet 格式，116MB 缓存 4911 只股票 400 天历史数据
- **MCP 服务**：5 个工具，可被 Claude Code / OpenClaw 等 MCP 客户端调用
- **回测引擎**：支持单股/组合回测，可配置止损止盈策略

---

## 🚪 四重门策略

黄金坑 = **涨停基因** × **深度回调** × **横盘筑底** × **技术反弹**

四重门采用 **AND 逻辑串联**，每一关都是过滤器：

| 关卡 | 因子 | 条件 | 过滤率 | 本质 |
|------|------|------|--------|------|
| **G1** | 涨停基因 | 120 天内有涨停记录 | 42% | 有爆发历史 |
| **G2** | 跌破涨停价 | 当前价 < 最近涨停价 | 15% | 已深度回调 |
| **G3** | 横盘筑底 | 60 日振幅 ≤15% + 贴均线 + 缩量 | **97.7%** | 筑底不破位 |
| **G4** | BBIBOLL 下轨反弹 | 触及布林下轨后当日反弹 | 极稀缺 | 时机启动 |

### 因子详解

#### Gate 1: 涨停基因 (LimitUpGene)
- **逻辑**：过去 120 个交易日内至少有一次涨停
- **阈值**：主板 9.8% / 创业板科创板 19.8%
- **评分**：涨停次数（0-50 分）+ 距最近涨停天数（0-50 分）

#### Gate 2: 跌破涨停价 (BelowLimitUpPrice)
- **逻辑**：当前收盘价 < 最近一次涨停的收盘价
- **目的**：确认已深度回调，洗盘充分
- **评分**：跌破幅度 0-20% 映射到 0-100 分（跌幅越大分越高）

#### Gate 3: 横盘筑底 (Consolidation) ⭐️ 主过滤器
- **逻辑**：
  - 近 60 日振幅 ≤ 15%（高低点差 / 低点）
  - 收盘价贴近 20 日均线（偏离 ≤ 10%）
  - 成交量萎缩（近 60 日均量 / 前 60 日均量 ≤ 0.8）
- **评分**：振幅紧度（0-40 分）+ 持续天数（0-30 分）+ 缩量程度（0-30 分）
- **过滤效果**：2394 只 → **54 只**（97.7% 淘汰率）

#### Gate 4: BBIBOLL 下轨反弹 (BBIBOLLLowerBounce) ⭐️ 时机过滤器
- **BBIBOLL**：BBI 的布林通道（通达信标准 N=11, M=6）
- **BBI**：(MA3 + MA6 + MA12 + MA24) / 4
- **逻辑**：
  - 连续 N 天收盘 ≤ 下轨
  - 当天收盘 > 昨收（反弹启动）
- **评分**：跌破下轨深度（0-50 分）+ 反弹力度（0-50 分）

---

## 📦 安装方法

### 1. 克隆仓库

```bash
git clone https://github.com/jinny280401-glitch/trading-system.git
cd trading-system
```

### 2. 创建虚拟环境

```bash
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

---

## 🚀 使用方式

### 方式 1: 命令行 (CLI)

```bash
# 全市场扫描（使用本地缓存，秒级完成）
python3 main.py scan

# 带实时行情扫描（约 3-4 分钟）
python3 main.py scan --realtime

# 单股调试
python3 main.py debug 000900 --start 2025-01-01 --end 2025-04-07

# 回测
python3 main.py backtest 000900 --start 2024-01-01 --end 2025-04-07
```

### 方式 2: MCP 服务

#### 启动 MCP 服务

```bash
python3 mcp_server.py
```

#### 配置到 Claude Code

在 `~/.claude/settings.json` 中添加：

```json
{
  "mcpServers": {
    "trading-system": {
      "command": "/path/to/trading-system/.venv/bin/python3",
      "args": ["/path/to/trading-system/mcp_server.py"]
    }
  }
}
```

---

## 🛠️ MCP 工具

| 工具名 | 功能 | 参数 |
|--------|------|------|
| `golden_pit_scan` | 全市场四重门扫描 | `use_realtime: bool` |
| `golden_pit_watchlist` | 观察池排序（G1-G3 过，等待 G4） | 无 |
| `stock_debug` | 单股调试（逐日信号 + 评分） | `code, start_date, end_date` |
| `update_stock_cache` | 更新指定股票最新数据 | `code` |
| `backtest_stock` | 单股/组合回测 | `code, start_date, end_date` |

### 示例：在 Claude Code 中调用

```
请用 golden_pit_scan 扫描今日黄金坑信号
```

## 🧭 研究路由

`serenity-skill` 仅用于产业链、供应链、卡点、瓶颈、主题深度调研类任务。普通个股快照、因子扫描、黄金坑初筛、快答、四重门仍走本项目原有数据链路、QC 和 Trust Gate。

在 Finance Suite / trading-system 体系内，`serenity-skill` 被分类为 **Methodology Consumer**。它不持有 Provider 注册、不参与 QC、不参与 Trust Gate、不修改 ReportAssembly；产出仅作为 research partner 的对话素材和核验清单，最终研究编排权属于 Research Runtime。

---

## 📊 数据源

| 数据源 | 用途 | 授权模式 |
|--------|------|---------|
| **BaoStock** | 历史日线数据（主数据源） | 免费公开 |
| **AkShare** | 实时行情 + 备选数据源 | 免费公开 |
| **东财 API** | 全市场快照（粗筛用） | 爬虫调用 |

**数据源声明**：
- BaoStock 和 AkShare 为免费公开数据源，遵守其使用条款
- 东财 API 通过爬虫方式调用，**仅供学习研究使用**，请勿用于商业用途
- 本项目不对数据准确性和时效性负责

---

## 📁 项目结构

```
trading-system/
├── main.py                 # CLI 入口
├── mcp_server.py          # MCP 服务
├── config/
│   └── settings.py        # 全局配置
├── factors/               # 因子模块
│   ├── base.py           # 因子基类
│   ├── limit_up.py       # 涨停相关
│   ├── bbiboll.py        # BBIBOLL 指标
│   ├── consolidation.py  # 横盘筑底
│   ├── volume.py         # 成交量
│   └── market_env.py     # 市场环境
├── data/
│   ├── provider.py       # 数据获取（两级数据源）
│   └── cache.py          # Parquet 缓存 + 增量更新
├── engine/
│   └── scanner.py        # 两阶段扫描引擎
├── backtest/
│   └── backtester.py     # 回测引擎
└── scripts/
    └── factor_scan.py    # 独立 CLI 脚本
```

---

## ⚠️ 免责声明

**本项目仅供学习研究使用，不构成任何投资建议。**

- 量化策略存在失效风险，历史表现不代表未来收益
- 股市有风险，投资需谨慎
- 使用本项目产生的任何投资损失，作者不承担责任
- 请遵守数据源的使用条款和相关法律法规

---

## 📄 许可证

本项目采用 [MIT License](LICENSE) 开源。

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

## 📧 联系方式

- GitHub: [@jinny280401-glitch](https://github.com/jinny280401-glitch)
- 项目主页: [trading-system](https://github.com/jinny280401-glitch/trading-system)

---

**⭐ 如果这个项目对你有帮助，请给个 Star！**

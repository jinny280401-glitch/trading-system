# Golden Pit Simulation Experiment v0.2

```
Version:    v0.2
Status:     DESIGN FROZEN (2026-07-22)
Primary:    Calmar Ratio (FROZEN)
Secondary:  Sharpe, Win Rate, Max Drawdown, Precision
```

## Research Questions (FROZEN)

```
RQ-1: 黄金坑前置 + 早盘确认 (S3) 是否优于纯黄金坑前置 (S2)？
RQ-2: 早盘确认增加的是收益 (Return) 还是精度 (Precision)？
RQ-3: 波段退出规则是否影响 Calmar Ratio 而非仅影响胜率？
```

## Failure Criteria (FROZEN)

| 条件 | 结论 |
|------|------|
| S3-1005 Calmar ≤ S2-1005 | 早盘确认未产生统计增量 |
| S2-open Calmar ≤ S0-0931 (Random 中位数) | 黄金坑 Baseline 无统计优势 |
| Blocking Gate 不通过 | 实验停止 |

## 文件结构

```
golden-pit-v0/
├── README.md
├── EXPERIMENT_MATRIX_v0.2.md        ← 实验矩阵 S0-S3
├── SIGNAL_FORMULA_MAP_v0.2.md       ← 公式与源码映射
├── no_future_function_audit.md      ← 无未来函数审计
├── platform_limitations.md          ← 平台限制
├── CHANGELOG.md                     ← 变更记录
├── drafts/                          ← ⛔ NOT APPROVED
│   ├── group_a_full_strategy.py
│   ├── group_b_prescreen_only.py
│   └── group_c_random_buy.py
└── platform_smoke/                  ← Platform Smoke 脚本
    ├── smoke_after_close.py
    ├── smoke_minute_bar.py
    ├── smoke_intraday_order.py
    ├── smoke_historical_constituents.py
    └── smoke_slippage.py
```

## 当前状态

```
Spec:                     DESIGN FROZEN
Strategy Implementation:  HOLD (待 Platform Smoke 全部 PASS)
Platform Smoke:           APPROVED / PENDING EXECUTION
Historical Backtest:      NOT RUN
Forward Simulation:       NOT STARTED
Strategy Effectiveness:   NOT CLAIMED
```

## 下一步

1. G 轮换聚宽密码
2. 登录 joinquant.com → 运行 `platform_smoke/` 下 5 个脚本
3. 全部 PASS → 解除 Implementation HOLD → 按 `EXPERIMENT_MATRIX_v0.2.md` 重写策略文件
4. 短区间 smoke → 正式回测 → 模拟盘

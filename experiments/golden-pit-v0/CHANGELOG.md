# CHANGELOG

## v0.2 (2026-07-22) — DESIGN FROZEN

**Status**: Package Aligned. Implementation HOLD.

### 变更

- 目录重构：Draft 文件移入 `drafts/`，新增 `platform_smoke/`
- 新增 `EXPERIMENT_MATRIX_v0.2.md` — 7 组单变量实验矩阵
- 新增 `SIGNAL_FORMULA_MAP_v0.2.md` — 公式与源码映射
- 新增 `CHANGELOG.md`
- 重写 `README.md` — Pre-registration, RQ, Failure Criteria, 状态锁
- 重写 `no_future_function_audit.md` — 移除 M4, 修正时间边界为 10:01, 区分 Phase 1/2 退出
- 重写 `platform_limitations.md` — 补充 jqdatasdk/jqdata 边界, Blocking Gates
- Smoke 拆分：5 个独立脚本
- Phase 1 退出统一为 Pure Fixed 10 日

### 审议

G 裁定: PASS / DESIGN FROZEN
C 补充: 实验隔离 PARTIAL（S2 vs S3 需时间匹配组）

## v0.1 (2026-07-22) — REVISION REQUIRED → PASS

### 变更

- 修复 6 项硬问题（双变量污染、Baseline 时间、滑点、M4、时间闭合、幸存者偏差）
- 两阶段实验（入场/退出分离）
- 早盘判定改为 10:01，只读闭合 bar
- M6 标注 DEGRADED

## v0 (2026-07-22) — PARTIAL / REVISION REQUIRED

### 变更

- 初始设计：A/B/C 三组对照
- 问题：A/B 双变量污染、M4 日量/8、10:00 bar 未闭合、FixedSlippage 误用
- G+C 审议：6 项需修复

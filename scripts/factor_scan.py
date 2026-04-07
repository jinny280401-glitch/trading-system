#!/usr/bin/env python3
"""
因子扫描 — 独立CLI脚本，供 Finance Suite 调用

用法:
    python3 scripts/factor_scan.py              # 扫描当天
    python3 scripts/factor_scan.py 2025-04-03   # 指定日期
    python3 scripts/factor_scan.py --json       # JSON输出（程序调用）

输出格式为 LLM 可读的结构化文本，可直接嵌入 Prompt
"""

import sys
import os
import json
import time
from datetime import datetime

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.provider import DataProvider
from factors.limit_up import LimitUpGene, BelowLimitUpPrice
from factors.volume import ConsecutiveDecline
from factors.bbiboll import BBIBOLLLowerBounce
from factors.consolidation import Consolidation
from engine.scanner import Scanner
from config.settings import FACTORS, SIGNAL_COMBO, FACTOR_WEIGHTS


def build_factors():
    """构建因子列表"""
    factor_map = {
        "limit_up_gene": lambda: LimitUpGene(
            lookback_days=FACTORS["limit_up_gene"]["lookback_days"],
        ),
        "below_limit_up_price": lambda: BelowLimitUpPrice(
            lookback_days=FACTORS["below_limit_up_price"]["lookback_days"],
        ),
        "consecutive_decline": lambda: ConsecutiveDecline(
            min_days=FACTORS["consecutive_decline"]["min_days"],
            max_days=FACTORS["consecutive_decline"]["max_days"],
            volume_shrink=FACTORS["consecutive_decline"]["volume_shrink"],
        ),
        "consolidation": lambda: Consolidation(
            lookback_days=FACTORS["consolidation"]["lookback_days"],
            max_amplitude=FACTORS["consolidation"]["max_amplitude"],
            ma_period=FACTORS["consolidation"]["ma_period"],
            ma_proximity=FACTORS["consolidation"]["ma_proximity"],
            volume_shrink_ratio=FACTORS["consolidation"]["volume_shrink_ratio"],
        ),
        "bbiboll": lambda: BBIBOLLLowerBounce(
            bbi_periods=FACTORS["bbiboll"]["bbi_periods"],
            boll_period=FACTORS["bbiboll"]["boll_period"],
            boll_std=FACTORS["bbiboll"]["boll_std"],
            min_days_below=FACTORS["bbiboll"]["min_days_below"],
        ),
    }
    factors = []
    for name in SIGNAL_COMBO:
        if name in factor_map:
            f = factor_map[name]()
            f.weight = FACTOR_WEIGHTS.get(name, 1.0)
            factors.append(f)
    return factors


def run_scan(scan_date: str = None) -> dict:
    """执行扫描，返回结构化结果"""
    provider = DataProvider()
    factors = build_factors()
    scanner = Scanner(provider, factors)

    t0 = time.time()
    result = scanner.scan(scan_date)
    elapsed = time.time() - t0

    hits = result["hits"]
    env = result["market_env"]
    stats = result["stats"]

    # 构建输出数据
    signals = []
    if not hits.empty:
        score_cols = [c for c in hits.columns if c.endswith("_score")]
        for _, row in hits.iterrows():
            sig = {
                "code": row["code"],
                "name": row.get("name", ""),
                "close": round(row["close"], 2),
                "pct_chg": round(row.get("pct_chg", 0), 2),
                "composite_score": round(row.get("composite_score", 0), 1),
            }
            for sc in score_cols:
                sig[sc] = round(row[sc], 1)
            signals.append(sig)

    return {
        "scan_date": scan_date or datetime.now().strftime("%Y-%m-%d"),
        "scan_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "elapsed_seconds": round(elapsed, 1),
        "market_env": env,
        "stats": stats,
        "factors_used": [f.name for f in factors],
        "factor_weights": {f.name: f.weight for f in factors},
        "signals": signals,
    }


def format_for_llm(data: dict) -> str:
    """格式化为 LLM 可读文本，可直接嵌入 Prompt"""
    lines = []
    lines.append(f"## 因子选股扫描结果")
    lines.append(f"扫描日期: {data['scan_date']}")
    lines.append(f"扫描耗时: {data['elapsed_seconds']}秒")
    lines.append("")

    # 市场环境
    env = data["market_env"]
    lines.append(f"### 市场环境")
    lines.append(f"- 沪深300状态: {env.get('status', '未知')}")
    if "index_close" in env:
        lines.append(f"- 指数收盘: {env['index_close']:.2f}")
        lines.append(f"- 20日均线: {env['ma20']:.2f}")
        lines.append(f"- 偏离度: {env['diff_pct']:.1f}%")
    safe = env.get("safe", True)
    lines.append(f"- 开仓建议: {'可以开仓' if safe else '谨慎操作（大盘在均线下方）'}")
    lines.append("")

    # 扫描统计
    stats = data["stats"]
    lines.append(f"### 扫描统计")
    lines.append(f"- 全市场: {stats.get('total_stocks', '?')} 只")
    lines.append(f"- 粗筛后: {stats.get('after_coarse', '?')} 只")
    lines.append(f"- 最终命中: {stats.get('hits', 0)} 只")
    lines.append("")

    # 使用的因子
    lines.append(f"### 选股因子")
    factor_desc = {
        "limit_up_gene": "涨停基因（半年内有涨停记录）",
        "below_limit_up_price": "跌破涨停价（当前价低于最近涨停价）",
        "consolidation": "横盘筑底（60日振幅<15%+缩量）",
        "bbiboll": "BBIBOLL低轨反弹（通达信标准N=11,M=6）",
        "consecutive_decline": "连跌���量（���续下跌+成交量萎���）",
    }
    weights = data.get("factor_weights", {})
    for f in data["factors_used"]:
        w = weights.get(f, 1.0)
        lines.append(f"- {factor_desc.get(f, f)}（权重: {w}）")
    lines.append("")

    # 命中股票
    signals = data["signals"]
    if not signals:
        lines.append("### 命中股票: 无")
    else:
        lines.append(f"### 命中股票（{len(signals)}只，按综合评分排序）")
        lines.append("")
        # 表头
        score_keys = [k for k in signals[0] if k.endswith("_score") and k != "composite_score"]
        header = "| 排名 | 代码 | 名称 | 收盘价 | 涨跌幅 | 综合评分 |"
        sep = "|------|------|------|--------|--------|----------|"
        for sk in score_keys:
            label = sk.replace("_score", "")
            header += f" {label} |"
            sep += "------|"
        lines.append(header)
        lines.append(sep)

        for i, sig in enumerate(signals, 1):
            row = f"| {i} | {sig['code']} | {sig['name']} | {sig['close']} | {sig['pct_chg']}% | {sig['composite_score']} |"
            for sk in score_keys:
                row += f" {sig.get(sk, 0)} |"
            lines.append(row)

    lines.append("")
    lines.append("注意: 因子信号仅为量化参考，需结合盘面环境、资金流向综合判断。")
    return "\n".join(lines)


if __name__ == "__main__":
    scan_date = None
    output_json = False

    for arg in sys.argv[1:]:
        if arg == "--json":
            output_json = True
        else:
            scan_date = arg

    data = run_scan(scan_date)

    if output_json:
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_for_llm(data))

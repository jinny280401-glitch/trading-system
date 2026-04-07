# Finance Suite 对接指南

## 概述

`factor_scan.py` 是 trading-system 的独立输出脚本，可被 Finance Suite 的集合竞价模组调用，
将因子选股信号嵌入分析 Prompt。

## 对接方式

### 方式1: 直接调用（推荐）

在 finance-suite 的 `scripts/auction_data.py` 中增加调用:

```python
import subprocess
import json

def get_factor_signals(scan_date: str = None) -> dict:
    """调用 trading-system 因子扫描"""
    cmd = ["python3", "/Users/Zhuanz/trading-system/scripts/factor_scan.py", "--json"]
    if scan_date:
        cmd.append(scan_date)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode == 0:
        return json.loads(result.stdout)
    return {"error": result.stderr}
```

### 方式2: LLM文本输出

直接运行获取可嵌入Prompt的文本:

```bash
python3 /Users/Zhuanz/trading-system/scripts/factor_scan.py 2025-04-03
```

输出即为 Markdown 格式，可直接拼接到 `prompts/auction-analysis.md` 的 Prompt 中。

### 方式3: 作为 OpenClaw Skill 数据源

在 `SKILL.md` 路由表中增加:

```markdown
| 因子扫描、量化选股、因子信号 | 集合竞价 | prompts/auction-analysis.md | scripts/auction_data.py + /Users/Zhuanz/trading-system/scripts/factor_scan.py |
```

## Prompt 模板补充

在 `prompts/auction-analysis.md` 末尾增加:

```markdown
### 六、因子选股信号

基于量化因子扫描，以下股票同时满足多重条件:
- 涨停基因: 半年内有涨停记录（有爆发基因）
- 跌破涨停价: 当前价低于最近涨停价（洗盘充分）
- 连跌缩量: 连续下跌+成交量萎缩（卖压衰竭）

{factor_signals_text}

选股逻辑: 有涨停基因的票 → 涨停后充分洗盘 → 缩量企稳 = 潜在反弹机会
注意: 因子信号仅为量化参考，需结合集合竞价数据、资金流向综合判断。
```

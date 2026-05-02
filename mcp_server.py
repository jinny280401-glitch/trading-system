"""
Trading System MCP Server
黄金坑四重门量化扫描系统，暴露为 MCP 工具供 Claude Code / OpenClaw 调用。

启动方式（stdio 模式）：
  /Users/Zhuanz/trading-system/.venv/bin/python3.12 /Users/Zhuanz/trading-system/mcp_server.py

工具列表：
  - golden_pit_scan       黄金坑全市场扫描（纯缓存 + 实时行情增量）
  - golden_pit_watchlist   观察池：G1-G3已过，距G4的距离排序
  - stock_debug           单股调试：4因子逐日信号 + 评分
  - update_stock_cache    更新指定股票的最新数据（AkShare spot_em）
  - backtest_stock        单股/组合回测
"""

from __future__ import annotations

import json
import sys
import os
import warnings

warnings.filterwarnings("ignore")

# 确保 trading-system 根目录在 import 路径中
_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _ROOT)

from mcp.server.fastmcp import FastMCP

# 无法计算时的默认值（如下轨为0或数据异常）
_DIST_UNAVAILABLE = 999.9

mcp = FastMCP(
    "trading-system",
    instructions=(
        "黄金坑四重门量化扫描 MCP 服务。"
        "四重门：涨停基因 → 跌破涨停价 → 横盘筑底 → BBIBOLL下轨反弹。"
        "数据源：本地Parquet缓存（4900+只A股日线）+ AkShare实时行情。"
        "扫描结果包含 _qc 质检字段，标注数据完整度和时效性。"
        "所有结果仅供研究参考，不构成投资建议。"
    ),
)


# ============================================================
# 质检层
# ============================================================

def _qc(status: str, completeness: float, sources: list, **extra) -> dict:
    qc = {
        "status": status,
        "completeness": completeness,
        "sources": sources,
        "fallback_source": "akshare" if "baostock" in sources else None,
        "missing_dimensions": extra.get("missing", []),
        "stale_data": extra.get("stale", []),
    }
    if "error" in extra:
        qc["error"] = extra["error"]
    if "note" in extra:
        qc["note"] = extra["note"]
    return qc


def _wrap(qc: dict, content: str) -> str:
    return json.dumps({"_qc": qc}, ensure_ascii=False) + "\n\n" + content


def _error(msg: str) -> str:
    qc = _qc("failure", 0, [], error=msg)
    return json.dumps({"_qc": qc}, ensure_ascii=False)


# ============================================================
# 内部工具函数
# ============================================================

def _load_cache_df(code: str):
    """从本地缓存读取日线数据"""
    import pandas as pd
    from data.cache import CACHE_DIR
    path = CACHE_DIR / f"{code}.parquet"
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    df["date"] = pd.to_datetime(df["date"])
    return df


def _build_factors(code: str = ""):
    """构建四重门因子"""
    from factors.limit_up import LimitUpGene, BelowLimitUpPrice
    from factors.consolidation import Consolidation
    from factors.bbiboll import BBIBOLLLowerBounce
    from config.settings import FACTORS
    return [
        LimitUpGene(lookback_days=FACTORS["limit_up_gene"]["lookback_days"], code=code, is_st=False),
        BelowLimitUpPrice(lookback_days=FACTORS["below_limit_up_price"]["lookback_days"], code=code, is_st=False),
        Consolidation(**FACTORS["consolidation"]),
        BBIBOLLLowerBounce(**FACTORS["bbiboll"]),
    ]


def _check_gates(df, code: str = ""):
    """检查四重门，返回 (pass_count, gate_results, scores)"""
    from config.settings import FACTOR_WEIGHTS
    factors = _build_factors(code)
    gate_names = ["limit_up_gene", "below_limit_up_price", "consolidation", "bbiboll"]
    results = {}
    scores = {}
    pass_count = 0

    for f, name in zip(factors, gate_names):
        sig = f.compute(df)
        passed = bool(sig.iloc[-1]) if len(sig) > 0 else False
        results[name] = passed
        if passed:
            pass_count += 1
            s = f.score(df)
            scores[name] = round(float(s.iloc[-1]), 1)
        else:
            scores[name] = 0
            break  # early exit

    # composite score
    if pass_count == 4:
        w = FACTOR_WEIGHTS
        tw = sum(w.values())
        composite = sum(scores.get(n, 0) * w[n] for n in gate_names) / tw
        scores["composite"] = round(composite, 1)

    return pass_count, results, scores


# ============================================================
# Tool 1: 黄金坑全市场扫描
# ============================================================
@mcp.tool()
def golden_pit_scan(use_realtime: bool = False) -> str:
    """全市场黄金坑四重门扫描。
    默认使用本地缓存（秒级完成，4900+只票）。
    设 use_realtime=True 会先拉 AkShare 实时行情追加今日数据（约3-4分钟）。
    返回：命中票列表 + 观察池（G1-G3过但G4未触发）。"""
    try:
        import pandas as pd
        from data.cache import CACHE_DIR
        from factors.bbiboll import compute_bbiboll

        cache_files = sorted(CACHE_DIR.glob("*.parquet"))
        codes = [f.stem for f in cache_files if not f.stem.startswith("8")]

        # 可选：拉实时行情追加今日数据
        spot_data = {}
        if use_realtime:
            try:
                import akshare as ak
                spot = ak.stock_zh_a_spot_em()
                for _, row in spot.iterrows():
                    c = str(row.get("代码", ""))
                    if c:
                        spot_data[c] = row
            except Exception:
                pass

        hits = []
        watchlist = []

        for code in codes:
            try:
                df = _load_cache_df(code)
                if df is None or len(df) < 120:
                    continue

                # 追加实时行情
                if code in spot_data:
                    r = spot_data[code]
                    price = r.get("最新价")
                    if pd.notna(price) and price > 0:
                        today = pd.DataFrame([{
                            "date": pd.Timestamp.now().normalize(),
                            "open": r.get("今开", price), "high": r.get("最高", price),
                            "low": r.get("最低", price), "close": price,
                            "volume": int(r.get("成交量", 0)),
                            "amount": r.get("成交额", 0), "pct_chg": r.get("涨跌幅", 0),
                        }])
                        df = pd.concat([df, today]).drop_duplicates(subset="date").sort_values("date").reset_index(drop=True)

                pass_count, results, scores = _check_gates(df, code)

                if pass_count >= 3:
                    close = df["close"]
                    bbi, upper, lower = compute_bbiboll(close)
                    last_close = float(close.iloc[-1])
                    last_lower = float(lower.iloc[-1])
                    dist_pct = round((last_close - last_lower) / last_lower * 100, 1) if last_lower > 0 else _DIST_UNAVAILABLE
                    last_date = df["date"].iloc[-1].strftime("%Y-%m-%d")

                    entry = {
                        "code": code, "close": round(last_close, 2), "date": last_date,
                        "lower": round(last_lower, 2), "dist_to_lower_pct": dist_pct,
                        "gates_passed": pass_count, **scores,
                    }
                    if pass_count == 4:
                        hits.append(entry)
                    else:
                        at_lower = last_close <= last_lower
                        entry["at_lower_now"] = at_lower
                        watchlist.append(entry)
            except Exception:
                continue

        # 排序
        hits.sort(key=lambda x: x.get("composite", 0), reverse=True)
        watchlist.sort(key=lambda x: x.get("dist_to_lower_pct", _DIST_UNAVAILABLE))

        last_date = df["date"].iloc[-1].strftime("%Y-%m-%d") if codes else "unknown"
        note = f"数据截至{last_date}"
        if use_realtime and spot_data:
            note += f"，已追加{len(spot_data)}只票实时行情"

        sources = ["local_cache"]
        if use_realtime:
            sources.append("akshare_realtime")

        qc = _qc(
            "success" if hits else "partial",
            1.0 if hits else 0.5,
            sources,
            note=note,
        )

        output_lines = [f"扫描 {len(codes)} 只票 | {note}"]
        output_lines.append(f"\n=== 黄金坑信号（四重门全命中）: {len(hits)} 只 ===")
        if hits:
            for h in hits:
                output_lines.append(
                    f"  {h['code']} | 收盘{h['close']} | 综合{h.get('composite',0)} | "
                    f"G1:{h.get('limit_up_gene',0)} G2:{h.get('below_limit_up_price',0)} "
                    f"G3:{h.get('consolidation',0)} G4:{h.get('bbiboll',0)}"
                )
        else:
            output_lines.append("  暂无")

        output_lines.append(f"\n=== 观察池（G1-G3过，等G4）: {len(watchlist)} 只 ===")
        for w in watchlist[:20]:
            flag = " << 已破轨" if w.get("at_lower_now") else ""
            output_lines.append(
                f"  {w['code']} | 收盘{w['close']} | 下轨{w['lower']} | 距下轨{w['dist_to_lower_pct']}%{flag}"
            )
        if len(watchlist) > 20:
            output_lines.append(f"  ... 共 {len(watchlist)} 只")

        return _wrap(qc, "\n".join(output_lines))

    except Exception as e:
        return _error(f"golden_pit_scan 异常: {e}")


# ============================================================
# Tool 2: 观察池详情
# ============================================================
@mcp.tool()
def golden_pit_watchlist(top_n: int = 20) -> str:
    """查看黄金坑观察池：已通过G1-G3的股票，按距BBIBOLL下轨距离排序。
    距离越近 = 越接近触发G4入场信号。at_lower_now=True 表示已破轨等反弹。"""
    try:
        import pandas as pd
        from data.cache import CACHE_DIR
        from factors.bbiboll import compute_bbiboll

        cache_files = sorted(CACHE_DIR.glob("*.parquet"))
        codes = [f.stem for f in cache_files if not f.stem.startswith("8")]
        results = []

        for code in codes:
            try:
                df = _load_cache_df(code)
                if df is None or len(df) < 120:
                    continue
                pass_count, gate_results, scores = _check_gates(df, code)
                if pass_count < 3:
                    continue

                close = df["close"]
                bbi, upper, lower = compute_bbiboll(close)
                last_close = float(close.iloc[-1])
                last_lower = float(lower.iloc[-1])
                dist = round((last_close - last_lower) / last_lower * 100, 1) if last_lower > 0 else _DIST_UNAVAILABLE
                recent_at = bool((close.tail(5) <= lower.tail(5)).any())

                results.append({
                    "code": code,
                    "close": round(last_close, 2),
                    "lower": round(last_lower, 2),
                    "dist_pct": dist,
                    "at_lower_now": last_close <= last_lower,
                    "touched_5d": recent_at,
                    "date": df["date"].iloc[-1].strftime("%Y-%m-%d"),
                    "g3_score": scores.get("consolidation", 0),
                })
            except Exception:
                continue

        results.sort(key=lambda x: x["dist_pct"])
        qc = _qc("success", 1.0, ["local_cache"])

        lines = [f"观察池: {len(results)} 只票（G1-G3已过，按距下轨排序）\n"]
        for r in results[:top_n]:
            flag = ""
            if r["at_lower_now"]:
                flag = " [已破轨]"
            elif r["touched_5d"]:
                flag = " [5日内触轨]"
            lines.append(
                f"  {r['code']} | 收{r['close']} 下轨{r['lower']} | "
                f"距{r['dist_pct']}%{flag} | 横盘分{r['g3_score']} | {r['date']}"
            )

        return _wrap(qc, "\n".join(lines))

    except Exception as e:
        return _error(f"golden_pit_watchlist 异常: {e}")


# ============================================================
# Tool 3: 单股调试
# ============================================================
@mcp.tool()
def stock_debug(code: str) -> str:
    """单股调试：查看指定股票的四重门因子逐日信号、评分、BBIBOLL位置。
    code: 6位股票代码，如 000900。"""
    try:
        import pandas as pd
        from factors.bbiboll import compute_bbiboll

        df = _load_cache_df(code)
        if df is None:
            return _error(f"缓存中无 {code} 的数据")
        if len(df) < 120:
            return _error(f"{code} 数据不足120天（当前{len(df)}天）")

        pass_count, gate_results, scores = _check_gates(df, code)

        close = df["close"]
        bbi, upper, lower = compute_bbiboll(close)
        last_close = float(close.iloc[-1])
        last_lower = float(lower.iloc[-1])
        last_upper = float(upper.iloc[-1])
        last_bbi = float(bbi.iloc[-1])
        last_date = df["date"].iloc[-1].strftime("%Y-%m-%d")

        lines = [
            f"=== {code} 调试 ({last_date}) ===",
            f"收盘: {round(last_close,2)}  涨跌幅: {round(float(df['pct_chg'].iloc[-1]),2)}%",
            f"",
            f"BBIBOLL 位置:",
            f"  上轨: {round(last_upper,2)}",
            f"  BBI:  {round(last_bbi,2)}",
            f"  下轨: {round(last_lower,2)}",
            f"  当前距下轨: {round((last_close-last_lower)/last_lower*100,1)}%",
            f"",
            f"四重门状态:",
        ]

        gate_labels = {
            "limit_up_gene": "G1 涨停基因",
            "below_limit_up_price": "G2 跌破涨停价",
            "consolidation": "G3 横盘筑底",
            "bbiboll": "G4 BBIBOLL反弹",
        }
        for name, label in gate_labels.items():
            passed = gate_results.get(name, False)
            score = scores.get(name, "-")
            status = "PASS" if passed else "FAIL"
            lines.append(f"  {label}: {status}  评分: {score}")

        if pass_count == 4:
            lines.append(f"\n  综合评分: {scores.get('composite', 0)}")
            lines.append(f"  >>> 黄金坑信号触发！")

        # 最近10日K线
        lines.append(f"\n最近10日:")
        recent = df.tail(10)
        for _, row in recent.iterrows():
            d = row["date"].strftime("%m-%d")
            lines.append(
                f"  {d} 收{round(row['close'],2)} 涨跌{round(row['pct_chg'],2)}% 量{int(row['volume'])}"
            )

        qc = _qc("success", 1.0, ["local_cache"])
        return _wrap(qc, "\n".join(lines))

    except Exception as e:
        return _error(f"stock_debug 异常: {e}")


# ============================================================
# Tool 4: 更新股票缓存
# ============================================================
@mcp.tool()
def update_stock_cache(codes: str = "") -> str:
    """用 AkShare 实时行情更新指定股票的缓存数据。
    codes: 逗号分隔的股票代码，如 "000900,603260"。留空则更新观察池所有票。
    注意：依赖网络，可能需要3-5分钟。"""
    try:
        import pandas as pd
        import akshare as ak
        from data.cache import CACHE_DIR, _atomic_write_parquet

        # 拉实时行情
        spot = ak.stock_zh_a_spot_em()

        target_codes = []
        if codes.strip():
            target_codes = [c.strip() for c in codes.split(",")]
        else:
            # 更新观察池
            cache_files = sorted(CACHE_DIR.glob("*.parquet"))
            all_codes = [f.stem for f in cache_files if not f.stem.startswith("8")]
            for code in all_codes:
                try:
                    df = _load_cache_df(code)
                    if df is None or len(df) < 120:
                        continue
                    pass_count, _, _ = _check_gates(df, code)
                    if pass_count >= 3:
                        target_codes.append(code)
                except Exception:
                    continue

        updated = 0
        failed = 0
        for code in target_codes:
            try:
                row = spot[spot["代码"] == code]
                if row.empty:
                    failed += 1
                    continue
                r = row.iloc[0]
                price = r.get("最新价")
                if pd.isna(price) or price <= 0:
                    failed += 1
                    continue

                today = pd.DataFrame([{
                    "date": pd.Timestamp.now().normalize(),
                    "open": r.get("今开", price), "high": r.get("最高", price),
                    "low": r.get("最低", price), "close": price,
                    "volume": int(r.get("成交量", 0)),
                    "amount": r.get("成交额", 0), "pct_chg": r.get("涨跌幅", 0),
                }])

                cache_path = CACHE_DIR / f"{code}.parquet"
                if cache_path.exists():
                    old = pd.read_parquet(cache_path)
                    old["date"] = pd.to_datetime(old["date"])
                    merged = pd.concat([old, today]).drop_duplicates(subset="date").sort_values("date")
                    _atomic_write_parquet(merged, cache_path)
                    updated += 1
                else:
                    failed += 1
            except Exception:
                failed += 1

        qc = _qc(
            "success" if updated > 0 else "failure",
            round(updated / max(len(target_codes), 1), 2),
            ["akshare_realtime"],
        )
        return _wrap(qc, f"更新完成: 成功 {updated}/{len(target_codes)}, 失败 {failed}")

    except Exception as e:
        return _error(f"update_stock_cache 异常: {e}")


# ============================================================
# Tool 5: 回测
# ============================================================
@mcp.tool()
def backtest_stock(code: str, start_date: str = "2024-01-01", end_date: str = "2025-04-03") -> str:
    """对指定股票运行黄金坑策略回测。
    返回：总收益率、年化收益率、最大回撤、Sharpe、Calmar、胜率、交易明细。
    code: 6位股票代码。"""
    try:
        import io
        from contextlib import redirect_stdout
        from data.provider import DataProvider
        from config.settings import FACTORS, SIGNAL_COMBO, FACTOR_WEIGHTS, BACKTEST
        from factors.limit_up import LimitUpGene, BelowLimitUpPrice
        from factors.consolidation import Consolidation
        from factors.bbiboll import BBIBOLLLowerBounce
        from backtest.backtester import Backtester

        provider = DataProvider()
        factors = _build_factors(code)
        for f in factors:
            f.weight = FACTOR_WEIGHTS.get(f.name, 1.0)

        bt = Backtester(
            provider=provider, factors=factors,
            initial_capital=BACKTEST["initial_capital"],
            commission_rate=BACKTEST["commission_rate"],
            stamp_tax=BACKTEST["stamp_tax"],
            slippage=BACKTEST["slippage"],
            hold_days=BACKTEST["hold_days"],
            stop_loss=BACKTEST["stop_loss"],
            take_profit=BACKTEST["take_profit"],
            max_positions=BACKTEST["max_positions"],
        )

        result = bt.run(code, start_date, end_date)

        buf = io.StringIO()
        with redirect_stdout(buf):
            print(result.summary())
            if not result.trades.empty:
                print(f"\n=== 交易明细（{len(result.trades)}笔）===")
                print(result.trades.to_string(index=False))

        qc = _qc("success", 1.0, ["local_cache"])
        return _wrap(qc, buf.getvalue())

    except Exception as e:
        return _error(f"backtest_stock 异常: {e}")


# ============================================================
# 启动入口
# ============================================================
if __name__ == "__main__":
    mcp.run(transport="stdio")

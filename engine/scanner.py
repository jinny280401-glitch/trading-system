"""
两阶段扫描引擎

阶段1: AkShare全市场快照粗筛（3秒，5000→~500）
阶段2: BaoStock历史日线精筛（30秒，因子计算）
"""

import copy
import pandas as pd
from datetime import datetime, timedelta
from typing import List
from concurrent.futures import ThreadPoolExecutor, as_completed

from data.provider import DataProvider
from factors.base import BaseFactor
from factors.market_env import MarketEnvironment


class Scanner:
    """两阶段全市场扫描器"""

    def __init__(self, provider: DataProvider, factors: List[BaseFactor]):
        self.provider = provider
        self.factors = factors
        self.market_env = MarketEnvironment()

    def scan(self, scan_date: str = None, max_workers: int = 8) -> dict:
        """
        全市场扫描，返回完整结果

        Returns:
            {
                "hits": DataFrame,         # 命中的股票
                "market_env": dict,         # 市场环境
                "stats": dict,              # 扫描统计
            }
        """
        if scan_date is None:
            scan_date = datetime.now().strftime("%Y-%m-%d")

        start_date = (datetime.strptime(scan_date, "%Y-%m-%d") - timedelta(days=400)).strftime("%Y-%m-%d")

        # ── 加载市场环境 ──
        self.market_env.load(self.provider, start_date, scan_date)
        env = self.market_env.get_status()
        print(f"市场环境: {env['status']}")

        # ── 阶段1: 粗筛 ──
        print("阶段1: 全市场快照粗筛...")
        snapshot = self.provider.get_market_snapshot()

        if snapshot.empty:
            print("  快照获取失败，降级为全量扫描")
            candidates = None
        else:
            # 粗筛条件
            mask = (
                ~snapshot['is_st']
                & ~snapshot['code'].str.startswith('8')  # 北交所
                & (snapshot['price'].notna())
                & (snapshot['price'] > 0)
                & (snapshot['market_cap'].notna())
                & (snapshot['market_cap'] > 2_000_000_000)  # 市值>20亿
            )
            # PE过滤：排除亏损（PE<0或None），但允许PE=None（有些票没PE数据）
            pe_ok = (snapshot['pe'].isna()) | (snapshot['pe'] > 0)
            mask = mask & pe_ok

            candidates = snapshot[mask].copy()
            print(f"  全市场 {len(snapshot)} 只 → 粗筛后 {len(candidates)} 只")

        # ── 阶段2: 精筛 ──
        print(f"阶段2: 历史数据精筛（{max_workers}线程并发）...")

        if candidates is not None:
            codes = candidates['code'].tolist()
            names = dict(zip(candidates['code'], candidates['name']))
        else:
            # 降级：优先用本地缓存文件列表，避免依赖网络
            from data.cache import CACHE_DIR
            cache_files = list(CACHE_DIR.glob("*.parquet"))
            if cache_files:
                codes = [f.stem for f in cache_files if not f.stem.startswith('8')]
                print(f"  使用本地缓存: {len(codes)} 只股票")
            else:
                # 最终降级：BaoStock 拉列表
                import baostock as bs
                from data.cache import _ensure_login
                _ensure_login()
                rs = bs.query_stock_basic()
                rows = []
                while rs.next():
                    rows.append(rs.get_row_data())
                stock_df = pd.DataFrame(rows, columns=rs.fields)
                stock_df = stock_df[(stock_df['type'] == '1') & (stock_df['status'] == '1')]
                codes = [c.split('.')[1] for c in stock_df['code'] if not c.startswith('bj.')]
            names = {}

        results = []
        total = len(codes)

        def _process_one(code):
            try:
                df = self.provider.get_daily(code, start_date, scan_date)
                if df.empty or len(df) < 30:
                    return None

                # 每线程独立副本，避免竞态
                local_factors = [copy.copy(f) for f in self.factors]
                is_st = names.get(code, '').find('ST') >= 0
                for factor in local_factors:
                    if hasattr(factor, 'code'):
                        factor.code = code
                    if hasattr(factor, 'is_st'):
                        factor.is_st = is_st

                # 计算所有因子
                factor_results = {}
                factor_scores = {}
                for factor in local_factors:
                    signals = factor.compute(df)
                    last_signal = signals.iloc[-1] if len(signals) > 0 else False
                    factor_results[factor.name] = bool(last_signal)
                    if not last_signal:
                        return None  # 一个不满足就跳过
                    # 计算评分
                    scores = factor.score(df)
                    factor_scores[f"{factor.name}_score"] = round(float(scores.iloc[-1]), 1)

                # 综合评分 = 加权平均
                weights = {f.name: f.weight for f in local_factors}
                total_weight = sum(weights.values())
                composite = sum(
                    factor_scores[f"{name}_score"] * weights[name]
                    for name in weights
                ) / total_weight if total_weight > 0 else 0

                # 全部因子命中
                return {
                    "code": code,
                    "name": names.get(code, ""),
                    "close": df["close"].iloc[-1],
                    "pct_chg": df["pct_chg"].iloc[-1],
                    "composite_score": round(composite, 1),
                    **factor_scores,
                    **factor_results,
                }
            except Exception as e:
                import logging
                logging.debug(f"扫描 {code} 异常: {e}")
                return None

        done = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_process_one, c): c for c in codes}
            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    results.append(result)
                done += 1
                if done % 200 == 0:
                    print(f"  精筛进度: {done}/{total}, 已命中 {len(results)} 只")

        hits_df = pd.DataFrame(results)
        if not hits_df.empty and "composite_score" in hits_df.columns:
            hits_df = hits_df.sort_values("composite_score", ascending=False).reset_index(drop=True)
        stats = {
            "scan_date": scan_date,
            "total_stocks": len(snapshot) if not snapshot.empty else total,
            "after_coarse": len(codes),
            "hits": len(results),
            "market_safe": env.get('safe', True),
        }

        print(f"\n扫描完成！{stats['total_stocks']} 只 → 粗筛 {stats['after_coarse']} 只 → 命中 {stats['hits']} 只")

        return {"hits": hits_df, "market_env": env, "stats": stats}

    def scan_single(self, code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """单股调试：计算全部因子的逐日信号"""
        df = self.provider.get_daily(code, start_date, end_date)
        if df.empty:
            return df

        for factor in self.factors:
            if hasattr(factor, 'code'):
                factor.code = code
            df[factor.name] = factor.compute(df)

        factor_cols = [f.name for f in self.factors]
        df["signal"] = df[factor_cols].all(axis=1)
        return df

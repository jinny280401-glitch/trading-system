"""
数据获取层 — 两级数据源

第一级: AkShare 全市场快照（粗筛用，1次调用3秒）
第二级: BaoStock 历史日线 + 本地Parquet缓存（精筛用）
"""

import os
import socket
import urllib.request
import json
import ssl
import urllib.parse
import pandas as pd
from datetime import datetime
from .cache import get_daily_cached, batch_cache


def _fix_network():
    """强制IPv4 + 绕过系统代理（AkShare访问东财需要）"""
    _orig = socket.getaddrinfo
    def ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
        return _orig(host, port, socket.AF_INET, type, proto, flags)
    socket.getaddrinfo = ipv4_only
    for k in list(os.environ):
        if 'proxy' in k.lower():
            del os.environ[k]
    os.environ['NO_PROXY'] = '*'
    urllib.request.getproxies = lambda: {}

_fix_network()

_SSL_CTX = ssl.create_default_context()


def _http_get(url: str, params: dict = None, timeout: int = 15) -> str:
    """用标准库urllib发GET请求（绕过requests/urllib3的SSL兼容问题）"""
    if params:
        url = url + '?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
        'Referer': 'https://finance.eastmoney.com/',
    })
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
        return resp.read().decode('utf-8')


class DataProvider:
    """两级数据源"""

    def get_market_snapshot(self) -> pd.DataFrame:
        """
        第一级：全市场实时快照（1次调用，~3秒）

        返回: DataFrame[code, name, price, pct_chg, volume, amount,
                         pe, pb, market_cap, is_st]
        用途: 粗筛
        """
        url = 'https://push2.eastmoney.com/api/qt/clist/get'
        params = {
            'pn': '1', 'pz': '10000', 'po': '1', 'np': '1',
            'ut': 'bd1d9ddb04089700cf9c27f6f7426281',
            'fltt': '2', 'invt': '2', 'fid': 'f3',
            'fs': 'm:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23',
            'fields': 'f2,f3,f5,f6,f9,f12,f14,f20,f23',
            # f2=最新价 f3=涨跌幅 f5=成交量 f6=成交额
            # f9=PE f12=代码 f14=名称 f20=总市值 f23=PB
        }
        try:
            text = _http_get(url, params)
            data = json.loads(text)
            items = data['data']['diff']
            rows = []
            for item in items:
                code = str(item.get('f12', ''))
                name = str(item.get('f14', ''))
                rows.append({
                    'code': code,
                    'name': name,
                    'price': item.get('f2'),
                    'pct_chg': item.get('f3'),
                    'volume': item.get('f5'),
                    'amount': item.get('f6'),
                    'pe': item.get('f9'),
                    'pb': item.get('f23'),
                    'market_cap': item.get('f20'),
                })
            df = pd.DataFrame(rows)
            # 标记ST
            df['is_st'] = df['name'].str.contains('ST|退', na=False)
            return df
        except Exception as e:
            print(f"全市场快照获取失败: {e}")
            return pd.DataFrame()

    def get_daily(self, code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        第二级：历史日线（带缓存）
        优先读本地Parquet，不命中则拉BaoStock
        """
        return get_daily_cached(code, start_date, end_date)

    def batch_load(self, codes: list, start_date: str, end_date: str, max_workers: int = 8):
        """批量预加载历史数据到本地缓存"""
        batch_cache(codes, start_date, end_date, max_workers)

    def get_index_daily(self, index_code: str = "sh.000300",
                        start_date: str = None, end_date: str = None) -> pd.DataFrame:
        """获取指数日线（沪深300等），用于市场环境判断和基准对比"""
        import baostock as bs
        from .cache import _ensure_login
        _ensure_login()
        rs = bs.query_history_k_data_plus(
            index_code,
            "date,open,high,low,close,volume",
            start_date=start_date,
            end_date=end_date,
            frequency="d",
        )
        rows = []
        while rs.next():
            rows.append(rs.get_row_data())
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows, columns=rs.fields)
        df["date"] = pd.to_datetime(df["date"])
        for col in ["open", "high", "low", "close"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype(int)
        return df.sort_values("date").reset_index(drop=True)

"""
本地 Parquet 缓存 + 增量更新
首次冷启动拉全量，之后每日只追加增量
"""

import os
import tempfile
import threading
import pandas as pd
import baostock as bs
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

_login_lock = threading.Lock()
_logged_in = False

# 每个股票代码一把锁，防止并发写同一个 parquet 文件
_file_locks = {}
_file_locks_lock = threading.Lock()


def _get_file_lock(code: str) -> threading.Lock:
    with _file_locks_lock:
        if code not in _file_locks:
            _file_locks[code] = threading.Lock()
        return _file_locks[code]


def _ensure_login():
    global _logged_in
    with _login_lock:
        if not _logged_in:
            bs.login()
            _logged_in = True


def _to_bs_code(code: str) -> str:
    """600519 -> sh.600519"""
    if code.startswith("6") or code.startswith("9"):
        return f"sh.{code}"
    return f"sz.{code}"


def _fetch_from_baostock(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """从BaoStock拉取日线数据"""
    _ensure_login()
    bs_code = _to_bs_code(code)
    rs = bs.query_history_k_data_plus(
        bs_code,
        "date,open,high,low,close,volume,amount,pctChg",
        start_date=start_date,
        end_date=end_date,
        frequency="d",
        adjustflag="2",  # 前复权
    )
    rows = []
    while rs.next():
        rows.append(rs.get_row_data())
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=rs.fields)
    df = df.rename(columns={"pctChg": "pct_chg"})
    df["date"] = pd.to_datetime(df["date"])
    for col in ["open", "high", "low", "close", "amount", "pct_chg"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype(int)
    df = df[df["volume"] > 0]  # 排除停牌日
    return df.sort_values("date").reset_index(drop=True)


def _fetch_from_akshare(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """从AkShare拉取日线数据（BaoStock降级备选）"""
    try:
        import akshare as ak
        df = ak.stock_zh_a_hist(
            symbol=code, period="daily",
            start_date=start_date.replace("-", ""),
            end_date=end_date.replace("-", ""),
            adjust="qfq",
        )
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.rename(columns={
            "日期": "date", "开盘": "open", "最高": "high",
            "最低": "low", "收盘": "close", "成交量": "volume",
            "成交额": "amount", "涨跌幅": "pct_chg",
        })
        df["date"] = pd.to_datetime(df["date"])
        for col in ["open", "high", "low", "close", "amount", "pct_chg"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        if "volume" in df.columns:
            df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype(int)
        df = df[df["volume"] > 0]
        return df[["date", "open", "high", "low", "close", "volume", "amount", "pct_chg"]].sort_values("date").reset_index(drop=True)
    except Exception:
        return pd.DataFrame()


def _atomic_write_parquet(df: pd.DataFrame, path: Path):
    """原子写入：先写临时文件再 rename，防止写到一半崩溃导致文件损坏"""
    fd, tmp_path = tempfile.mkstemp(suffix=".parquet", dir=path.parent)
    try:
        os.close(fd)
        df.to_parquet(tmp_path, index=False)
        os.replace(tmp_path, path)  # 原子操作
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def get_daily_cached(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    带缓存的日线数据获取（线程安全）
    - 缓存命中：直接读 parquet（毫秒级）
    - 部分命中：只拉增量数据
    - 未命中：全量拉取并缓存
    """
    cache_path = CACHE_DIR / f"{code}.parquet"
    lock = _get_file_lock(code)

    with lock:
        if cache_path.exists():
            df = pd.read_parquet(cache_path)
            df["date"] = pd.to_datetime(df["date"])
            last_date = df["date"].max()
            target_end = pd.Timestamp(end_date)

            if last_date >= target_end:
                # 缓存完全命中
                mask = (df["date"] >= start_date) & (df["date"] <= end_date)
                return df[mask].reset_index(drop=True)

            # 增量拉取（BaoStock → AkShare → 用已有缓存）
            next_day = (last_date + timedelta(days=1)).strftime("%Y-%m-%d")
            new_data = pd.DataFrame()
            try:
                new_data = _fetch_from_baostock(code, next_day, end_date)
            except Exception:
                pass
            if new_data.empty:
                try:
                    new_data = _fetch_from_akshare(code, next_day, end_date)
                except Exception:
                    pass
            if not new_data.empty:
                df = pd.concat([df, new_data]).drop_duplicates(subset="date").sort_values("date")
                _atomic_write_parquet(df, cache_path)

            mask = (df["date"] >= start_date) & (df["date"] <= end_date)
            return df[mask].reset_index(drop=True)

        # 首次全量拉取（BaoStock优先，失败降级AkShare）
        df = _fetch_from_baostock(code, start_date, end_date)
        if df.empty:
            df = _fetch_from_akshare(code, start_date, end_date)
        if not df.empty:
            _atomic_write_parquet(df, cache_path)
        return df


def batch_cache(codes: list, start_date: str, end_date: str, max_workers: int = 8):
    """
    并发批量拉取并缓存
    用于首次冷启动或批量更新
    """
    _ensure_login()
    total = len(codes)
    done = 0
    failed = 0

    def _fetch_one(code):
        try:
            return code, get_daily_cached(code, start_date, end_date)
        except Exception:
            return code, pd.DataFrame()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_fetch_one, c): c for c in codes}
        for future in as_completed(futures):
            code, df = future.result()
            done += 1
            if df.empty:
                failed += 1
            if done % 100 == 0:
                print(f"  缓存进度: {done}/{total} (失败: {failed})")

    print(f"缓存完成: {done}/{total}, 失败: {failed}")

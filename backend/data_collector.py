"""
EMCT — AKShare 数据采集模块
日线拉取、缓存、股票池同步
"""
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
from database import get_db


def fetch_daily_kline(code: str, days: int = 60) -> list[dict]:
    """拉取单只股票/指数历史日线（前复权）"""
    try:
        # 指数代码（000xxx/399xxx）用 stock_zh_index_daily
        if code.startswith(("000", "399")):
            prefix = "sh" if code.startswith("000") else "sz"
            symbol = f"{prefix}{code}"
            df = ak.stock_zh_index_daily(symbol=symbol)
        else:
            prefix = "sh" if code.startswith(("6", "9")) else "sz"
            symbol = f"{prefix}{code}"
            df = ak.stock_zh_a_daily(symbol=symbol, adjust="qfq")
        if df is None or df.empty:
            print(f"  ⚠️ {code} 无数据")
            return []
        # stock_zh_a_daily 返回英文列名: date, open, high, low, close, volume, amount
        df = df.tail(days)
        rows = []
        for _, row in df.iterrows():
            rows.append({
                "code": code,
                "date": str(row["date"])[:10],
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
                "amount": float(row["amount"]) if "amount" in row else 0,
            })
        return rows
    except Exception as e:
        print(f"  ❌ {code} 拉取失败: {e}")
        return []


def save_klines(rows: list[dict]) -> int:
    """保存日线到数据库（INSERT OR IGNORE 防重复）"""
    if not rows:
        return 0
    db = get_db()
    count = 0
    for r in rows:
        try:
            db.execute("""
                INSERT OR IGNORE INTO daily_kline (code, date, open, high, low, close, volume, amount)
                VALUES (?,?,?,?,?,?,?,?)
            """, (r["code"], r["date"], r["open"], r["high"], r["low"], r["close"], r["volume"], r["amount"]))
            if db.total_changes > 0:
                count += 1
        except Exception as e:
            print(f"  DB写入失败 {r['code']} {r['date']}: {e}")
    db.commit()
    db.close()
    return count


def sync_all_klines(days: int = 60) -> dict:
    """同步所有活跃股票日线"""
    db = get_db()
    stocks = db.execute(
        "SELECT code, name FROM stock_pool WHERE active=1 ORDER BY id"
    ).fetchall()
    db.close()

    result = {"total": len(stocks), "new": 0, "errors": 0}
    for s in stocks:
        print(f"📊 {s['name']}({s['code']})...", end=" ")
        rows = fetch_daily_kline(s["code"], days=days)
        if rows:
            n = save_klines(rows)
            result["new"] += n
            print(f"+{n}条")
        else:
            result["errors"] += 1
            print("失败")
    return result


def get_kline_stats() -> dict:
    """日线缓存统计"""
    db = get_db()
    row = db.execute("""
        SELECT COUNT(DISTINCT code) as stocks, COUNT(*) as total,
               MIN(date) as earliest, MAX(date) as latest
        FROM daily_kline
    """).fetchone()
    db.close()
    return dict(row) if row else {"stocks": 0, "total": 0}


def warm_up_all(days: int = 120):
    """首次启动预热：拉取120天历史数据"""
    print(f"\n🔥 预热缓存：拉取近{days}天日线...")
    result = sync_all_klines(days=days)
    print(f"✅ 预热完成：{result['total']}只股票，新增{result['new']}条，失败{result['errors']}只")
    return result


if __name__ == "__main__":
    # 手动测试
    print("测试: 拉取贵州茅台近10天数据")
    rows = fetch_daily_kline("600519", days=10)
    for r in rows:
        print(f"  {r['date']} O:{r['open']} H:{r['high']} L:{r['low']} C:{r['close']} V:{r['volume']}")

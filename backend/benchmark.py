"""
沪深300指数数据同步 — 从 AKShare 获取并存储
"""
import sqlite3
from database import get_db


def sync_hs300() -> dict:
    """同步沪深300日线数据"""
    try:
        import akshare as ak
    except ImportError:
        return {"ok": False, "error": "请安装 akshare: pip install akshare"}

    db = get_db()
    
    # 确保表存在
    db.execute("""
        CREATE TABLE IF NOT EXISTS benchmark_kline (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            close REAL NOT NULL,
            UNIQUE(date)
        )
    """)
    
    try:
        # 获取沪深300日线
        df = ak.stock_zh_index_daily(symbol="sh000300")
        df = df.rename(columns={"date": "date", "close": "close"})
        df["date"] = df["date"].astype(str)
        
        inserted = 0
        for _, row in df.iterrows():
            try:
                db.execute(
                    "INSERT OR IGNORE INTO benchmark_kline (date, close) VALUES (?, ?)",
                    (row["date"], float(row["close"]))
                )
                inserted += 1
            except:
                pass
        
        db.commit()
        count = db.execute("SELECT COUNT(*) FROM benchmark_kline").fetchone()[0]
        db.close()
        
        return {
            "ok": True,
            "inserted": inserted,
            "total": count,
            "range": f'{df["date"].iloc[0]} ~ {df["date"].iloc[-1]}' if len(df) > 0 else "无",
        }
    except Exception as e:
        db.close()
        return {"ok": False, "error": str(e)}


def get_benchmark() -> dict:
    """获取沪深300指数数据（用于对比）"""
    db = get_db()
    rows = db.execute(
        "SELECT date, close FROM benchmark_kline ORDER BY date ASC"
    ).fetchall()
    db.close()
    
    if not rows:
        return {"rows": [], "range": "无数据"}
    
    return {
        "rows": [{"date": r["date"], "close": r["close"]} for r in rows],
        "range": f"{rows[0]['date']} ~ {rows[-1]['date']}",
    }


def market_regime_ok() -> tuple[bool, str]:
    """
    市场趋势过滤：
    - 沪深300站上MA20或MA60 → 可以交易
    - 沪深300跌破MA20且跌破MA60 → 熊市，暂停买入
    - 单日暴跌 >2% → 恐慌日，暂停买入
    返回: (是否可交易, 原因)
    """
    db = get_db()
    rows = db.execute(
        "SELECT date, close FROM benchmark_kline ORDER BY date ASC"
    ).fetchall()
    db.close()

    if len(rows) < 60:
        return True, "基准数据不足60条，跳过过滤"

    closes = [r["close"] for r in rows]
    n = len(closes)

    # MA20
    ma20 = sum(closes[-20:]) / 20
    # MA60
    ma60 = sum(closes[-60:]) / 60
    latest = closes[-1]

    # 单日暴跌
    if n >= 2:
        chg_today = (closes[-1] - closes[-2]) / closes[-2] * 100
        if chg_today <= -2:
            return False, f"恐慌日（大盘跌 {chg_today:.1f}%），暂停开仓"

    # 熊市判断
    above_ma20 = latest > ma20
    above_ma60 = latest > ma60

    if not above_ma20 and not above_ma60:
        return False, f"熊市（¥{latest:.0f} < MA20 ¥{ma20:.0f} & MA60 ¥{ma60:.0f}），暂停开仓"

    if above_ma20 and above_ma60:
        return True, f"多头（¥{latest:.0f} > MA20 ¥{ma20:.0f} > MA60 ¥{ma60:.0f}）"

    return True, f"震荡（¥{latest:.0f}, MA20 ¥{ma20:.0f}, MA60 ¥{ma60:.0f}）"

"""数据采集 API"""
from fastapi import APIRouter, BackgroundTasks
from data_collector import sync_all_klines, get_kline_stats, fetch_daily_kline, save_klines

router = APIRouter(prefix="/data", tags=["data"])


def _fetch_intraday_sina(code: str) -> list[dict]:
    """从新浪拉今日5分钟K线，返回 [{time,open,close,high,low,volume}]"""
    import urllib.request, json, re
    prefix = "sh" if code.startswith("6") else "sz"
    url = f"https://quotes.sina.cn/cn/api/jsonp_v2.php/data/CN_MarketDataService.getKLineData?symbol={prefix}{code}&scale=5&datalen=300"
    req = urllib.request.Request(url, headers={"Referer": "https://finance.sina.com.cn"})
    resp = urllib.request.urlopen(req, timeout=8)
    raw = resp.read().decode("gbk", errors="ignore")
    m = re.search(r"data\((\[.*\])", raw, re.DOTALL)
    if not m:
        return []
    data = json.loads(m.group(1))
    from datetime import date
    today = str(date.today())
    rows = []
    for r in data:
        if not r.get("day", "").startswith(today):
            continue
        rows.append({
            "time": r["day"][-8:],
            "open": float(r["open"]),
            "close": float(r["close"]),
            "high": float(r["high"]),
            "low": float(r["low"]),
            "volume": int(float(r.get("volume", 0))),
        })
    return rows


@router.get("/stats")
def stats():
    """日线缓存统计"""
    return get_kline_stats()


@router.post("/sync")
def sync(background_tasks: BackgroundTasks, days: int = 60):
    """同步所有活跃股票日线（后台任务）"""
    background_tasks.add_task(sync_all_klines, days)
    return {"ok": True, "msg": f"开始同步 {days} 天日线"}


@router.post("/sync/{code}")
def sync_one(code: str, days: int = 60):
    """同步单只股票"""
    rows = fetch_daily_kline(code, days=days)
    if not rows:
        return {"ok": False, "msg": f"{code} 拉取失败"}
    n = save_klines(rows)
    return {"ok": True, "new": n, "code": code, "latest": rows[-1]["date"] if rows else ""}


@router.get("/kline/{code}")
def get_kline(code: str, limit: int = 60):
    """获取K线数据（供图表），自动追加今日蜡烛"""
    from database import get_db
    db = get_db()
    rows = db.execute(
        "SELECT date, open, high, low, close, volume FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT ?",
        (code, limit)
    ).fetchall()
    db.close()
    result = [dict(r) for r in reversed(rows)]

    # 追加今日数据（若当日不在DB中）
    from datetime import date
    today = str(date.today())
    if not result or result[-1]["date"] != today:
        intra = _fetch_intraday_sina(code)
        if intra:
            today_row = {
                "date": today,
                "open": intra[0]["open"],
                "high": max(r["high"] for r in intra),
                "low": min(r["low"] for r in intra),
                "close": intra[-1]["close"],
                "volume": sum(r["volume"] for r in intra),
            }
            result.append(today_row)
    return {"rows": result}


@router.get("/intraday/{code}")
def get_intraday(code: str):
    """获取今日分时数据（5分钟K线，新浪源）"""
    try:
        rows = _fetch_intraday_sina(code)
        return {"rows": rows, "live": True}
    except Exception as e:
        return {"rows": [], "error": str(e)}

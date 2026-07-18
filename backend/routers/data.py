"""数据采集 API"""
from fastapi import APIRouter, BackgroundTasks
from data_collector import sync_all_klines, get_kline_stats, fetch_daily_kline, save_klines

router = APIRouter(prefix="/data", tags=["data"])


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

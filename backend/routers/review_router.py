"""复盘 API"""
from fastapi import APIRouter
from review import (
    sync_trade_logs, get_stats, get_monthly_pnl,
    get_stock_performance, get_timeline, add_review, get_review_summary,
    deepseek_analyze
)

router = APIRouter(prefix="/review", tags=["review"])


@router.post("/sync")
def do_sync():
    """从订单同步交易日志"""
    n = sync_trade_logs()
    return {"ok": True, "synced": n}


@router.get("/stats")
def stats():
    return get_stats()


@router.get("/monthly")
def monthly():
    return {"rows": get_monthly_pnl()}


@router.get("/stocks")
def stock_perf():
    return {"rows": get_stock_performance()}


@router.get("/timeline")
def timeline(limit: int = 50):
    return {"rows": get_timeline(limit)}


@router.post("/{trade_id}/note")
def add_note(trade_id: int, review: str = "", tags: str = ""):
    return add_review(trade_id, review, tags)


@router.get("/summary")
def summary():
    """复盘文本摘要（供AI分析用）"""
    return {"summary": get_review_summary()}


@router.get("/analyze")
def analyze():
    """DeepSeek AI 复盘分析"""
    summary_text = get_review_summary()
    result = deepseek_analyze(summary_text)
    return {"analysis": result}

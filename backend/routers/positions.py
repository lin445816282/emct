"""持仓管理 API"""
from fastapi import APIRouter, HTTPException
from database import get_db

router = APIRouter(prefix="/positions", tags=["positions"])

@router.get("")
def list_positions():
    db = get_db()
    rows = db.execute("SELECT * FROM positions ORDER BY id").fetchall()
    db.close()
    return {"rows": [dict(r) for r in rows]}

@router.get("/summary")
def summary():
    """持仓汇总"""
    db = get_db()
    total_value = db.execute("SELECT COALESCE(SUM(market_value),0) FROM positions").fetchone()[0]
    total_pnl = db.execute("SELECT COALESCE(SUM(profit_loss),0) FROM positions").fetchone()[0]
    total_cost = db.execute("SELECT COALESCE(SUM(volume * avg_cost),0) FROM positions").fetchone()[0]
    db.close()
    return {
        "total_value": round(total_value, 2),
        "total_pnl": round(total_pnl, 2),
        "total_cost": round(total_cost, 2),
        "pnl_pct": round(total_pnl / total_cost * 100, 2) if total_cost else 0
    }

"""股票池管理 API"""
from fastapi import APIRouter, HTTPException
from database import get_db

router = APIRouter(prefix="/stock-pool", tags=["stock-pool"])

@router.get("")
def list_pool(sector: str = "", active: int = None):
    db = get_db()
    sql = "SELECT * FROM stock_pool WHERE 1=1"
    params = []
    if sector:
        sql += " AND sector=?"
        params.append(sector)
    if active is not None:
        sql += " AND active=?"
        params.append(active)
    sql += " ORDER BY id"
    rows = db.execute(sql, params).fetchall()
    db.close()
    return {"rows": [dict(r) for r in rows]}

@router.post("/add")
def add_stock(code: str, name: str, market: str, sector: str = ""):
    db = get_db()
    try:
        db.execute(
            "INSERT INTO stock_pool (code, name, market, sector) VALUES (?,?,?,?)",
            (code, name, market, sector)
        )
        db.commit()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(400, str(e))
    finally:
        db.close()

@router.post("/toggle")
def toggle_stock(code: str):
    db = get_db()
    row = db.execute("SELECT active FROM stock_pool WHERE code=?", (code,)).fetchone()
    if not row:
        db.close()
        raise HTTPException(404, "股票不存在")
    new_val = 0 if row["active"] else 1
    db.execute("UPDATE stock_pool SET active=? WHERE code=?", (new_val, code))
    db.commit()
    db.close()
    return {"ok": True, "active": new_val}

@router.delete("/remove")
def remove_stock(code: str):
    db = get_db()
    db.execute("DELETE FROM stock_pool WHERE code=?", (code,))
    db.commit()
    db.close()
    return {"ok": True}

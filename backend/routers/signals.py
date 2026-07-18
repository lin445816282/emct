"""信号记录 API — 扫描分析 + 查询 + 确认 + 权重优化"""
import json
from fastapi import APIRouter
from database import get_db
from analyzer import scan_all, analyze_stock, WEIGHTS

router = APIRouter(prefix="/signals", tags=["signals"])


@router.post("/scan")
def scan_signals():
    """扫描全部活跃股票，生成信号并入库（覆盖当天旧信号）"""
    from datetime import datetime
    now = datetime.now()
    if now.weekday() >= 5:
        return {"ok": False, "error": f"周末休市（{now.strftime('%Y-%m-%d')}），跳过信号扫描"}

    results = scan_all()

    db = get_db()
    # 先清除今天的未处理信号，避免重复
    db.execute("DELETE FROM signals WHERE date=date('now','localtime') AND status='pending'")
    saved = 0
    for r in results:
        db.execute(
            """INSERT INTO signals (code, name, date, signal_type, strength, score, reason, price_ref, status)
               VALUES (?,?,date('now','localtime'),?,?,?,?,?,'pending')""",
            (r["code"], r["name"], r["signal_type"], r["strength"],
             r["score"], " | ".join(r["reasons"]), r["price_ref"])
        )
        saved += 1
    db.commit()
    db.close()

    return {
        "scanned": len(results),
        "saved": saved,
        "signals": results,
        "summary": {
            "strong_buy": sum(1 for r in results if r["signal_type"] == "strong_buy"),
            "buy": sum(1 for r in results if r["signal_type"] == "buy"),
            "hold": sum(1 for r in results if r["signal_type"] == "hold"),
            "sell": sum(1 for r in results if r["signal_type"] == "sell"),
            "strong_sell": sum(1 for r in results if r["signal_type"] == "strong_sell"),
        }
    }


@router.get("/analyze/{code}")
def analyze_single(code: str, name: str = ""):
    """实时分析单只股票（不入库）"""
    if not name:
        db = get_db()
        row = db.execute("SELECT name FROM stock_pool WHERE code=?", (code,)).fetchone()
        db.close()
        name = row["name"] if row else code
    return analyze_stock(code, name)


@router.get("")
def list_signals(status: str = "", signal_type: str = "", limit: int = 20):
    """查询最新信号（每只股票只取最新一条）"""
    db = get_db()
    where = []
    params = []
    if status:
        where.append("s.status=?")
        params.append(status)
    if signal_type:
        where.append("s.signal_type=?")
        params.append(signal_type)
    where_clause = " AND " + " AND ".join(where) if where else ""

    sql = f"""
        SELECT s.* FROM signals s
        INNER JOIN (
            SELECT code, MAX(id) as max_id
            FROM signals
            WHERE date=date('now','localtime')
            GROUP BY code
        ) latest ON s.id = latest.max_id
        {where_clause}
        ORDER BY ABS(s.score) DESC
        LIMIT ?
    """
    params.append(limit)
    rows = db.execute(sql, params).fetchall()
    db.close()
    return {"rows": [dict(r) for r in rows]}


@router.post("/{signal_id}/confirm")
def confirm_signal(signal_id: int):
    db = get_db()
    db.execute("UPDATE signals SET status='confirmed' WHERE id=?", (signal_id,))
    db.commit()
    db.close()
    return {"ok": True}


@router.post("/{signal_id}/expire")
def expire_signal(signal_id: int):
    db = get_db()
    db.execute("UPDATE signals SET status='expired' WHERE id=?", (signal_id,))
    db.commit()
    db.close()
    return {"ok": True}


# ── 权重优化 API ──

@router.get("/weights")
def get_weights():
    """获取当前因子权重"""
    return {k: round(v, 3) for k, v in WEIGHTS.items()}


@router.put("/weights")
def update_weights(weights: dict):
    """手动设置因子权重（需均等归一化）"""
    total = sum(weights.values())
    if total <= 0:
        return {"ok": False, "error": "权重和必须>0"}
    for k, v in weights.items():
        if k in WEIGHTS:
            WEIGHTS[k] = round(v / total, 4)
    return {"ok": True, "weights": {k: round(v, 3) for k, v in WEIGHTS.items()}}


@router.post("/optimize")
def optimize_weights(n_iter: int = 30, max_stocks: int = 15):
    """网格搜索最优权重（基于历史信号-收益相关性）"""
    from weight_optimizer import optimize
    return optimize(n_iter=n_iter, max_stocks=max_stocks)

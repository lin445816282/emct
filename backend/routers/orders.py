"""订单记录 API — 创建 + CDP执行 + 查询"""
from fastapi import APIRouter, HTTPException
from database import get_db
from cdp_trader import execute_order, get_session
from risk_control import check_order_allowed, get_position_risk

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("")
def list_orders(limit: int = 20):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM orders ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    db.close()
    return {"rows": [dict(r) for r in rows]}


@router.post("/create")
def create_order(signal_id: int = 0, code: str = "", name: str = "",
                 direction: str = "buy", price: float = 0, volume: int = 100):
    """创建订单（风控审核）"""
    # 风控检查
    risk = check_order_allowed(code, direction, price, volume)
    if not risk["allowed"]:
        return {"ok": False, "error": risk["reason"]}

    amount = round(price * volume, 2)
    db = get_db()
    cur = db.execute(
        """INSERT INTO orders (signal_id, code, name, direction, price, volume, amount, order_status)
           VALUES (?,?,?,?,?,?,?,'created')""",
        (signal_id, code, name, direction, price, volume, amount)
    )
    db.commit()
    order_id = cur.lastrowid
    db.close()
    return {"ok": True, "order_id": order_id}


@router.post("/{order_id}/execute")
async def exec_order(order_id: int):
    """CDP执行指定订单"""
    db = get_db()
    order = db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if not order:
        db.close()
        raise HTTPException(404, "订单不存在")

    if order["order_status"] != "created":
        db.close()
        return {"ok": False, "error": f"订单状态为 {order['order_status']}，无法执行"}

    # 更新状态为执行中
    db.execute("UPDATE orders SET order_status='executing', updated_at=datetime('now','localtime') WHERE id=?", (order_id,))
    db.commit()
    db.close()

    # 执行
    result = await execute_order(
        code=order["code"],
        name=order["name"],
        direction=order["direction"],
        price=order["price"],
        volume=order["volume"],
    )

    # 更新结果
    db = get_db()
    if result["ok"]:
        db.execute(
            """UPDATE orders SET order_status='submitted', screenshot_path=?,
               updated_at=datetime('now','localtime') WHERE id=?""",
            (result.get("screenshot", ""), order_id)
        )
    else:
        db.execute(
            """UPDATE orders SET order_status='failed', error_msg=?,
               updated_at=datetime('now','localtime') WHERE id=?""",
            (result.get("error", "未知错误"), order_id)
        )
    db.commit()
    db.close()
    return result


@router.post("/{order_id}/status")
def update_status(order_id: int, status: str, order_ref: str = "", error_msg: str = ""):
    """手动更新订单状态"""
    db = get_db()
    db.execute(
        """UPDATE orders SET order_status=?, order_ref=?, error_msg=?,
           updated_at=datetime('now','localtime') WHERE id=?""",
        (status, order_ref, error_msg, order_id)
    )
    db.commit()
    db.close()
    return {"ok": True}


@router.get("/cdp/status")
async def cdp_status():
    """检查 CDP 连接状态"""
    try:
        session = await get_session()
        return {"connected": session.connected, "target": session.target_id}
    except Exception as e:
        return {"connected": False, "error": str(e)}


@router.post("/quick-buy")
async def quick_buy(code: str, name: str, price: float, volume: int = 100, signal_id: int = 0):
    """快捷买入：创建订单 + 立即执行"""
    # 先创建
    r = create_order(signal_id=signal_id, code=code, name=name,
                     direction="buy", price=price, volume=volume)
    if not r["ok"]:
        return r
    # 再执行
    return await exec_order(r["order_id"])


@router.get("/risk/summary")
def risk_summary():
    """风控总览"""
    return get_position_risk()

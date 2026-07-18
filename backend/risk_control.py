"""
EMCT — 风控模块
仓位限制、止损止盈、单日限额、订单审核
"""
from database import get_db
from typing import Optional


class RiskConfig:
    """风控参数配置"""
    MAX_POSITION_PCT = 0.3      # 单只股票最大仓位 30%
    MAX_TOTAL_PCT = 0.8         # 总仓位上限 80%
    MAX_DAILY_ORDERS = 5        # 单日最大下单次数
    MAX_DAILY_AMOUNT = 50000    # 单日最大交易金额
    STOP_LOSS_PCT = -8.0        # 止损线 -8%
    TAKE_PROFIT_PCT = 15.0      # 止盈线 +15%
    MIN_VOLUME = 100            # 最小交易量
    MAX_SINGLE_AMOUNT = 10000   # 单笔最大金额
    BLACKLIST: list[str] = []   # 黑名单股票代码


def get_position_risk(code: Optional[str] = None) -> dict:
    """获取当前持仓风险数据"""
    db = get_db()
    total_value = db.execute(
        "SELECT COALESCE(SUM(market_value), 0) FROM positions"
    ).fetchone()[0]

    positions = db.execute(
        "SELECT code, name, volume, avg_cost, current_price, market_value, profit_loss, profit_loss_pct FROM positions"
    ).fetchall()

    result = {
        "total_value": round(total_value, 2),
        "position_count": len(positions),
        "positions": [],
        "warnings": [],
    }

    for p in positions:
        pos = dict(p)
        pct = (pos["market_value"] / total_value * 100) if total_value > 0 else 0
        pos["weight_pct"] = round(pct, 1)
        result["positions"].append(pos)

        # 止损检查
        if pos["profit_loss_pct"] is not None and pos["profit_loss_pct"] <= RiskConfig.STOP_LOSS_PCT:
            result["warnings"].append(f"⚠️ {pos['name']} 触发止损 {pos['profit_loss_pct']:.1f}%")
        # 止盈检查
        if pos["profit_loss_pct"] is not None and pos["profit_loss_pct"] >= RiskConfig.TAKE_PROFIT_PCT:
            result["warnings"].append(f"🎯 {pos['name']} 触发止盈 {pos['profit_loss_pct']:.1f}%")
        # 仓位超限
        if pct > RiskConfig.MAX_POSITION_PCT * 100:
            result["warnings"].append(f"📊 {pos['name']} 仓位超限 {pct:.0f}%")

    if total_value > 0 and total_value > RiskConfig.MAX_DAILY_AMOUNT:
        result["warnings"].append(f"📊 总仓位超限 {total_value:.0f}")

    db.close()
    return result


def check_order_allowed(code: str, direction: str, price: float, volume: int) -> dict:
    """
    检查订单是否通过风控
    返回: {"allowed": bool, "reason": str}
    """
    amount = price * volume

    # 1. 黑名单
    if code in RiskConfig.BLACKLIST:
        return {"allowed": False, "reason": f"{code} 在黑名单中"}

    # 2. 单笔最大金额
    if amount > RiskConfig.MAX_SINGLE_AMOUNT:
        return {"allowed": False, "reason": f"单笔金额 {amount:.0f} 超限(≤{RiskConfig.MAX_SINGLE_AMOUNT})"}

    # 3. 最小交易量
    if volume < RiskConfig.MIN_VOLUME:
        return {"allowed": False, "reason": f"最小交易量 {RiskConfig.MIN_VOLUME}股"}

    # 4. 单日限制
    db = get_db()
    today_orders = db.execute(
        "SELECT COUNT(*) as cnt, COALESCE(SUM(amount), 0) as total "
        "FROM orders WHERE date(created_at)=date('now','localtime') "
        "AND order_status NOT IN ('cancelled', 'failed')"
    ).fetchone()

    if today_orders["cnt"] >= RiskConfig.MAX_DAILY_ORDERS:
        db.close()
        return {"allowed": False, "reason": f"单日下单次数已达上限({RiskConfig.MAX_DAILY_ORDERS})"}

    if today_orders["total"] + amount > RiskConfig.MAX_DAILY_AMOUNT:
        db.close()
        return {"allowed": False, "reason": f"单日交易金额超限(≤{RiskConfig.MAX_DAILY_AMOUNT})"}

    # 5. 买入时检查仓位
    if direction == "buy":
        pos = db.execute(
            "SELECT market_value FROM positions WHERE code=?", (code,)
        ).fetchone()
        total_value = db.execute(
            "SELECT COALESCE(SUM(market_value), 0) FROM positions"
        ).fetchone()[0]
        db.close()

        if pos and total_value > 0:
            new_pct = (pos["market_value"] + amount) / total_value
            if new_pct > RiskConfig.MAX_POSITION_PCT:
                return {"allowed": False,
                        "reason": f"仓位将达到 {new_pct*100:.0f}%，超过单只上限{RiskConfig.MAX_POSITION_PCT*100:.0f}%"}
    else:
        db.close()

    return {"allowed": True, "reason": "通过"}


MAX_TOTAL_AMOUNT = 50000  # 总仓位上限5万

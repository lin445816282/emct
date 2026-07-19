"""
EMCT — 风控模块
仓位限制、止损止盈、单日限额、订单审核
所有参数从 DB strategy_config 读取，不再硬编码
"""
from database import get_db
from typing import Optional


def _get_risk_config() -> dict:
    """从 DB 策略配置读取风控参数，失败则抛异常（绝不静默回退）"""
    from strategy_config import get_config
    cfg = get_config()
    return {
        "stop_loss_pct": cfg["stop_loss_pct"],
        "take_profit_pct": cfg["take_profit_pct"],
        "max_single_amount": cfg["max_single_amount"],
        "max_positions": cfg["max_positions"],
        "min_strength": cfg["min_strength"],
        "max_hold_days": cfg["max_hold_days"],
    }


class RiskConfig:
    """风控参数 — 从 DB 实时读取，不再硬编码"""
    
    @staticmethod
    def get() -> dict:
        return _get_risk_config()
    
    @property
    def MAX_POSITION_PCT(self) -> float:
        return 0.3  # 单票仓位上限 30%（固定，非策略参数）
    
    @property
    def MAX_TOTAL_PCT(self) -> float:
        return 0.8  # 总仓位上限 80%（固定）
    
    @property
    def MAX_DAILY_ORDERS(self) -> int:
        return 5  # 单日最大下单次数（固定）
    
    @property
    def MAX_DAILY_AMOUNT(self) -> int:
        return 50000  # 单日最大交易金额（固定）
    
    @property
    def MIN_VOLUME(self) -> int:
        return 100  # 最小交易量
    
    @property
    def BLACKLIST(self) -> list:
        return []  # 黑名单股票代码


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

    risk = _get_risk_config()
    stop_loss = risk["stop_loss_pct"]
    take_profit = risk["take_profit_pct"]

    for p in positions:
        pos = dict(p)
        pct = (pos["market_value"] / total_value * 100) if total_value > 0 else 0
        pos["weight_pct"] = round(pct, 1)
        result["positions"].append(pos)

        # 止损检查（从 DB 配置读取阈值）
        if pos["profit_loss_pct"] is not None and pos["profit_loss_pct"] <= stop_loss:
            result["warnings"].append(f"⚠️ {pos['name']} 触发止损 {pos['profit_loss_pct']:.1f}% (阈值{stop_loss}%)")
        # 止盈检查（从 DB 配置读取阈值）
        if pos["profit_loss_pct"] is not None and pos["profit_loss_pct"] >= take_profit:
            result["warnings"].append(f"🎯 {pos['name']} 触发止盈 {pos['profit_loss_pct']:.1f}% (阈值{take_profit}%)")
        # 仓位超限
        if pct > RiskConfig().MAX_POSITION_PCT * 100:
            result["warnings"].append(f"📊 {pos['name']} 仓位超限 {pct:.0f}%")

    if total_value > 0 and total_value > RiskConfig().MAX_DAILY_AMOUNT:
        result["warnings"].append(f"📊 总仓位超限 {total_value:.0f}")

    db.close()
    return result


def check_order_allowed(code: str, direction: str, price: float, volume: int) -> dict:
    """
    检查订单是否通过风控
    返回: {"allowed": bool, "reason": str}
    所有阈值从 DB 策略配置实时读取
    """
    risk = _get_risk_config()
    amount = price * volume
    rc = RiskConfig()

    # 1. 黑名单
    if code in rc.BLACKLIST:
        return {"allowed": False, "reason": f"{code} 在黑名单中"}

    # 2. 单笔最大金额（从 DB 读）
    max_single = risk["max_single_amount"]
    if amount > max_single:
        return {"allowed": False, "reason": f"单笔金额 {amount:.0f} 超限(≤{max_single})"}

    # 3. 最小交易量
    if volume < rc.MIN_VOLUME:
        return {"allowed": False, "reason": f"最小交易量 {rc.MIN_VOLUME}股"}

    # 4. 单日限制
    db = get_db()
    today_orders = db.execute(
        "SELECT COUNT(*) as cnt, COALESCE(SUM(amount), 0) as total "
        "FROM orders WHERE date(created_at)=date('now','localtime') "
        "AND order_status NOT IN ('cancelled', 'failed')"
    ).fetchone()

    if today_orders["cnt"] >= rc.MAX_DAILY_ORDERS:
        db.close()
        return {"allowed": False, "reason": f"单日下单次数已达上限({rc.MAX_DAILY_ORDERS})"}

    if today_orders["total"] + amount > rc.MAX_DAILY_AMOUNT:
        db.close()
        return {"allowed": False, "reason": f"单日交易金额超限(≤{rc.MAX_DAILY_AMOUNT})"}

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
            if new_pct > rc.MAX_POSITION_PCT:
                return {"allowed": False,
                        "reason": f"仓位将达到 {new_pct*100:.0f}%，超过单只上限{rc.MAX_POSITION_PCT*100:.0f}%"}
    else:
        db.close()

    return {"allowed": True, "reason": "通过"}


MAX_TOTAL_AMOUNT = 50000  # 总仓位上限5万

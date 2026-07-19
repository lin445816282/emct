"""模拟交易 API"""
from fastapi import APIRouter, HTTPException
from database import get_db
from sim_trader import (
    get_account, reset_account, deposit,
    execute_buy, execute_sell,
    get_sim_positions, get_sim_orders, refresh_prices,
    auto_stop_check, get_equity_curve, auto_sell_t1,
    auto_trade_from_signals, auto_trade_open
)
from backtest_engine import run_backtest, run_rolling_backtest
from benchmark import sync_hs300, get_benchmark

router = APIRouter(prefix="/sim", tags=["sim"])


@router.get("/account")
def account():
    return get_account()


@router.post("/account/reset")
def reset(initial_cash: float = 50000):
    return reset_account(initial_cash)


@router.post("/account/deposit")
def do_deposit(amount: float):
    return deposit(amount)


@router.get("/positions")
def positions():
    return {"rows": get_sim_positions()}


@router.get("/orders")
def orders(limit: int = 30):
    return {"rows": get_sim_orders(limit)}


@router.post("/order/create")
def create_sim_order(code: str, name: str, direction: str = "buy",
                     price: float = 0, volume: int = 100, signal_id: int = 0):
    """创建模拟订单"""
    amount = round(price * volume, 2)
    db = get_db()
    cur = db.execute(
        """INSERT INTO orders (signal_id, code, name, direction, price, volume, amount,
           order_status, sim_mode) VALUES (?,?,?,?,?,?,?,'created',1)""",
        (signal_id, code, name, direction, price, volume, amount)
    )
    db.commit()
    order_id = cur.lastrowid
    db.close()
    return {"ok": True, "order_id": order_id}


@router.post("/order/{order_id}/execute")
def exec_sim_order(order_id: int):
    """执行模拟订单"""
    db = get_db()
    order = db.execute("SELECT * FROM orders WHERE id=? AND sim_mode=1", (order_id,)).fetchone()
    db.close()

    if not order:
        raise HTTPException(404, "订单不存在或非模拟单")

    if order["direction"] == "buy":
        return execute_buy(order_id)
    else:
        return execute_sell(order_id)


@router.post("/quick-trade")
def quick_trade(code: str, name: str, direction: str = "buy",
                price: float = 0, volume: int = 100, signal_id: int = 0):
    """快速交易：创建+立即执行"""
    r = create_sim_order(code=code, name=name, direction=direction,
                         price=price, volume=volume, signal_id=signal_id)
    if not r["ok"]:
        return r
    return exec_sim_order(r["order_id"])

@router.post("/refresh-prices")
def do_refresh_prices():
    return refresh_prices()

@router.post("/auto-check")
def do_auto_check():
    """自动止损止盈扫描"""
    return auto_stop_check()

@router.post("/settle-t1")
def do_settle_t1():
    """T+1结算：卖出隔夜持仓"""
    return auto_sell_t1()

@router.post("/auto-trade")
def do_auto_trade():
    """自动跟单：基于今日 pending 信号 → 标记 queued（次日开盘执行）"""
    return auto_trade_from_signals()

@router.post("/auto-trade-open")
def do_auto_trade_open():
    """次日开盘执行 queued 信号 → 用开盘价买入"""
    return auto_trade_open()

@router.get("/market-regime")
def market_regime():
    """查看当前市场趋势（v2：熊市允许轻仓10%）"""
    from benchmark import market_regime_ok
    ok, msg, bear_factor = market_regime_ok()
    return {"ok": ok, "msg": msg, "can_trade": ok, "bear_factor": bear_factor}

@router.get("/equity-curve")
def equity_curve():
    """净值曲线数据"""
    return {"rows": get_equity_curve()}

@router.get("/backtest")
def backtest(
    date_from: str = None,
    date_to: str = None,
    slippage: float = 0.001,
    commission: float = 0.0003,
):
    """运行回测。风控参数从 DB strategy_config 自动读取"""
    return run_backtest(
        date_from=date_from,
        date_to=date_to,
        slippage_pct=slippage,
        commission_pct=commission,
    )

@router.get("/backtest/rolling")
def rolling_backtest(
    window_days: int = 30,
    step_days: int = 7,
):
    """滚动窗口回测。风控参数从 DB 自动读取"""
    return run_rolling_backtest(
        window_days=window_days,
        step_days=step_days,
    )

@router.post("/sync-benchmark")
def do_sync_benchmark():
    """同步沪深300指数数据"""
    return sync_hs300()

@router.get("/benchmark")
def benchmark_data():
    """获取沪深300指数数据"""
    return get_benchmark()

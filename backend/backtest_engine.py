"""
回测引擎 — 基于历史信号模拟交易，计算绩效指标
"""
import sqlite3
from datetime import datetime

from database import get_db


def run_backtest(
    initial_cash: float = 50000,
    max_position_pct: float = 0.3,
    stop_loss_pct: float = -0.08,
    take_profit_pct: float = 0.15,
    max_hold_days: int = 10,
) -> dict:
    """
    回测：遍历信号，模拟买入→持仓→卖出
    返回：绩效指标 + 净值曲线 + 交易记录
    """
    db = get_db()
    db.row_factory = sqlite3.Row
    
    # 获取所有信号（按日期排序）
    signals = db.execute("""
        SELECT * FROM signals WHERE signal_type='buy'
        ORDER BY date ASC
    """).fetchall()
    
    if not signals:
        db.close()
        return {"ok": False, "error": "无信号数据"}
    
    # 加载所有日线数据以供快速查询
    all_kline = {}
    for row in db.execute("SELECT code, date, close FROM daily_kline ORDER BY date ASC"):
        key = (row["code"], row["date"])
        all_kline[key] = row["close"]
    
    db.close()
    
    # --- 回测核心 ---
    cash = initial_cash
    positions = {}  # code -> {shares, cost, buy_date}
    trades = []     # 每笔交易记录
    equity_daily = {}  # date -> total_value
    
    skipped_no_kline = 0
    skipped_no_cash = 0
    
    all_dates = sorted(set(d for _, d in all_kline.keys()))
    
    for sig in signals:
        code = sig["code"]
        sig_date = sig["date"]
        
        # 找下一个交易日
        next_dates = [d for d in all_dates if d > sig_date]
        if not next_dates:
            skipped_no_kline += 1
            continue
        buy_date = next_dates[0]
        
        buy_price = all_kline.get((code, buy_date))
        if not buy_price or buy_price <= 0:
            skipped_no_kline += 1
            continue
        
        # 计算买入量
        max_spend = cash * max_position_pct
        max_shares = int(max_spend / buy_price / 100) * 100  # 整手
        if max_shares < 100:
            continue
        
        buy_amount = buy_price * max_shares
        if buy_amount > cash:
            continue
        
        # 执行买入
        cash -= buy_amount
        cash = round(cash, 2)
        positions[code] = {
            "shares": max_shares,
            "cost": buy_price,
            "buy_date": buy_date,
            "buy_price": buy_price,
            "amount": buy_amount,
        }
        
        trades.append({
            "date": buy_date,
            "code": code,
            "name": sig["name"],
            "type": "buy",
            "price": buy_price,
            "shares": max_shares,
            "amount": buy_amount,
            "reason": sig["reason"] or "",
        })
        
        # 寻找卖出时机：遍历后续日期
        future_dates = [d for d in all_dates if d > buy_date]
        sold = False
        
        for check_date in future_dates:
            price = all_kline.get((code, check_date))
            if not price:
                continue
            
            pnl_pct = (price - buy_price) / buy_price
            hold_days = (datetime.strptime(check_date, "%Y-%m-%d") - 
                         datetime.strptime(buy_date, "%Y-%m-%d")).days
            
            exit_reason = None
            
            # 止损
            if pnl_pct <= stop_loss_pct:
                exit_reason = "止损"
            # 止盈
            elif pnl_pct >= take_profit_pct:
                exit_reason = "止盈"
            # 超时
            elif hold_days >= max_hold_days:
                exit_reason = "到期"
            
            if exit_reason:
                sell_amount = price * max_shares
                pnl = sell_amount - buy_amount
                cash += sell_amount
                cash = round(cash, 2)
                
                trades.append({
                    "date": check_date,
                    "code": code,
                    "name": sig["name"],
                    "type": "sell",
                    "price": price,
                    "shares": max_shares,
                    "amount": sell_amount,
                    "pnl": round(pnl, 2),
                    "pnl_pct": round(pnl_pct * 100, 2),
                    "hold_days": hold_days,
                    "reason": exit_reason,
                })
                
                sold = True
                del positions[code]
                break
        
        # 如果到最后都没卖出，强制平仓
        if not sold and positions.get(code):
            pos = positions[code]
            # 找最后一个有价格的日期
            last_dates = [d for d in all_dates if d > pos["buy_date"]]
            if last_dates:
                last_date = last_dates[-1]
                last_price = all_kline.get((code, last_date))
                if last_price:
                    pnl_pct = (last_price - pos["cost"]) / pos["cost"]
                    sell_amount = last_price * pos["shares"]
                    pnl = sell_amount - pos["amount"]
                    cash += sell_amount
                    cash = round(cash, 2)
                    
                    trades.append({
                        "date": last_date,
                        "code": code,
                        "name": sig["name"],
                        "type": "sell",
                        "price": last_price,
                        "shares": pos["shares"],
                        "amount": sell_amount,
                        "pnl": round(pnl, 2),
                        "pnl_pct": round(pnl_pct * 100, 2),
                        "hold_days": (datetime.strptime(last_date, "%Y-%m-%d") - 
                                     datetime.strptime(pos["buy_date"], "%Y-%m-%d")).days,
                        "reason": "强制平仓",
                    })
                    del positions[code]
    
    # 处理剩余持仓（按最后价格估值）
    remaining_value = 0
    for code, pos in positions.items():
        last_dates = [d for d in all_dates if d > pos["buy_date"]]
        if last_dates:
            last_price = all_kline.get((code, last_dates[-1]))
            if last_price:
                remaining_value += last_price * pos["shares"]
    
    final_value = cash + remaining_value
    
    # --- 计算每日净值 ---
    equity_curve = []
    # 从第一个信号日到最后交易日
    all_dates_sorted = sorted(all_dates)
    if trades:
        first_date = min(t["date"] for t in trades)
        last_date = max(t["date"] for t in trades)
        
        # 按天重放交易
        cash_timeline = initial_cash
        pos_timeline = {}  # code -> {shares, cost}
        
        for date in all_dates_sorted:
            if date < first_date:
                equity_curve.append({"date": date, "total": initial_cash})
                continue
            if date > last_date:
                # 最后一天之后不变
                continue
            
            # 执行当天的交易
            for t in trades:
                if t["date"] == date:
                    if t["type"] == "buy":
                        cash_timeline -= t["amount"]
                        pos_timeline[t["code"]] = {
                            "shares": t["shares"],
                            "cost": t["price"],
                        }
                    else:
                        cash_timeline += t["amount"]
                        if t["code"] in pos_timeline:
                            del pos_timeline[t["code"]]
            
            # 计算当天持仓市值
            mv = 0
            for code, pos in pos_timeline.items():
                price = all_kline.get((code, date))
                if price:
                    mv += price * pos["shares"]
                else:
                    mv += pos["cost"] * pos["shares"]
            
            total = round(cash_timeline + mv, 2)
            equity_curve.append({"date": date, "total": total})
    
    # 加最后一天
    if equity_curve and trades:
        last_eq_date = equity_curve[-1]["date"]
        last_trade_date = max(t["date"] for t in trades)
        if last_trade_date > last_eq_date:
            # 重算最后一天
            final_cash_timeline = initial_cash
            final_pos_timeline = {}
            for t in trades:
                if t["type"] == "buy":
                    final_cash_timeline -= t["amount"]
                    final_pos_timeline[t["code"]] = {"shares": t["shares"], "cost": t["price"]}
                else:
                    final_cash_timeline += t["amount"]
                    if t["code"] in final_pos_timeline:
                        del final_pos_timeline[t["code"]]
            equity_curve.append({"date": last_trade_date, "total": round(final_cash_timeline, 2)})
    
    # --- 绩效指标 ---
    total_pnl = final_value - initial_cash
    total_return = round(total_pnl / initial_cash * 100, 2)
    
    sell_trades = [t for t in trades if t.get("type") == "sell"]
    win_trades = [t for t in sell_trades if t.get("pnl", 0) > 0]
    loss_trades = [t for t in sell_trades if t.get("pnl", 0) < 0]
    
    win_rate = round(len(win_trades) / len(sell_trades) * 100, 2) if sell_trades else 0
    avg_win = round(sum(t["pnl"] for t in win_trades) / len(win_trades), 2) if win_trades else 0
    avg_loss = round(abs(sum(t["pnl"] for t in loss_trades) / len(loss_trades)), 2) if loss_trades else 0
    profit_factor = round(avg_win / avg_loss, 2) if avg_loss > 0 else 0
    avg_hold = round(sum(t.get("hold_days", 0) for t in sell_trades) / len(sell_trades), 1) if sell_trades else 0
    
    # 最大回撤
    max_dd = 0
    peak = initial_cash
    for pt in equity_curve:
        if pt["total"] > peak:
            peak = pt["total"]
        dd = (peak - pt["total"]) / peak * 100
        if dd > max_dd:
            max_dd = round(dd, 2)
    
    # CAGR（年化）
    if equity_curve and len(equity_curve) >= 2:
        first_day = equity_curve[0]["date"]
        last_day = equity_curve[-1]["date"]
        days = (datetime.strptime(last_day, "%Y-%m-%d") - datetime.strptime(first_day, "%Y-%m-%d")).days
        years = max(days / 365, 0.02)
        cagr = round(((final_value / initial_cash) ** (1 / years) - 1) * 100, 2)
    else:
        cagr = 0
    
    return {
        "ok": True,
        "summary": {
            "initial_cash": initial_cash,
            "final_value": round(final_value, 2),
            "total_pnl": round(total_pnl, 2),
            "total_return": total_return,
            "cagr": cagr,
            "max_drawdown": max_dd,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "total_trades": len(sell_trades),
            "win_trades": len(win_trades),
            "loss_trades": len(loss_trades),
            "avg_hold_days": avg_hold,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
        },
        "trades": trades,
        "equity_curve": equity_curve,
        "diagnostic": {
            "signals_total": len(signals),
            "skipped_no_kline": skipped_no_kline,
            "kline_range": f"{all_dates[0]}~{all_dates[-1]}" if all_dates else "无数据",
            "signal_range": f"{signals[0]['date']}~{signals[-1]['date']}" if signals else "无",
        },
    }

"""
回测引擎 v2 — 基于历史信号模拟交易，计算绩效指标
新增：日期范围/过滤测试信号/滑点手续费/滚动窗口
"""
import sqlite3
from datetime import datetime
from typing import Optional

from database import get_db


def run_backtest(
    initial_cash: float = 50000,
    max_position_pct: float = 0.3,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    slippage_pct: float = 0.001,  # 滑点 0.1%
    commission_pct: float = 0.0003,  # 手续费 0.03%
) -> dict:
    """
    回测：遍历信号，模拟买入→持仓→卖出
    
    风控参数（止损/止盈/满仓天数/最小强度）从 DB strategy_config 实时读取
    """
    from strategy_config import get_config as _get_strategy
    cfg = _get_strategy()
    stop_loss_pct = cfg["stop_loss_pct"] / 100  # DB存整数，转小数
    take_profit_pct = cfg["take_profit_pct"] / 100
    max_hold_days = cfg["max_hold_days"]
    min_strength = cfg["min_strength"]

    db = get_db()

    # 默认日期范围：最近 60 天
    if not date_from:
        date_from = db.execute(
            "SELECT date(MAX(date), '-60 days') FROM signals"
        ).fetchone()[0] or "2026-01-01"
    if not date_to:
        date_to = db.execute("SELECT MAX(date) FROM signals").fetchone()[0] or "2099-12-31"

    # 获取信号：过滤测试信号 + 日期范围 + 排除今天（无次日K线）
    today = datetime.now().strftime("%Y-%m-%d")
    signals = db.execute("""
        SELECT * FROM signals 
        WHERE signal_type IN ('buy', 'strong_buy')
          AND date >= ? AND date < ?
          AND strength >= ?
          AND (reason IS NULL OR reason NOT LIKE '%[backtest]%')
          AND reason NOT LIKE '%测试信号%'
        ORDER BY date ASC
    """, (date_from, today, min_strength)).fetchall()

    if not signals:
        db.close()
        return {"ok": False, "error": f"无有效买入信号（{date_from}~{today}，强度≥{min_strength}）"}

    # 加载 K 线
    all_kline = {}
    for row in db.execute(
        "SELECT code, date, close FROM daily_kline ORDER BY date ASC"
    ):
        all_kline[(row["code"], row["date"])] = row["close"]
    db.close()

    all_dates = sorted(set(d for _, d in all_kline.keys()))
    if not all_dates:
        return {"ok": False, "error": "无K线数据"}

    # 交易成本因子：买入时扣费，卖出时滑点
    buy_cost_factor = 1 + commission_pct
    sell_price_factor = 1 - slippage_pct - commission_pct

    cash = initial_cash
    positions = {}
    trades = []
    skipped_no_kline = 0
    skipped_no_cash = 0

    for sig in signals:
        code = sig["code"]
        sig_date = sig["date"]

        # 买入去重：已有该股持仓则跳过
        if code in positions:
            continue

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

        # 含手续费的买入价
        effective_buy_price = buy_price * buy_cost_factor

        # 计算买入量（整手）
        max_spend = cash * max_position_pct
        max_shares = int(max_spend / effective_buy_price / 100) * 100
        if max_shares < 100:
            skipped_no_cash += 1
            continue

        buy_amount = round(effective_buy_price * max_shares, 2)
        if buy_amount > cash:
            skipped_no_cash += 1
            continue

        # 执行买入
        cash -= buy_amount
        cash = round(cash, 2)
        positions[code] = {
            "shares": max_shares,
            "cost": effective_buy_price,
            "buy_date": buy_date,
            "buy_price": effective_buy_price,
            "amount": buy_amount,
        }

        trades.append({
            "date": buy_date,
            "code": code,
            "name": sig["name"],
            "type": "buy",
            "price": round(effective_buy_price, 2),
            "shares": max_shares,
            "amount": buy_amount,
            "reason": (sig["reason"] or "")[:80],
        })

        # 寻找卖出时机
        future_dates = [d for d in all_dates if d > buy_date]
        sold = False

        for check_date in future_dates:
            raw_price = all_kline.get((code, check_date))
            if not raw_price:
                continue

            # 卖出滑点价
            sell_price = raw_price * sell_price_factor
            pnl_pct = (sell_price - effective_buy_price) / effective_buy_price
            hold_days = (datetime.strptime(check_date, "%Y-%m-%d") -
                         datetime.strptime(buy_date, "%Y-%m-%d")).days

            exit_reason = None
            if pnl_pct <= stop_loss_pct:
                exit_reason = "止损"
            elif pnl_pct >= take_profit_pct:
                exit_reason = "止盈"
            elif hold_days >= max_hold_days:
                exit_reason = "到期"

            if exit_reason:
                sell_amount = round(sell_price * max_shares, 2)
                pnl = round(sell_amount - buy_amount, 2)
                cash += sell_amount
                cash = round(cash, 2)

                trades.append({
                    "date": check_date,
                    "code": code,
                    "name": sig["name"],
                    "type": "sell",
                    "price": round(sell_price, 2),
                    "shares": max_shares,
                    "amount": sell_amount,
                    "pnl": pnl,
                    "pnl_pct": round(pnl_pct * 100, 2),
                    "hold_days": hold_days,
                    "reason": exit_reason,
                })
                sold = True
                del positions[code]
                break

        # 强制平仓
        if not sold and positions.get(code):
            pos = positions[code]
            last_dates = [d for d in all_dates if d > pos["buy_date"]]
            if last_dates:
                last_date = last_dates[-1]
                raw_price = all_kline.get((code, last_date))
                if raw_price:
                    last_price = raw_price * sell_price_factor
                    pnl_pct = (last_price - pos["cost"]) / pos["cost"]
                    sell_amount = round(last_price * pos["shares"], 2)
                    pnl = round(sell_amount - pos["amount"], 2)
                    cash += sell_amount
                    cash = round(cash, 2)
                    trades.append({
                        "date": last_date,
                        "code": code,
                        "name": sig["name"],
                        "type": "sell",
                        "price": round(last_price, 2),
                        "shares": pos["shares"],
                        "amount": sell_amount,
                        "pnl": pnl,
                        "pnl_pct": round(pnl_pct * 100, 2),
                        "hold_days": (datetime.strptime(last_date, "%Y-%m-%d") -
                                     datetime.strptime(pos["buy_date"], "%Y-%m-%d")).days,
                        "reason": "强制平仓",
                    })
                    del positions[code]

    # 剩余持仓估值
    remaining_value = 0
    for code, pos in positions.items():
        last_dates = [d for d in all_dates if d > pos["buy_date"]]
        if last_dates:
            last_price = all_kline.get((code, last_dates[-1]))
            if last_price:
                remaining_value += last_price * pos["shares"] * sell_price_factor

    final_value = cash + remaining_value

    # ── 每日净值曲线 ──
    equity_curve = []
    all_dates_sorted = sorted(all_dates)
    if trades:
        first_date = min(t["date"] for t in trades)
        last_date = max(t["date"] for t in trades)
        cash_timeline = initial_cash
        pos_timeline = {}

        for date in all_dates_sorted:
            if date < first_date:
                equity_curve.append({"date": date, "total": initial_cash})
                continue
            if date > last_date:
                continue

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

            mv = 0
            for code, pos in pos_timeline.items():
                price = all_kline.get((code, date))
                mv += (price or pos["cost"]) * pos["shares"]

            equity_curve.append({
                "date": date,
                "total": round(cash_timeline + mv, 2),
            })

    # ── 绩效指标 ──
    total_pnl = final_value - initial_cash
    total_return = round(total_pnl / initial_cash * 100, 2)

    sell_trades = [t for t in trades if t.get("type") == "sell"]
    win_trades = [t for t in sell_trades if t.get("pnl", 0) > 0]
    loss_trades = [t for t in sell_trades if t.get("pnl", 0) < 0]
    flat_trades = [t for t in sell_trades if t.get("pnl", 0) == 0]

    win_rate = round(len(win_trades) / len(sell_trades) * 100, 2) if sell_trades else 0
    avg_win = round(sum(t["pnl"] for t in win_trades) / len(win_trades), 2) if win_trades else 0
    avg_loss = round(abs(sum(t["pnl"] for t in loss_trades) / len(loss_trades)), 2) if loss_trades else 0
    profit_factor = round(avg_win / avg_loss, 2) if avg_loss > 0 else (999 if avg_win > 0 else 0)
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

    # CAGR
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
            "total_trades": len(trades),
            "completed_trades": len(sell_trades),
            "open_positions": len(positions),
            "win_trades": len(win_trades),
            "loss_trades": len(loss_trades),
            "flat_trades": len(flat_trades),
            "avg_hold_days": avg_hold,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
        },
        "trades": trades,
        "equity_curve": equity_curve,
        "diagnostic": {
            "signals_total": len(signals),
            "skipped_no_kline": skipped_no_kline,
            "skipped_no_cash": skipped_no_cash,
            "kline_range": f"{all_dates[0]}~{all_dates[-1]}" if all_dates else "无数据",
            "signal_range": f"{signals[0]['date']}~{signals[-1]['date']}" if signals else "无",
            "date_filter": f"{date_from}~{date_to}",
            "slippage": f"{slippage_pct*100:.1f}%",
            "commission": f"{commission_pct*100:.2f}%",
        },
    }


def run_rolling_backtest(
    window_days: int = 30,
    step_days: int = 7,
    initial_cash: float = 50000,
    **kwargs,
) -> dict:
    """滚动窗口回测：分多个窗口单独回测，汇总平均绩效"""
    db = get_db()
    db.row_factory = sqlite3.Row
    all_sig_dates = db.execute(
        "SELECT DISTINCT date FROM signals WHERE signal_type IN ('buy','strong_buy') ORDER BY date"
    ).fetchall()
    db.close()

    if len(all_sig_dates) < 2:
        return {"ok": False, "error": "信号数据不足"}

    first_date = all_sig_dates[0]["date"]
    last_date = all_sig_dates[-1]["date"]

    windows = []
    results = []

    current_start = first_date
    while current_start < last_date:
        current_end_dt = datetime.strptime(current_start, "%Y-%m-%d")
        from datetime import timedelta
        current_end = (current_end_dt + timedelta(days=window_days)).strftime("%Y-%m-%d")
        if current_end > last_date:
            current_end = last_date

        windows.append({"from": current_start, "to": current_end})

        result = run_backtest(
            initial_cash=initial_cash,
            date_from=current_start,
            date_to=current_end,
            **kwargs,
        )
        results.append(result)

        # 下一窗口
        next_dt = current_end_dt + timedelta(days=step_days)
        current_start = next_dt.strftime("%Y-%m-%d")

    # 汇总
    valid = [r for r in results if r.get("ok")]
    if not valid:
        return {"ok": False, "error": "所有窗口均无有效信号"}

    avg_return = sum(r["summary"]["total_return"] for r in valid) / len(valid)
    avg_win_rate = sum(r["summary"]["win_rate"] for r in valid) / len(valid)
    avg_max_dd = sum(r["summary"]["max_drawdown"] for r in valid) / len(valid)
    total_trades = sum(r["summary"]["total_trades"] for r in valid)

    return {
        "ok": True,
        "rolling": {
            "windows": len(windows),
            "valid_windows": len(valid),
            "avg_return": round(avg_return, 2),
            "avg_win_rate": round(avg_win_rate, 2),
            "avg_max_dd": round(avg_max_dd, 2),
            "total_trades": total_trades,
        },
        "windows": [
            {
                "from": w["from"],
                "to": w["to"],
                "summary": r.get("summary") if r.get("ok") else {"error": r.get("error")},
            }
            for w, r in zip(windows, results)
        ],
    }

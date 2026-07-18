"""
EMCT — 模拟交易引擎
虚拟资金、撮合成交、持仓管理，完全独立于 CDP 真实交易
"""
from database import get_db, init_db
from datetime import datetime


# ── 账户 ──

def get_account() -> dict:
    """获取模拟账户信息"""
    db = get_db()
    acct = db.execute("SELECT * FROM sim_account ORDER BY id DESC LIMIT 1").fetchone()
    if not acct:
        db.execute("INSERT INTO sim_account (initial_cash, cash) VALUES (50000, 50000)")
        db.commit()
        acct = db.execute("SELECT * FROM sim_account ORDER BY id DESC LIMIT 1").fetchone()

    # 计算持仓市值
    positions = db.execute(
        "SELECT * FROM positions WHERE sim_mode=1 AND volume > 0"
    ).fetchall()
    total_mv = sum(p["market_value"] or 0 for p in positions)
    total_pnl = sum(p["profit_loss"] or 0 for p in positions)

    db.execute(
        "UPDATE sim_account SET total_value=?, total_pnl=?, updated_at=datetime('now','localtime') WHERE id=?",
        (acct["cash"] + total_mv, total_pnl, acct["id"])
    )
    db.commit()

    result = dict(acct)
    result["market_value"] = round(total_mv, 2)
    result["total_pnl"] = round(total_pnl, 2)
    result["total_pnl_pct"] = round(total_pnl / acct["initial_cash"] * 100, 2) if acct["initial_cash"] else 0
    result["total_value"] = round(acct["cash"] + total_mv, 2)

    db.close()
    return result


def reset_account(initial_cash: float = 50000):
    """重置模拟账户"""
    db = get_db()
    # 删除旧记录
    db.execute("DELETE FROM orders WHERE sim_mode=1")
    db.execute("DELETE FROM positions WHERE sim_mode=1")
    db.execute("DELETE FROM trade_log WHERE sim_mode=1")
    db.execute("DELETE FROM sim_account")
    # 新建
    db.execute(
        "INSERT INTO sim_account (initial_cash, cash, total_value) VALUES (?,?,?)",
        (initial_cash, initial_cash, initial_cash)
    )
    db.commit()
    db.close()
    return {"ok": True, "initial_cash": initial_cash}


def deposit(amount: float):
    """入金"""
    db = get_db()
    acct = db.execute("SELECT * FROM sim_account ORDER BY id DESC LIMIT 1").fetchone()
    if acct:
        db.execute(
            "UPDATE sim_account SET cash=cash+?, initial_cash=initial_cash+? WHERE id=?",
            (amount, amount, acct["id"])
        )
    db.commit()
    db.close()
    return get_account()


# ── 交易时间 ──

def _is_trading_time() -> tuple[bool, str]:
    """检查是否在A股交易时间（9:30-11:30, 13:00-15:00）"""
    from datetime import datetime
    now = datetime.now()
    weekday = now.weekday()
    if weekday >= 5:
        return False, "周末休市"
    t = now.hour * 60 + now.minute
    if 9 * 60 + 30 <= t <= 11 * 60 + 30:
        return True, "早盘"
    if 13 * 60 <= t <= 15 * 60:
        return True, "午盘"
    return False, f"非交易时间（当前 {now.strftime('%H:%M')}，交易时段 9:30-11:30 13:00-15:00）"


def _get_real_price(code: str) -> float | None:
    """从日线获取最新收盘价作为真实成交价"""
    db = get_db()
    row = db.execute(
        "SELECT close FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 1",
        (code,)
    ).fetchone()
    db.close()
    return float(row["close"]) if row and row["close"] else None


def _check_sim_risk(db, code: str, direction: str, price: float, volume: int) -> tuple[bool, str]:
    """模拟风控检查（复用已有db连接）"""
    amount = price * volume

    # 1. 最小交易量（1手=100股）
    if volume < 100:
        return False, f"最小交易量 100 股"

    # 2. 单日次数限制
    today_cnt = db.execute(
        "SELECT COUNT(*) FROM orders WHERE sim_mode=1"
        " AND date(created_at)=date('now','localtime')"
        " AND order_status NOT IN ('cancelled','failed')"
    ).fetchone()[0]
    if today_cnt >= 5:
        return False, f"今日下单已达上限(5笔)"

    # 3. 单日金额限制
    today_amt = db.execute(
        "SELECT COALESCE(SUM(amount),0) FROM orders WHERE sim_mode=1"
        " AND date(created_at)=date('now','localtime')"
        " AND order_status NOT IN ('cancelled','failed')"
    ).fetchone()[0]
    if today_amt + amount > 50000:
        return False, f"今日交易金额将超限(≤5万)"

    # 4. 买入：单票仓位不超过30%（有持仓时才检查）
    if direction == "buy":
        pos = db.execute("SELECT market_value FROM positions WHERE code=? AND sim_mode=1", (code,)).fetchone()
        total_mv = db.execute("SELECT COALESCE(SUM(market_value),0) FROM positions WHERE sim_mode=1").fetchone()[0]
        if total_mv > 0:  # 已有持仓才检查集中度
            existing_mv = pos["market_value"] if pos else 0
            new_pct = (existing_mv + amount) / (total_mv + amount) * 100
            if new_pct > 30:
                return False, f"单票仓位将达 {new_pct:.0f}%（上限30%）"

    return True, "通过"


# ── 下单执行 ──

def execute_buy(order_id: int) -> dict:
    """模拟买入成交（交易时间内+真实日线价格）"""
    db = get_db()
    order = db.execute("SELECT * FROM orders WHERE id=? AND sim_mode=1", (order_id,)).fetchone()
    if not order:
        db.close()
        return {"ok": False, "error": "订单不存在或非模拟单"}

    if order["order_status"] != "created":
        db.close()
        return {"ok": False, "error": f"订单状态 {order['order_status']} 不可执行"}

    # ✅ 交易时间检查
    ok, reason = _is_trading_time()
    if not ok:
        db.close()
        return {"ok": False, "error": reason}

    code = order["code"]
    name = order["name"] or order["code"]
    # ✅ 用真实日线价格（复用db连接，避免死锁）
    price_row = db.execute(
        "SELECT close FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 1", (code,)
    ).fetchone()
    if not price_row or not price_row["close"]:
        db.close()
        return {"ok": False, "error": f"{code} 无日线数据"}
    price = float(price_row["close"])
    volume = order["volume"]
    amount = round(price * volume, 2)

    # ✅ 风控检查
    passed, risk_msg = _check_sim_risk(db, code, "buy", price, volume)
    if not passed:
        db.close()
        return {"ok": False, "error": risk_msg}

    # 资金检查
    acct = db.execute("SELECT * FROM sim_account ORDER BY id DESC LIMIT 1").fetchone()
    if not acct or acct["cash"] < amount:
        db.close()
        return {"ok": False, "error": f"资金不足（需要 ¥{amount:,.0f}，可用 ¥{acct['cash']:,.0f}）"}

    # 扣款
    db.execute("UPDATE sim_account SET cash=cash-? WHERE id=?", (amount, acct["id"]))

    # 更新订单
    db.execute(
        "UPDATE orders SET order_status='filled', amount=?, updated_at=datetime('now','localtime') WHERE id=?",
        (amount, order_id)
    )

    # 更新持仓
    existing = db.execute(
        "SELECT * FROM positions WHERE code=? AND sim_mode=1", (code,)
    ).fetchone()
    if existing:
        total_volume = existing["volume"] + volume
        new_cost = round(
            (existing["avg_cost"] * existing["volume"] + price * volume) / total_volume, 2
        )
        new_mv = round(price * total_volume, 2)
        pnl = round(total_volume * (price - new_cost), 2)
        pnl_pct = round((price - new_cost) / new_cost * 100, 2) if new_cost else 0
        db.execute(
            """UPDATE positions SET volume=?, avg_cost=?, current_price=?,
               market_value=?, profit_loss=?, profit_loss_pct=?,
               updated_at=datetime('now','localtime') WHERE id=?""",
            (total_volume, new_cost, price, new_mv, pnl, pnl_pct, existing["id"])
        )
    else:
        db.execute(
            """INSERT INTO positions (code, name, volume, avg_cost, current_price,
               market_value, profit_loss, profit_loss_pct, sim_mode, buy_date)
               VALUES (?,?,?,?,?,?,?,?,1,?)""",
            (code, name, volume, price, price, amount, 0, 0, datetime.now().strftime("%Y-%m-%d"))
        )    # 交易日志
    db.execute(
        """INSERT INTO trade_log (order_id, code, action, price, volume, sim_mode)
           VALUES (?,?, 'open', ?, ?, 1)""",
        (order_id, code, price, volume)
    )

    db.commit()
    db.close()
    return {"ok": True, "order_id": order_id, "filled_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}


def execute_sell(order_id: int) -> dict:
    """模拟卖出（平仓，交易时间内+真实行情价）"""
    db = get_db()
    order = db.execute("SELECT * FROM orders WHERE id=? AND sim_mode=1", (order_id,)).fetchone()
    if not order:
        db.close()
        return {"ok": False, "error": "订单不存在或非模拟单"}

    # ✅ 交易时间检查
    ok, reason = _is_trading_time()
    if not ok:
        db.close()
        return {"ok": False, "error": reason}

    code = order["code"]
    # ✅ 卖出用真实日线收盘价（复用db连接）
    price_row = db.execute(
        "SELECT close FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 1", (code,)
    ).fetchone()
    if not price_row or not price_row["close"]:
        db.close()
        return {"ok": False, "error": f"{code} 无日线数据"}
    sell_price = float(price_row["close"])
    sell_volume = order["volume"]

    # ✅ 风控检查
    passed, risk_msg = _check_sim_risk(db, code, "sell", sell_price, sell_volume)
    if not passed:
        db.close()
        return {"ok": False, "error": risk_msg}

    # 查找持仓
    pos = db.execute(
        "SELECT * FROM positions WHERE code=? AND sim_mode=1", (code,)
    ).fetchone()
    if not pos or pos["volume"] <= 0:
        db.close()
        return {"ok": False, "error": f"没有 {code} 的持仓"}

    if sell_volume > pos["volume"]:
        db.close()
        return {"ok": False, "error": f"持仓不足（持有 {pos['volume']}股，卖出 {sell_volume}股）"}

    sell_amount = round(sell_price * sell_volume, 2)
    cost_basis = pos["avg_cost"] * sell_volume
    pnl = round(sell_amount - cost_basis, 2)
    pnl_pct = round((sell_price - pos["avg_cost"]) / pos["avg_cost"] * 100, 2)

    # 更新资金
    db.execute(
        "UPDATE sim_account SET cash=cash+? WHERE id=(SELECT id FROM sim_account ORDER BY id DESC LIMIT 1)",
        (sell_amount,)
    )

    # 更新订单
    db.execute(
        "UPDATE orders SET order_status='filled', amount=?, updated_at=datetime('now','localtime') WHERE id=?",
        (sell_amount, order_id)
    )

    # 更新持仓
    remaining = pos["volume"] - sell_volume
    if remaining > 0:
        # 部分平仓：重新计算剩余持仓的浮动盈亏
        remaining_mv = round(sell_price * remaining, 2)
        new_pnl = round(remaining * (sell_price - pos["avg_cost"]), 2)
        new_pnl_pct = round((sell_price - pos["avg_cost"]) / pos["avg_cost"] * 100, 2) if pos["avg_cost"] else 0
        db.execute(
            """UPDATE positions SET volume=?, current_price=?, market_value=?,
               profit_loss=?, profit_loss_pct=?,
               updated_at=datetime('now','localtime')
               WHERE id=?""",
            (remaining, sell_price, remaining_mv, new_pnl, new_pnl_pct, pos["id"])
        )
    else:
        db.execute("DELETE FROM positions WHERE id=?", (pos["id"],))

    # 交易日志
    hold_days = 0
    open_log = db.execute(
        "SELECT created_at FROM trade_log WHERE code=? AND action='open' AND sim_mode=1 ORDER BY id DESC LIMIT 1",
        (code,)
    ).fetchone()
    if open_log:
        try:
            open_dt = datetime.strptime(open_log["created_at"], "%Y-%m-%d %H:%M:%S")
            hold_days = (datetime.now() - open_dt).days
        except:
            pass

    db.execute(
        """INSERT INTO trade_log (order_id, code, action, price, volume, pnl, pnl_pct, hold_days, sim_mode)
           VALUES (?,?, 'close', ?, ?, ?, ?, ?, 1)""",
        (order_id, code, sell_price, sell_volume, pnl, pnl_pct, hold_days)
    )

    db.commit()
    db.close()
    return {
        "ok": True, "order_id": order_id,
        "pnl": round(pnl, 2), "pnl_pct": round(pnl_pct, 2),
        "filled_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }


# ── 辅助 ──

def get_sim_positions() -> list[dict]:
    """获取模拟持仓"""
    db = get_db()
    rows = db.execute(
        "SELECT * FROM positions WHERE sim_mode=1 AND volume > 0 ORDER BY market_value DESC"
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


def get_sim_orders(limit: int = 30) -> list[dict]:
    """获取模拟订单"""
    db = get_db()
    rows = db.execute(
        "SELECT * FROM orders WHERE sim_mode=1 ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]

def refresh_prices() -> dict:
    """用日线最新收盘价刷新所有模拟持仓市值"""
    db = get_db()
    positions = db.execute(
        "SELECT * FROM positions WHERE sim_mode=1 AND volume > 0"
    ).fetchall()
    updated = 0
    for pos in positions:
        row = db.execute(
            "SELECT close FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 1",
            (pos["code"],)
        ).fetchone()
        if not row or not row["close"]:
            continue
        price = row["close"]
        mv = round(price * pos["volume"], 2)
        pnl = round(pos["volume"] * (price - pos["avg_cost"]), 2)
        pnl_pct = round((price - pos["avg_cost"]) / pos["avg_cost"] * 100, 2) if pos["avg_cost"] else 0
        db.execute(
            """UPDATE positions SET current_price=?, market_value=?,
               profit_loss=?, profit_loss_pct=?,
               updated_at=datetime('now','localtime') WHERE id=?""",
            (price, mv, pnl, pnl_pct, pos["id"])
        )
        updated += 1
    db.commit()
    db.close()
    return {"ok": True, "updated": updated}


def auto_stop_check() -> dict:
    """自动止损止盈扫描：检查所有持仓，触发则自动卖出"""
    # 非交易时间不检查
    ok, _ = _is_trading_time()
    if not ok:
        return {"ok": True, "checked": 0, "triggered": 0, "msg": "非交易时间，跳过"}

    db = get_db()
    positions = db.execute(
        "SELECT * FROM positions WHERE sim_mode=1 AND volume > 0"
    ).fetchall()

    triggered = 0
    for pos in positions:
        # 刷新价格
        row = db.execute(
            "SELECT close FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 1",
            (pos["code"],)
        ).fetchone()
        if not row or not row["close"]:
            continue
        price = float(row["close"])
        pnl_pct = round((price - pos["avg_cost"]) / pos["avg_cost"] * 100, 2) if pos["avg_cost"] else 0

        # 更新持仓价格
        mv = round(price * pos["volume"], 2)
        pnl = round(pos["volume"] * (price - pos["avg_cost"]), 2)
        db.execute(
            """UPDATE positions SET current_price=?, market_value=?,
               profit_loss=?, profit_loss_pct=?,
               updated_at=datetime('now','localtime') WHERE id=?""",
            (price, mv, pnl, pnl_pct, pos["id"])
        )

        # 止损 -8% 或 止盈 +15%
        trigger = None
        if pnl_pct <= -8:
            trigger = f"止损 {pnl_pct}%"
        elif pnl_pct >= 15:
            trigger = f"止盈 {pnl_pct}%"

        if trigger:
            # 创建卖出订单并立即执行
            amount = round(price * pos["volume"], 2)
            cur = db.execute(
                """INSERT INTO orders (code, name, direction, price, volume, amount,
                   order_status, sim_mode) VALUES (?,?,?,?,?,?,'created',1)""",
                (pos["code"], pos["name"], "sell", price, pos["volume"], amount)
            )
            order_id = cur.lastrowid
            db.commit()

            # 执行卖出（复用 execute_sell 逻辑，但需要关闭此连接先）
            db.close()
            result = execute_sell(order_id)
            db = get_db()  # 重新打开
            triggered += 1
            print(f"  🚨 {pos['name']} {trigger} → 自动卖出 {pos['volume']}股 @{price}")

    db.commit()
    db.close()
    return {"ok": True, "checked": len(positions), "triggered": triggered,
            "msg": f"扫描 {len(positions)} 只，触发 {triggered} 笔"}


def get_equity_curve() -> list[dict]:
    """计算净值曲线：每日总资产 = 现金 + 持仓市值"""
    db = get_db()
    # 获取所有交易日
    dates = db.execute(
        "SELECT DISTINCT date FROM daily_kline ORDER BY date"
    ).fetchall()

    acct = db.execute("SELECT * FROM sim_account LIMIT 1").fetchone()
    initial_cash = acct["initial_cash"] if acct else 50000

    curve = []
    holdings = {}  # code -> {volume, avg_cost}

    for d in dates:
        date_str = d["date"]
        # 当天之前的所有成交
        trades = db.execute(
            """SELECT code, action, price, volume FROM trade_log
               WHERE sim_mode=1 AND created_at <= ? ORDER BY id""",
            (date_str + " 23:59:59",)
        ).fetchall()

        # 重建持仓
        holdings = {}
        for t in trades:
            if t["action"] == "open":
                if t["code"] in holdings:
                    h = holdings[t["code"]]
                    total_vol = h["volume"] + t["volume"]
                    h["avg_cost"] = (h["avg_cost"] * h["volume"] + t["price"] * t["volume"]) / total_vol
                    h["volume"] = total_vol
                else:
                    holdings[t["code"]] = {"volume": t["volume"], "avg_cost": t["price"]}
            elif t["action"] == "close":
                if t["code"] in holdings:
                    holdings[t["code"]]["volume"] -= t["volume"]
                    if holdings[t["code"]]["volume"] <= 0:
                        del holdings[t["code"]]

        # 计算当日持仓市值
        mv = 0
        for code, h in holdings.items():
            if h["volume"] > 0:
                row = db.execute(
                    "SELECT close FROM daily_kline WHERE code=? AND date<=? ORDER BY date DESC LIMIT 1",
                    (code, date_str)
                ).fetchone()
                if row:
                    mv += h["volume"] * float(row["close"])

        # 计算现金（初始现金 - 买入总额 + 卖出总额）
        total_buy = sum(t["price"] * t["volume"] for t in trades if t["action"] == "open")
        total_sell = sum(t["price"] * t["volume"] for t in trades if t["action"] == "close")
        cash = initial_cash - total_buy + total_sell

        total = cash + mv
        pnl = total - initial_cash
        pnl_pct = round(pnl / initial_cash * 100, 2)

        curve.append({
            "date": date_str,
            "total": round(total, 2),
            "cash": round(cash, 2),
            "market_value": round(mv, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": pnl_pct,
        })

    db.close()
    return curve


def auto_sell_t1() -> dict:
    """退出检查：止损(-8%) / 止盈(+15%) / 到期(10天) / 信号反转"""
    return auto_exit_check()

def auto_exit_check() -> dict:
    """
    智能退出引擎（对齐回测逻辑）：
    - 止损：浮亏 ≤ -8%
    - 止盈：浮盈 ≥ +15%
    - 到期：持有 ≥ 10 个交易日
    - 信号反转：今日信号变为 sell/strong_sell
    """
    db = get_db()
    today = datetime.now().strftime("%Y-%m-%d")

    positions = db.execute(
        "SELECT * FROM positions WHERE sim_mode=1 AND volume > 0"
    ).fetchall()

    if not positions:
        db.close()
        return {"ok": True, "sold": 0, "msg": "无持仓"}

    results = []
    for pos in positions:
        code = pos["code"]

        # 1. 刷新价格
        price_row = db.execute(
            "SELECT close FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 1", (code,)
        ).fetchone()
        if not price_row or not price_row["close"]:
            continue
        price = float(price_row["close"])
        volume = pos["volume"]
        cost = pos["avg_cost"]

        # 更新持仓价格
        mv = round(price * volume, 2)
        pnl = round(volume * (price - cost), 2)
        pnl_pct = round((price - cost) / cost * 100, 2) if cost else 0
        db.execute(
            """UPDATE positions SET current_price=?, market_value=?,
               profit_loss=?, profit_loss_pct=?, updated_at=datetime('now','localtime')
               WHERE id=?""",
            (price, mv, pnl, pnl_pct, pos["id"])
        )

        # 2. 判断退出条件
        trigger = None
        hold_days = 0

        # 计算持有天数
        buy_date = pos["buy_date"] if "buy_date" in pos.keys() else ""
        if not buy_date:
            # 从 trade_log 回填
            open_log = db.execute(
                """SELECT created_at FROM trade_log
                   WHERE code=? AND action='open' AND sim_mode=1
                   ORDER BY id DESC LIMIT 1""", (code,)
            ).fetchone()
            if open_log:
                buy_date = open_log["created_at"][:10]
                db.execute("UPDATE positions SET buy_date=? WHERE id=?", (buy_date, pos["id"]))

        if buy_date:
            try:
                hold_days = (datetime.strptime(today, "%Y-%m-%d") -
                            datetime.strptime(buy_date, "%Y-%m-%d")).days
            except:
                pass

        # 止损
        if pnl_pct <= -8:
            trigger = f"止损 {pnl_pct}%"
        # 止盈
        elif pnl_pct >= 15:
            trigger = f"止盈 {pnl_pct}%"
        # 到期
        elif hold_days >= 10:
            trigger = f"到期({hold_days}天)"
        # 信号反转
        else:
            sig = db.execute(
                """SELECT signal_type FROM signals
                   WHERE code=? AND date=? ORDER BY id DESC LIMIT 1""",
                (code, today)
            ).fetchone()
            if sig and sig["signal_type"] in ("sell", "strong_sell"):
                trigger = f"信号反转→{sig['signal_type']}"

        if not trigger:
            continue

        # 3. 执行卖出
        amount = round(price * volume, 2)
        cur = db.execute(
            """INSERT INTO orders (code, name, direction, price, volume, amount,
               order_status, sim_mode) VALUES (?,?,?,?,?,?,'filled',1)""",
            (code, pos["name"], "sell", price, volume, amount)
        )
        order_id = cur.lastrowid

        # 回笼资金
        db.execute(
            "UPDATE sim_account SET cash=cash+? WHERE id=(SELECT id FROM sim_account ORDER BY id DESC LIMIT 1)",
            (amount,)
        )

        # 交易日志
        db.execute(
            """INSERT INTO trade_log (order_id, code, action, price, volume, pnl, pnl_pct, hold_days, sim_mode)
               VALUES (?,?, 'close', ?, ?, ?, ?, ?, 1)""",
            (order_id, code, price, volume, pnl, pnl_pct, hold_days)
        )

        # 清理持仓
        db.execute("DELETE FROM positions WHERE id=?", (pos["id"],))

        results.append({
            "code": code, "name": pos["name"], "volume": volume,
            "buy_price": cost, "sell_price": price,
            "pnl": round(pnl, 2), "pnl_pct": pnl_pct,
            "hold_days": hold_days, "trigger": trigger
        })

    db.commit()
    db.close()

    total_pnl = sum(r["pnl"] for r in results)
    return {
        "ok": True, "sold": len(results), "total_pnl": round(total_pnl, 2),
        "trades": results,
        "msg": f"退出检查: 平仓 {len(results)} 笔 (P&L ¥{total_pnl:+,.0f})"
        if results else "退出检查: 无触发"
    }


def auto_trade_from_signals() -> dict:
    """
    自动跟单：读取今天 pending 的买入信号，自动下单成交。
    规则：
    - 先检查市场趋势（熊市/暴跌暂停开仓）
    - 组合最大回撤 >10% → 熔断暂停
    - 只跟 strong_buy / buy 信号（评分≥25）
    - 已有持仓的票跳过，同板块不重复买
    - 仓位按波动率调整（高波少买，低波多买）
    - 最多持有 5 只，单票基准：现金 20% 或 ¥5000
    """
    from benchmark import market_regime_ok

    # 市场趋势过滤
    market_ok, market_msg = market_regime_ok()
    if not market_ok:
        return {"ok": True, "traded": 0, "msg": f"市场过滤: {market_msg}"}

    db = get_db()
    today = datetime.now().strftime("%Y-%m-%d")

    # 组合回撤熔断
    acct = db.execute("SELECT * FROM sim_account ORDER BY id DESC LIMIT 1").fetchone()
    if acct:
        total_pnl_pct = (acct["total_pnl"] or 0) / acct["initial_cash"] * 100 if acct["initial_cash"] else 0
        if total_pnl_pct <= -10:
            db.close()
            return {"ok": True, "traded": 0, "msg": f"🔴 熔断！组合回撤 {total_pnl_pct:.1f}% ≤ -10%，暂停开仓"}
        if total_pnl_pct <= -5:
            # 回撤警告但继续，仓位减半
            pass  # 下面处理

    # 1. 查信号
    rows = db.execute(
        """SELECT * FROM signals
           WHERE date=? AND status='pending'
           AND signal_type IN ('strong_buy','buy')
           ORDER BY strength DESC""",
        (today,)
    ).fetchall()

    if not rows:
        db.close()
        return {"ok": True, "traded": 0, "msg": "今日无 pending 买入信号"}

    # 2. 持仓 + 板块
    held_rows = db.execute(
        "SELECT p.code, p.volume, s.sector FROM positions p "
        "LEFT JOIN stock_pool s ON p.code=s.code "
        "WHERE p.sim_mode=1 AND p.volume>0"
    ).fetchall()
    held_codes = {r["code"] for r in held_rows}
    held_sectors = {r["sector"] for r in held_rows if r["sector"]}

    # 3. 账户
    acct = db.execute("SELECT * FROM sim_account ORDER BY id DESC LIMIT 1").fetchone()
    cash = acct["cash"] if acct else 50000
    total_pnl_pct = (acct["total_pnl"] or 0) / acct["initial_cash"] * 100 if acct and acct["initial_cash"] else 0

    # 4. 已开仓数
    open_cnt = len(held_codes)
    max_new = 5 - open_cnt
    if max_new <= 0:
        db.close()
        return {"ok": True, "traded": 0, "msg": f"已满仓({open_cnt}只)，不再开新仓"}

    # 回撤 -5%~-10%：仓位减半
    drawdown_factor = 0.5 if total_pnl_pct <= -5 else 1.0

    def get_volatility(code):
        """计算20日年化波动率"""
        prices = db.execute(
            "SELECT close FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 21", (code,)
        ).fetchall()
        if len(prices) < 11:
            return None
        closes = [p["close"] for p in reversed(prices)]
        returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
        import math
        daily_vol = (sum(r**2 for r in returns) / len(returns)) ** 0.5
        return daily_vol * math.sqrt(252)  # 年化

    results = []
    skipped = []
    vol_factors = []
    for r in rows:
        if len(results) >= max_new:
            break

        code = r["code"]
        name = r["name"]
        strength = r["strength"] or 0
        score = r["score"] or "{}"

        # 解析 score 验证阈值
        try:
            import json
            sc = json.loads(score)
            if isinstance(sc, dict):
                total = sum(v for v in sc.values() if isinstance(v, (int, float)))
            else:
                total = float(sc) if sc else strength
        except:
            total = strength

        if strength < 25 or total < 25:
            skipped.append({"code": code, "name": name, "reason": f"评分不足 {total:.1f}/{strength:.1f}"})
            continue

        if code in held_codes:
            skipped.append({"code": code, "name": name, "reason": "已持有"})
            continue

        # 板块去重：同板块已有持仓则跳过
        sector_row = db.execute(
            "SELECT sector FROM stock_pool WHERE code=?", (code,)
        ).fetchone()
        stock_sector = sector_row["sector"] if sector_row else None
        if stock_sector and stock_sector in held_sectors:
            skipped.append({"code": code, "name": name, "reason": f"已持有同板块({stock_sector})"})
            continue

        # 获取板块信息（股票池中可能没有，查 signals 的 sector 字段）
        sig_sector = r["sector"] if "sector" in r.keys() and r["sector"] else None
        sector_to_check = stock_sector or sig_sector
        if sector_to_check and sector_to_check in held_sectors:
            skipped.append({"code": code, "name": name, "reason": f"已持有同板块({sector_to_check})"})
            continue

        # 取最新价格
        price_row = db.execute(
            "SELECT close FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 1", (code,)
        ).fetchone()
        if not price_row or not price_row["close"]:
            skipped.append({"code": code, "name": name, "reason": "无价格"})
            continue
        price = float(price_row["close"])

        # 波动率仓位调整
        vol = get_volatility(code)
        vol_factor = 1.0
        if vol is not None:
            # 基准年化波动率 30%，高于则减仓，低于则加仓
            vol_factor = min(1.5, max(0.3, 0.30 / vol))
            vol_factors.append(vol_factor)

        # 仓位计算：20%现金 或 ¥5000，取小，再乘波动率+回撤因子
        trade_amount = min(cash * 0.2, 5000) * vol_factor * drawdown_factor
        volume = max(100, int(trade_amount / price / 100) * 100)  # 整手
        amount = round(price * volume, 2)

        if cash < amount:
            skipped.append({"code": code, "name": name, "reason": f"资金不足(需¥{amount:.0f})"})
            continue

        # 创建订单
        cur = db.execute(
            """INSERT INTO orders (signal_id, code, name, direction, price, volume, amount,
               order_status, sim_mode) VALUES (?,?,?,?,?,?,?,'created',1)""",
            (r["id"], code, name, "buy", price, volume, amount)
        )
        order_id = cur.lastrowid

        # 扣款
        db.execute("UPDATE sim_account SET cash=cash-? WHERE id=?", (amount, acct["id"]))
        cash -= amount

        # 更新订单为已成交
        db.execute(
            "UPDATE orders SET order_status='filled', updated_at=datetime('now','localtime') WHERE id=?",
            (order_id,)
        )

        # 更新持仓
        existing = db.execute(
            "SELECT * FROM positions WHERE code=? AND sim_mode=1", (code,)
        ).fetchone()
        if existing:
            total_vol = existing["volume"] + volume
            new_cost = round((existing["avg_cost"] * existing["volume"] + price * volume) / total_vol, 2)
            new_mv = round(price * total_vol, 2)
            new_pnl = round(total_vol * (price - new_cost), 2)
            new_pnl_pct = round((price - new_cost) / new_cost * 100, 2) if new_cost else 0
            db.execute(
                """UPDATE positions SET volume=?, avg_cost=?, current_price=?,
                   market_value=?, profit_loss=?, profit_loss_pct=?,
                   updated_at=datetime('now','localtime') WHERE id=?""",
                (total_vol, new_cost, price, new_mv, new_pnl, new_pnl_pct, existing["id"])
            )
        else:
            db.execute(
                """INSERT INTO positions (code, name, volume, avg_cost, current_price,
                   market_value, profit_loss, profit_loss_pct, sim_mode, buy_date)
                   VALUES (?,?,?,?,?,?,?,?,1,?)""",
                (code, name, volume, price, price, amount, 0, 0, today)
            )

        # 交易日志
        db.execute(
            """INSERT INTO trade_log (order_id, code, action, price, volume, sim_mode)
               VALUES (?,?, 'open', ?, ?, 1)""",
            (order_id, code, price, volume)
        )

        # 标记信号已使用
        db.execute("UPDATE signals SET status='executed' WHERE id=?", (r["id"],))

        held_codes.add(code)
        if stock_sector:
            held_sectors.add(stock_sector)
        results.append({
            "code": code, "name": name,
            "price": round(price, 2), "volume": volume,
            "amount": round(amount, 2),
            "score": round(total, 1)
        })

    db.commit()
    db.close()

    total_amount = sum(r["amount"] for r in results)
    return {
        "ok": True,
        "traded": len(results),
        "total_amount": round(total_amount, 2),
        "trades": results,
        "skipped": skipped,
        "msg": f"自动跟单 {len(results)} 笔 (共 ¥{total_amount:,.0f})，跳过 {len(skipped)} 只"
    }

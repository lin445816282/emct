"""
EMCT — 复盘引擎
从订单自动生成交易日志，计算盈亏，统计分析
"""
from database import get_db
from datetime import datetime, timedelta


def sync_trade_logs():
    """从已提交/成交订单自动生成交易日志（含模拟订单）"""
    db = get_db()
    orders = db.execute("""
        SELECT o.*, s.name as stock_name
        FROM orders o
        LEFT JOIN stock_pool s ON o.code = s.code
        WHERE o.order_status IN ('submitted', 'filled')
          AND o.id NOT IN (SELECT order_id FROM trade_log WHERE order_id IS NOT NULL)
        ORDER BY o.id
    """).fetchall()
    db.close()

    created = 0
    for o in orders:
        _create_trade_from_order(dict(o))
        created += 1
    return created


def _create_trade_from_order(order: dict):
    """从订单创建交易日志"""
    db = get_db()

    # 判断是开仓还是平仓
    # 简单逻辑：买入=开仓，卖出=平仓
    action = "open" if order["direction"] == "buy" else "close"

    # 平仓时计算盈亏
    pnl = 0
    pnl_pct = 0
    hold_days = 0

    if action == "close":
        # 找到对应的开仓订单
        open_order = db.execute("""
            SELECT * FROM trade_log
            WHERE code=? AND action='open'
            ORDER BY id DESC LIMIT 1
        """, (order["code"],)).fetchone()

        if open_order:
            pnl = (order["price"] - open_order["price"]) * order["volume"]
            pnl_pct = round((order["price"] - open_order["price"]) / open_order["price"] * 100, 2)

            # 计算持仓天数
            try:
                close_dt = datetime.strptime(order["created_at"], "%Y-%m-%d %H:%M:%S")
                open_dt = datetime.strptime(open_order["created_at"], "%Y-%m-%d %H:%M:%S")
                hold_days = (close_dt - open_dt).days
            except:
                hold_days = 0

    db.execute("""
        INSERT INTO trade_log (order_id, code, action, price, volume, pnl, pnl_pct, hold_days)
        VALUES (?,?,?,?,?,?,?,?)
    """, (order["id"], order["code"], action, order["price"], order["volume"],
          round(pnl, 2), pnl_pct, hold_days))
    db.commit()
    db.close()


def get_stats() -> dict:
    """获取整体交易统计（含未平仓浮动盈亏）"""
    db = get_db()
    stats = db.execute("""
        SELECT
            COUNT(*) as total_trades,
            COUNT(CASE WHEN action='close' THEN 1 END) as closed_trades,
            COUNT(CASE WHEN action='close' AND pnl > 0 THEN 1 END) as wins,
            COUNT(CASE WHEN action='close' AND pnl < 0 THEN 1 END) as losses,
            COUNT(CASE WHEN action='close' AND pnl = 0 THEN 1 END) as breakeven,
            COALESCE(SUM(CASE WHEN action='close' THEN pnl END), 0) as total_pnl,
            COALESCE(AVG(CASE WHEN action='close' THEN pnl_pct END), 0) as avg_pnl_pct,
            COALESCE(AVG(CASE WHEN action='close' AND pnl > 0 THEN pnl_pct END), 0) as avg_win_pct,
            COALESCE(AVG(CASE WHEN action='close' AND pnl < 0 THEN pnl_pct END), 0) as avg_loss_pct,
            COALESCE(AVG(CASE WHEN action='close' THEN hold_days END), 0) as avg_hold_days,
            COALESCE(MAX(CASE WHEN action='close' THEN pnl END), 0) as best_trade,
            COALESCE(MIN(CASE WHEN action='close' THEN pnl END), 0) as worst_trade
        FROM trade_log
    """).fetchone()

    result = dict(stats) if stats else {}
    closed = result.get("closed_trades", 0) or 0
    wins = result.get("wins", 0) or 0
    losses = result.get("losses", 0) or 0
    breakeven = result.get("breakeven", 0) or 0

    # 计算未平仓浮动盈亏
    open_pnl = _calc_open_pnl(db)

    # 胜率区分显示
    if closed == 0:
        display_win_rate = "--"
    elif wins + losses == 0:
        display_win_rate = "平盘"
    else:
        display_win_rate = f"{round(wins / closed * 100, 1)}%"

    result["win_rate"] = display_win_rate
    result["win_rate_num"] = round(wins / closed * 100, 1) if closed > 0 else 0
    result["profit_factor"] = _calc_profit_factor(db) if closed > 0 else 0
    result["open_pnl"] = open_pnl  # 未平仓浮动盈亏
    result["total_pnl_all"] = result["total_pnl"] + open_pnl  # 含浮动

    db.close()
    return result


def _calc_open_pnl(db) -> float:
    """计算所有未平仓的浮动盈亏（用新浪实时价）"""
    open_trades = db.execute("""
        SELECT tl.code, tl.price, tl.volume
        FROM trade_log tl
        WHERE tl.action='open'
          AND tl.code NOT IN (
              SELECT code FROM trade_log WHERE action='close'
          )
        GROUP BY tl.code
        HAVING SUM(tl.volume) > 0
    """).fetchall()

    if not open_trades:
        return 0.0

    # 批量获取实时价格
    codes = [r["code"] for r in open_trades]
    prices = _get_sina_prices(codes)

    total_pnl = 0.0
    for t in open_trades:
        cur = prices.get(t["code"], t["price"])
        total_pnl += (cur - t["price"]) * t["volume"]
    return round(total_pnl, 2)


def _get_sina_prices(codes: list) -> dict:
    """新浪批量获取实时价 → {code: price}"""
    try:
        import urllib.request
        sina_codes = [("sh" if c.startswith("6") else "sz") + c for c in codes]
        url = "http://hq.sinajs.cn/list=" + ",".join(sina_codes)
        req = urllib.request.Request(url, headers={"Referer": "https://finance.sina.com.cn"})
        resp = urllib.request.urlopen(req, timeout=5)
        prices = {}
        for line in resp.read().decode("gbk", errors="ignore").strip().split("\n"):
            if "=" not in line: continue
            raw = line.split('"')[1] if '"' in line else ""
            parts = raw.split(",")
            if len(parts) < 4: continue
            try:
                price = float(parts[3])
                if price > 0:
                    key = line.split("=")[0].replace("var hq_str_", "")
                    prices[key[2:]] = price  # 去 sh/sz 前缀
            except (ValueError, IndexError): continue
        return prices
    except Exception:
        return {}


def _calc_profit_factor(db) -> float:
    """盈亏比：总盈利/|总亏损|"""
    row = db.execute("""
        SELECT
            COALESCE(SUM(CASE WHEN pnl > 0 THEN pnl END), 0) as gross_profit,
            COALESCE(SUM(CASE WHEN pnl < 0 THEN ABS(pnl) END), 0) as gross_loss
        FROM trade_log WHERE action='close'
    """).fetchone()
    if row and row["gross_loss"] > 0:
        return round(row["gross_profit"] / row["gross_loss"], 2)
    return 0


def get_monthly_pnl() -> list[dict]:
    """月度盈亏汇总"""
    db = get_db()
    rows = db.execute("""
        SELECT strftime('%Y-%m', created_at) as month,
               COUNT(*) as trades,
               COALESCE(SUM(pnl), 0) as pnl,
               COUNT(CASE WHEN pnl > 0 THEN 1 END) as wins,
               COUNT(CASE WHEN pnl < 0 THEN 1 END) as losses
        FROM trade_log WHERE action='close'
        GROUP BY month ORDER BY month DESC LIMIT 12
    """).fetchall()
    db.close()
    return [dict(r) for r in rows]


def get_stock_performance() -> list[dict]:
    """各股票表现排行"""
    db = get_db()
    rows = db.execute("""
        SELECT t.code, COALESCE(s.name, t.code) as name,
               COUNT(*) as trades,
               COALESCE(SUM(t.pnl), 0) as total_pnl,
               COUNT(CASE WHEN t.pnl > 0 THEN 1 END) as wins,
               COUNT(CASE WHEN t.pnl < 0 THEN 1 END) as losses,
               ROUND(AVG(t.pnl_pct), 2) as avg_pnl_pct
        FROM trade_log t
        LEFT JOIN stock_pool s ON t.code = s.code
        WHERE t.action='close'
        GROUP BY t.code
        ORDER BY total_pnl DESC
    """).fetchall()
    db.close()
    return [dict(r) for r in rows]


def get_timeline(limit: int = 50) -> list[dict]:
    """交易时间线"""
    db = get_db()
    rows = db.execute("""
        SELECT * FROM trade_log ORDER BY id DESC LIMIT ?
    """, (limit,)).fetchall()
    db.close()
    return [dict(r) for r in rows]


def add_review(trade_id: int, review: str, tags: str = ""):
    """添加复盘笔记"""
    db = get_db()
    db.execute(
        "UPDATE trade_log SET review=?, tags=? WHERE id=?",
        (review, tags, trade_id)
    )
    db.commit()
    db.close()
    return {"ok": True}


def get_review_summary() -> str:
    """生成复盘文本摘要（供AI分析）"""
    stats = get_stats()
    monthly = get_monthly_pnl()
    stocks = get_stock_performance()

    lines = [
        f"📊 交易统计：共{stats.get('total_trades', 0)}笔，"
        f"已平仓{stats.get('closed_trades', 0)}笔，"
        f"胜率{stats.get('win_rate', 0)}%，"
        f"总盈亏¥{stats.get('total_pnl', 0):,.2f}，"
        f"盈亏比{stats.get('profit_factor', 0)}",
        f"平均盈亏{stats.get('avg_pnl_pct', 0):.2f}%，"
        f"平均持仓{stats.get('avg_hold_days', 0):.0f}天",
    ]

    if stocks:
        lines.append("\n📈 股票表现：")
        for s in stocks[:5]:
            wl = f"{s['wins']}W/{s['losses']}L" if s['wins'] + s['losses'] > 0 else "-"
            lines.append(f"  {s['name']} P&L ¥{s['total_pnl']:,.2f} ({wl})")

    if monthly:
        lines.append("\n📅 月度：")
        for m in monthly[:6]:
            lines.append(f"  {m['month']} ¥{m['pnl']:,.2f} ({m['wins']}W/{m['losses']}L)")

    return "\n".join(lines)


def deepseek_analyze(summary_text: str, api_key: str = "") -> str:
    """调用 DeepSeek API 生成交易复盘分析"""
    if not api_key:
        try:
            from config import DEEPSEEK_API_KEY
            api_key = DEEPSEEK_API_KEY
        except ImportError:
            pass

    if not api_key:
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")

    if not api_key:
        return _fallback_analysis(summary_text)

    prompt = f"""你是一位专业量化交易分析师。根据以下交易数据，用中文给出简洁的复盘分析：

{summary_text}

请分析：
1. 整体交易表现评价（1-2句）
2. 主要问题或风险点
3. 1-2条可操作的改进建议

用自然对话语气，不要用markdown格式，150字以内。"""

    try:
        req = urllib.request.Request(
            "https://api.deepseek.com/v1/chat/completions",
            data=json.dumps({
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 300,
                "temperature": 0.7,
            }).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"[AI分析失败: {str(e)[:100]}]\n\n{_fallback_analysis(summary_text)}"


def _fallback_analysis(summary_text: str) -> str:
    """AI不可用时的备用分析模板"""
    stats = get_stats()
    parts = [f"基于数据：\n{summary_text}\n"]
    parts.append("📌 参考建议：")
    parts.append("1. 关注胜率与盈亏比的平衡，理想状态胜率>50%且盈亏比>1.5")
    parts.append("2. 控制单笔亏损不超过总资金2%")
    parts.append("3. 连亏3笔后暂停交易，复盘原因")
    return "\n".join(parts)


import os, json, urllib.request

if __name__ == "__main__":
    print(get_review_summary())

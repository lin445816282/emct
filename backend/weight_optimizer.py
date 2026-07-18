"""
因子权重自适应优化 — 基于历史信号→收益相关性评估
"""
import numpy as np
from datetime import datetime, timedelta, date
from database import get_db
from analyzer import _compute_all_factors, load_klines, WEIGHTS

FACTORS = list(WEIGHTS.keys())


def generate_weight_candidates(n=200):
    """生成权重候选"""
    candidates = []
    candidates.append({"name": "current", "weights": WEIGHTS.copy()})

    eq = {f: 1/len(FACTORS) for f in FACTORS}
    candidates.append({"name": "equal", "weights": eq})

    for f in FACTORS:
        w = {k: 0.05 for k in FACTORS}
        w[f] = 0.75
        candidates.append({"name": f"heavy_{f}", "weights": w})

    np.random.seed(42)
    for i in range(min(n, 200)):
        raw = np.random.dirichlet(np.ones(len(FACTORS)))
        candidates.append({"name": f"random_{i}", "weights": dict(zip(FACTORS, raw))})

    return candidates


def evaluate_weights(weights: dict, max_stocks=15, lookback=60) -> dict:
    """
    评估权重：对每只股票，在回看窗口内逐日计算因子分→组合分
    检查组合分与实际5日/10日收益的相关性
    """
    db = get_db()
    stocks = db.execute(
        "SELECT code, name FROM stock_pool WHERE active=1 LIMIT ?",
        (max_stocks,)
    ).fetchall()
    db.close()

    total_good = 0
    total_bad = 0
    total_signal = 0
    returns_when_bull = []
    returns_when_bear = []

    for s in stocks:
        rows = load_klines(s["code"], min_bars=lookback + 30)
        if rows is None or len(rows) < lookback:
            continue

        closes = np.array([r["close"] for r in rows], dtype=np.float64)
        n = len(closes)

        # 滑动窗口：对每个交易日采样
        for i in range(lookback, n - 10, 5):
            # 用 i 位置之前的数据计算因子
            window = rows[:i+1]
            if len(window) < 60:
                continue

            result = _compute_all_factors(window, weights)
            if "error" in result:
                continue

            score = result.get("score", 0)
            if abs(score) < 1:  # 忽略极弱信号
                continue

            # 计算未来5日/10日收益
            future_5d = (closes[min(i+5, n-1)] - closes[i]) / closes[i] * 100 if i+5 < n else None
            future_10d = (closes[min(i+10, n-1)] - closes[i]) / closes[i] * 100 if i+10 < n else None

            total_signal += 1

            if score > 0:  # 看涨信号
                if future_5d is not None:
                    returns_when_bull.append(future_5d)
                    if future_5d > 0:
                        total_good += 1
                    else:
                        total_bad += 1
            else:  # 看跌信号
                if future_5d is not None:
                    returns_when_bear.append(future_5d)
                    if future_5d < 0:
                        total_good += 1
                    else:
                        total_bad += 1

    # 综合评分
    accuracy = total_good / max(total_good + total_bad, 1) * 100
    avg_bull_ret = np.mean(returns_when_bull) if returns_when_bull else 0
    avg_bear_ret = np.mean(returns_when_bear) if returns_when_bear else 0
    spread = avg_bull_ret - avg_bear_ret if returns_when_bull and returns_when_bear else 0
    sharpe = spread / (np.std(returns_when_bull + returns_when_bear) + 1e-8) if returns_when_bull and returns_when_bear else 0

    composite = accuracy * spread if spread > 0 else accuracy * 0.5

    return {
        "accuracy": round(accuracy, 1),
        "avg_bull_return": round(float(avg_bull_ret), 2),
        "avg_bear_return": round(float(avg_bear_ret), 2),
        "spread": round(float(spread), 2),
        "sharpe": round(float(sharpe), 2),
        "composite": round(float(composite), 2),
        "total_signals": total_signal,
        "bull_signals": len(returns_when_bull),
        "bear_signals": len(returns_when_bear),
    }


def optimize(n_iter=50, max_stocks=15):
    """主入口：随机搜索最优权重"""
    candidates = generate_weight_candidates(n_iter)
    results = []

    for i, c in enumerate(candidates):
        ev = evaluate_weights(c["weights"], max_stocks=max_stocks)
        results.append({
            "name": c["name"],
            "weights": {k: round(v, 3) for k, v in c["weights"].items()},
            **ev,
        })

    results.sort(key=lambda x: x.get("composite", -999), reverse=True)

    return {
        "ok": True,
        "tested": len(results),
        "best": results[0] if results else None,
        "top5": results[:5],
        "current": {k: round(v, 3) for k, v in WEIGHTS.items()},
    }

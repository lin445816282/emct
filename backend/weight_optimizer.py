"""
权重优化引擎 — 网格搜索 + 随机采样，评估信号准确率
"""
import numpy as np
import json
from typing import Optional
from database import get_db
from analyzer import _compute_all_factors, load_klines


FACTOR_NAMES = ["ma_trend", "macd", "rsi", "bollinger", "volume", "momentum"]


def generate_candidates(n_iter: int = 200) -> list[dict]:
    """生成候选权重组合：当前权重/等权/单因子主导/随机采样"""
    candidates = []

    # 当前权重
    from analyzer import WEIGHTS
    candidates.append(dict(WEIGHTS))

    # 等权
    eq = {k: 1/6 for k in FACTOR_NAMES}
    candidates.append(eq)

    # 单因子主导（每个因子占 50%）
    for f in FACTOR_NAMES:
        w = {k: 0.1 for k in FACTOR_NAMES}
        w[f] = 0.5
        total = sum(w.values())
        candidates.append({k: v/total for k, v in w.items()})

    # 随机采样（Dirichlet 分布）
    rng = np.random.default_rng(42)
    for _ in range(n_iter - len(candidates)):
        raw = rng.dirichlet(np.ones(6))
        candidates.append({FACTOR_NAMES[i]: round(float(raw[i]), 4) for i in range(6)})

    return candidates


def evaluate_weights(
    weights: dict,
    max_stocks: int = 15,
    lookback: int = 60,
    forward_days: int = 5,
) -> dict:
    """
    评估一组权重：对每只股票滑动窗口计算因子分 → 判断方向准确率

    返回 {accuracy, buy_hit_rate, sell_hit_rate, buy_return, sell_return, score}
    """
    db = get_db()
    active = db.execute(
        "SELECT code, name FROM stock_pool WHERE active=1 LIMIT ?", (max_stocks,)
    ).fetchall()
    db.close()

    total_signals = 0
    buy_correct = 0
    sell_correct = 0
    buy_returns = []
    sell_returns = []

    for stock in active:
        code = stock["code"]
        rows = load_klines(code, min_bars=lookback + 30)
        if rows is None:
            continue

        closes = np.array([r["close"] for r in rows], dtype=np.float64)
        n = len(closes)

        # 滑动窗口：每5天算一次因子分，看未来5天收益
        for i in range(lookback, n - forward_days, 5):
            window = rows[i - lookback:i]
            if len(window) < 35:
                continue

            result = _compute_all_factors(window, weights)
            if result.get("error"):
                continue

            score = result.get("score", 0)
            future_return = (closes[i + forward_days] - closes[i]) / closes[i]

            total_signals += 1
            if score > 10:  # 看涨
                buy_returns.append(future_return)
                if future_return > 0:
                    buy_correct += 1
            elif score < -10:  # 看跌
                sell_returns.append(future_return)
                if future_return < 0:
                    sell_correct += 1

    if total_signals == 0:
        return {"accuracy": 0, "score": -999, "total_signals": 0}

    buy_total = len(buy_returns)
    sell_total = len(sell_returns)
    buy_hit = buy_correct / buy_total if buy_total else 0
    sell_hit = sell_correct / sell_total if sell_total else 0
    accuracy = (buy_correct + sell_correct) / total_signals if total_signals else 0

    avg_buy_ret = float(np.mean(buy_returns)) if buy_returns else 0
    avg_sell_ret = float(np.mean(sell_returns)) if sell_returns else 0

    # 综合评分：准确率 × (看涨收益 - 看跌收益)
    ret_spread = avg_buy_ret - avg_sell_ret
    composite = accuracy * max(ret_spread, 0.001) * 100

    return {
        "accuracy": round(accuracy, 4),
        "buy_hit_rate": round(buy_hit, 4),
        "sell_hit_rate": round(sell_hit, 4),
        "avg_buy_return": round(avg_buy_ret, 4),
        "avg_sell_return": round(avg_sell_ret, 4),
        "score": round(composite, 4),
        "total_signals": total_signals,
        "buy_signals": buy_total,
        "sell_signals": sell_total,
    }


def optimize_weights(
    n_iter: int = 200,
    max_stocks: int = 15,
) -> dict:
    """搜索最优权重组合"""
    from analyzer import WEIGHTS as current_weights

    candidates = generate_candidates(n_iter)
    results = []

    current_result = None
    best = None
    best_score = -9999

    for i, w in enumerate(candidates):
        result = evaluate_weights(w, max_stocks=max_stocks)
        result["weights"] = w
        result["rank"] = i + 1
        results.append(result)

        if result["score"] > best_score:
            best_score = result["score"]
            best = result

        # 标记当前权重
        if w == current_weights:
            current_result = result

    # 按 score 排序
    results.sort(key=lambda x: x["score"], reverse=True)
    for i, r in enumerate(results):
        r["rank"] = i + 1

    return {
        "ok": True,
        "best": {
            "weights": best["weights"],
            "accuracy": best["accuracy"],
            "buy_hit_rate": best["buy_hit_rate"],
            "sell_hit_rate": best["sell_hit_rate"],
            "score": best["score"],
            "total_signals": best["total_signals"],
        } if best else None,
        "current": {
            "weights": current_weights,
            "accuracy": current_result["accuracy"] if current_result else 0,
            "score": current_result["score"] if current_result else 0,
        } if current_result else None,
        "candidates": len(candidates),
        "top5": results[:5],
    }

# Alias for signals.py import
optimize = optimize_weights

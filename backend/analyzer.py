"""
EMCT — 多因子技术分析引擎
基于 TA-Lib 计算指标，加权评分生成买卖信号
"""
import numpy as np
from typing import Optional
from database import get_db

# ── 因子权重 ──
WEIGHTS = {
    "ma_trend": 0.25,      # 均线排列
    "macd": 0.20,          # MACD 金叉死叉
    "rsi": 0.15,           # RSI 超买超卖
    "bollinger": 0.15,     # 布林带位置
    "volume": 0.10,        # 量价配合
    "momentum": 0.15,      # 近期动量
}

# ── 信号阈值 ──
SIGNAL_THRESHOLDS = {
    "strong_buy": 30,
    "buy": 10,
    "sell": -10,
    "strong_sell": -30,
}


def load_klines(code: str, min_bars: int = 60) -> Optional[np.ndarray]:
    """从DB加载日线，返回结构化数组"""
    db = get_db()
    rows = db.execute(
        "SELECT date, open, high, low, close, volume, amount FROM daily_kline "
        "WHERE code=? ORDER BY date ASC",
        (code,)
    ).fetchall()
    db.close()
    if len(rows) < min_bars:
        return None
    return rows


def compute_all_factors(rows) -> dict:
    return _compute_all_factors(rows, WEIGHTS)

def _compute_all_factors(rows, weights: dict = None) -> dict:
    """计算所有技术因子，返回评分明细"""
    closes = np.array([r["close"] for r in rows], dtype=np.float64)
    highs = np.array([r["high"] for r in rows], dtype=np.float64)
    lows = np.array([r["low"] for r in rows], dtype=np.float64)
    volumes = np.array([r["volume"] for r in rows], dtype=np.float64)

    scores = {}
    details = {}
    n = len(closes)
    latest = closes[-1]

    # ── 1. 均线趋势 (MA5/10/20/60) ──
    ma5 = talib.SMA(closes, 5)
    ma10 = talib.SMA(closes, 10)
    ma20 = talib.SMA(closes, 20)
    ma60 = talib.SMA(closes, 60)

    ma_score = 0
    ma_reasons = []
    if not np.isnan(ma5[-1]) and not np.isnan(ma10[-1]) and not np.isnan(ma20[-1]):
        if ma5[-1] > ma10[-1] > ma20[-1]:
            ma_score += 40
            ma_reasons.append("多头排列")
        elif ma5[-1] < ma10[-1] < ma20[-1]:
            ma_score -= 40
            ma_reasons.append("空头排列")

        if latest > ma5[-1]:
            ma_score += 20
            ma_reasons.append("站上MA5")
        elif latest < ma5[-1]:
            ma_score -= 20
            ma_reasons.append("跌破MA5")

        # 均线斜率
        if n >= 6:
            slope5 = (ma5[-1] - ma5[-6]) / ma5[-6] * 100
            if slope5 > 1:
                ma_score += 15
            elif slope5 < -1:
                ma_score -= 15

    if not np.isnan(ma60[-1]):
        if latest > ma60[-1]:
            ma_score += 25
            ma_reasons.append("站上MA60")
        else:
            ma_score -= 25
            ma_reasons.append("跌破MA60")

    scores["ma_trend"] = np.clip(ma_score, -100, 100)
    details["ma_trend"] = {"ma5": round(ma5[-1], 2) if not np.isnan(ma5[-1]) else None,
                           "ma20": round(ma20[-1], 2) if not np.isnan(ma20[-1]) else None,
                           "ma60": round(ma60[-1], 2) if not np.isnan(ma60[-1]) else None,
                           "reasons": ma_reasons}

    # ── 2. MACD ──
    macd_line, signal_line, hist = talib.MACD(closes)
    macd_score = 0
    macd_reasons = []

    if n >= 35 and not np.isnan(macd_line[-1]):
        # 金叉检测：前一根 hist < 0，当前 hist >= 0
        if hist[-2] < 0 and hist[-1] >= 0:
            macd_score += 60
            macd_reasons.append("MACD金叉")
        # 死叉
        elif hist[-2] > 0 and hist[-1] <= 0:
            macd_score -= 60
            macd_reasons.append("MACD死叉")

        # 柱状图方向
        if len(hist) >= 4:
            if hist[-1] > hist[-2] > hist[-3]:
                macd_score += 20
                macd_reasons.append("红柱放大")
            elif hist[-1] < hist[-2] < hist[-3]:
                macd_score -= 20
                macd_reasons.append("绿柱放大")

        # 零轴位置
        if macd_line[-1] > 0:
            macd_score += 20
        else:
            macd_score -= 20

    scores["macd"] = np.clip(macd_score, -100, 100)
    details["macd"] = {"macd": round(macd_line[-1], 4) if not np.isnan(macd_line[-1]) else None,
                       "signal": round(signal_line[-1], 4) if not np.isnan(signal_line[-1]) else None,
                       "hist": round(hist[-1], 4) if not np.isnan(hist[-1]) else None,
                       "reasons": macd_reasons}

    # ── 3. RSI (14) ──
    rsi = talib.RSI(closes, 14)
    rsi_score = 0
    rsi_reasons = []

    if not np.isnan(rsi[-1]):
        rsi_val = rsi[-1]
        if rsi_val < 30:
            rsi_score += 50
            rsi_reasons.append(f"超卖({rsi_val:.0f})")
        elif rsi_val < 40:
            rsi_score += 25
        elif rsi_val > 70:
            rsi_score -= 50
            rsi_reasons.append(f"超买({rsi_val:.0f})")
        elif rsi_val > 60:
            rsi_score -= 25

        # RSI方向
        if len(rsi) >= 3 and not np.isnan(rsi[-3]):
            if rsi[-1] > rsi[-3]:
                rsi_score += 15

    scores["rsi"] = np.clip(rsi_score, -100, 100)
    details["rsi"] = {"rsi": round(rsi[-1], 2) if not np.isnan(rsi[-1]) else None,
                      "reasons": rsi_reasons}

    # ── 4. 布林带 ──
    upper, middle, lower = talib.BBANDS(closes, 20, 2, 2)
    bb_score = 0
    bb_reasons = []

    if not np.isnan(lower[-1]):
        width_pct = (upper[-1] - lower[-1]) / middle[-1] * 100
        position = (latest - lower[-1]) / (upper[-1] - lower[-1])  # 0=下轨, 1=上轨

        if position < 0.1:
            bb_score += 60
            bb_reasons.append("触下轨")
        elif position < 0.25:
            bb_score += 30
            bb_reasons.append("近下轨")
        elif position > 0.9:
            bb_score -= 60
            bb_reasons.append("触上轨")
        elif position > 0.75:
            bb_score -= 30
            bb_reasons.append("近上轨")

        # 带宽
        if width_pct < 5:
            bb_score += 15  # 收窄酝酿突破
            bb_reasons.append("带宽收窄")

        # 中轨突破方向
        if n >= 2 and latest > middle[-1] and closes[-2] <= middle[-2]:
            bb_score += 25
            bb_reasons.append("突破中轨")
        elif n >= 2 and latest < middle[-1] and closes[-2] >= middle[-2]:
            bb_score -= 25
            bb_reasons.append("跌破中轨")

    scores["bollinger"] = np.clip(bb_score, -100, 100)
    details["bollinger"] = {"upper": round(upper[-1], 2) if not np.isnan(upper[-1]) else None,
                            "middle": round(middle[-1], 2) if not np.isnan(middle[-1]) else None,
                            "lower": round(lower[-1], 2) if not np.isnan(lower[-1]) else None,
                            "position": round(position, 3) if not np.isnan(lower[-1]) else None,
                            "reasons": bb_reasons}

    # ── 5. 量价配合 ──
    vol_score = 0
    vol_reasons = []

    if len(volumes) >= 10:
        avg_vol_10 = np.mean(volumes[-11:-1])
        avg_vol_5 = np.mean(volumes[-6:-1])
        today_vol = volumes[-1]

        # 放量
        vol_ratio = today_vol / avg_vol_10 if avg_vol_10 > 0 else 1
        if vol_ratio > 2:
            vol_reasons.append("巨量")
            if latest > closes[-2]:
                vol_score += 30  # 放量上涨好
            else:
                vol_score -= 30  # 放量下跌差
        elif vol_ratio > 1.5:
            vol_reasons.append("放量")
            if latest > closes[-2]:
                vol_score += 20
            else:
                vol_score -= 20
        elif vol_ratio < 0.5:
            vol_reasons.append("缩量")
            vol_score += 5

        # 量能趋势：5日均量 vs 10日均量
        if avg_vol_5 > avg_vol_10 * 1.2:
            vol_score += 15
            vol_reasons.append("量能放大")

    scores["volume"] = np.clip(vol_score, -100, 100)
    details["volume"] = {"vol_ratio": round(vol_ratio, 2) if len(volumes) >= 10 else None,
                         "reasons": vol_reasons}

    # ── 6. 近期动量 ──
    mom_score = 0
    mom_reasons = []

    if n >= 5:
        chg_5d = (latest - closes[-5]) / closes[-5] * 100
        if chg_5d > 5:
            mom_score += 30
            mom_reasons.append(f"5日涨{chg_5d:.1f}%")
        elif chg_5d > 2:
            mom_score += 15
        elif chg_5d < -5:
            mom_score -= 30
            mom_reasons.append(f"5日跌{abs(chg_5d):.1f}%")
        elif chg_5d < -2:
            mom_score -= 15

    if n >= 20:
        chg_20d = (latest - closes[-20]) / closes[-20] * 100
        if chg_20d > 10:
            mom_score -= 20  # 涨幅过大，回调风险
            mom_reasons.append(f"20日涨{chg_20d:.1f}%")
        elif chg_20d < -10:
            mom_score += 20  # 超跌反弹机会
            mom_reasons.append(f"20日跌{abs(chg_20d):.1f}%")

    scores["momentum"] = np.clip(mom_score, -100, 100)
    details["momentum"] = {"chg_5d": round(chg_5d, 2) if n >= 5 else None,
                           "chg_20d": round(chg_20d, 2) if n >= 20 else None,
                           "reasons": mom_reasons}

    # ── 加权汇总 ──
    w = weights if weights is not None else WEIGHTS
    total = sum(scores[k] * w[k] for k in WEIGHTS)
    signal_type = "hold"
    if total >= SIGNAL_THRESHOLDS["strong_buy"]:
        signal_type = "strong_buy"
    elif total >= SIGNAL_THRESHOLDS["buy"]:
        signal_type = "buy"
    elif total <= SIGNAL_THRESHOLDS["strong_sell"]:
        signal_type = "strong_sell"
    elif total <= SIGNAL_THRESHOLDS["sell"]:
        signal_type = "sell"

    # 汇总所有原因
    all_reasons = []
    for k in WEIGHTS:
        for r in details[k].get("reasons", []):
            all_reasons.append(f"[{k}] {r}")

    return {
        "score": round(float(total), 1),
        "signal_type": signal_type,
        "strength": abs(float(total)),
        "factor_scores": {k: round(float(v), 1) for k, v in scores.items()},
        "details": details,
        "reasons": all_reasons,
        "price_ref": round(float(latest), 2),
    }


def analyze_stock(code: str, name: str) -> Optional[dict]:
    """分析单只股票，返回信号"""
    rows = load_klines(code)
    if rows is None:
        return {"code": code, "name": name, "error": "数据不足"}
    result = compute_all_factors(rows)
    result["code"] = code
    result["name"] = name
    return result


def scan_all() -> list[dict]:
    """扫描全部活跃股票，返回信号列表（按评分排序）"""
    db = get_db()
    stocks = db.execute("SELECT code, name FROM stock_pool WHERE active=1").fetchall()
    db.close()

    signals = []
    for s in stocks:
        r = analyze_stock(s["code"], s["name"])
        if r and "error" not in r:
            signals.append(r)

    signals.sort(key=lambda x: abs(x["score"]), reverse=True)
    return signals


# 延迟导入避免循环
import talib

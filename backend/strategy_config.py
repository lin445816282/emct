"""策略配置持久化模块 — 从 DB 读写，支持热更新"""
import json
from database import get_db

DEFAULTS = {
    "weights": {
        "ma_trend": 0.18, "macd": 0.18, "rsi": 0.14,
        "bollinger": 0.17, "volume": 0.17, "momentum": 0.16
    },
    "thresholds": {
        "strong_buy": 28, "buy": 10, "sell": -10, "strong_sell": -28
    },
    "bear_factor": 0.5,
    "max_positions": 8,
    "min_strength": 10,
    "max_single_amount": 5000,
    "stop_loss_pct": -8,
    "take_profit_pct": 15,
    "trailing_stop_pct": 3,  # 移动止损：从最高点回撤3%触发卖出
    "risk_per_trade_pct": 2,  # 单笔风险比例（%），决定仓位大小
    "max_hold_days": 10,
    "circuit_breaker_pct": -15,  # 组合回撤熔断线（负数，如 -15 表示亏 15% 停开仓）
    "caution_drawdown_pct": -7,   # 回撤警告线（负数，触及减半仓位）
    "caution_factor": 0.6,        # 警告仓位系数（如 0.6 = 降至60%）
}

# 内存缓存（短TTL，避免多进程读到过期配置）
_cache = None
_cache_time = 0
_CACHE_TTL = 5  # 秒，足够短让 cron job 进程间同步


def _init_table():
    """确保 strategy_config 表存在"""
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS strategy_config (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            data TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            version INTEGER NOT NULL DEFAULT 1
        )
    """)
    # 插入默认配置（如果不存在）
    row = db.execute("SELECT id FROM strategy_config WHERE id = 1").fetchone()
    if not row:
        db.execute(
            "INSERT INTO strategy_config (id, data) VALUES (1, ?)",
            (json.dumps(DEFAULTS, ensure_ascii=False),)
        )
    db.commit()
    db.close()


def get_config() -> dict:
    """获取当前策略配置（5秒TTL缓存，跨进程同步友好）"""
    global _cache, _cache_time
    import time
    now = time.time()
    if _cache is not None and (now - _cache_time) < _CACHE_TTL:
        return _cache

    db = get_db()
    row = db.execute("SELECT data FROM strategy_config WHERE id = 1").fetchone()
    db.close()

    if row:
        _cache = json.loads(row["data"])
    else:
        _init_table()
        _cache = dict(DEFAULTS)
    _cache_time = now
    return _cache


def save_config(config: dict) -> dict:
    """保存策略配置（覆写整份 JSON），返回验后的 config"""
    global _cache
    
    # 校验：合并默认值，防止缺字段
    merged = dict(DEFAULTS)
    merged.update(config)
    
    # 校验权重和为 1
    w = merged["weights"]
    total = sum(w.values())
    if abs(total - 1.0) > 0.001:
        # 自动归一化
        for k in w:
            w[k] = round(w[k] / total, 4)
    
    # 写入 DB
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO strategy_config (id, data, updated_at, version) VALUES (1, ?, datetime('now','localtime'), COALESCE((SELECT version+1 FROM strategy_config WHERE id=1), 1))",
        (json.dumps(merged, ensure_ascii=False),)
    )
    db.commit()
    db.close()
    
    _cache = merged
    return merged


def reset_config() -> dict:
    """恢复默认配置"""
    global _cache
    _cache = None
    
    db = get_db()
    db.execute("DELETE FROM strategy_config WHERE id = 1")
    db.commit()
    db.close()
    
    return get_config()


def get_weights() -> dict:
    return get_config()["weights"]


def get_thresholds() -> dict:
    return get_config()["thresholds"]


def get_bear_factor() -> float:
    return get_config()["bear_factor"]


def get_max_positions() -> int:
    return get_config()["max_positions"]


def get_risk_params() -> dict:
    cfg = get_config()
    return {
        "stop_loss_pct": cfg["stop_loss_pct"],
        "take_profit_pct": cfg["take_profit_pct"],
        "trailing_stop_pct": cfg.get("trailing_stop_pct", 3),
        "risk_per_trade_pct": cfg.get("risk_per_trade_pct", 2),
        "max_hold_days": cfg["max_hold_days"],
        "max_single_amount": cfg["max_single_amount"],
        "min_strength": cfg["min_strength"],
        "circuit_breaker_pct": cfg.get("circuit_breaker_pct", -15),
        "caution_drawdown_pct": cfg.get("caution_drawdown_pct", -7),
        "caution_factor": cfg.get("caution_factor", 0.6),
    }


def get_config_snapshot() -> str:
    """返回当前配置的 JSON 快照，含版本号，用于订单审计"""
    import json
    cfg = get_config()
    db = get_db()
    row = db.execute("SELECT version FROM strategy_config WHERE id=1").fetchone()
    db.close()
    snapshot = {
        "version": row["version"] if row else 1,
        "weights": cfg["weights"],
        "thresholds": cfg["thresholds"],
        "bear_factor": cfg["bear_factor"],
        "max_positions": cfg["max_positions"],
        "min_strength": cfg["min_strength"],
        "max_single_amount": cfg["max_single_amount"],
        "stop_loss_pct": cfg["stop_loss_pct"],
        "take_profit_pct": cfg["take_profit_pct"],
        "trailing_stop_pct": cfg.get("trailing_stop_pct", 3),
        "risk_per_trade_pct": cfg.get("risk_per_trade_pct", 2),
        "max_hold_days": cfg["max_hold_days"],
        "circuit_breaker_pct": cfg.get("circuit_breaker_pct", -15),
        "caution_drawdown_pct": cfg.get("caution_drawdown_pct", -7),
        "caution_factor": cfg.get("caution_factor", 0.6),
    }
    return json.dumps(snapshot, ensure_ascii=False)


# 初始化
_init_table()

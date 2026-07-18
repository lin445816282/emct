"""策略配置核心 — 持久化存储 + 内存缓存"""
import json
from analyzer import WEIGHTS, SIGNAL_THRESHOLDS
from database import get_db

DEFAULTS = {
    "weights": {"ma_trend": 0.18, "macd": 0.18, "rsi": 0.14, "bollinger": 0.17, "volume": 0.17, "momentum": 0.16},
    "thresholds": {"strong_buy": 28, "buy": 10, "sell": -10, "strong_sell": -28},
    "bear_factor": 0.5,
    "max_positions": 8,
    "min_strength": 10,
    "max_single_amount": 5000,
    "stop_loss_pct": -8,
    "take_profit_pct": 15,
    "max_hold_days": 10,
}

# 内存缓存
_cache: dict | None = None
_db_ready: bool = False


def _ensure_db():
    """确保 strategy_config 表和初始数据存在"""
    global _db_ready
    if _db_ready:
        return
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS strategy_config (
            id INTEGER PRIMARY KEY CHECK(id=1),
            config_json TEXT NOT NULL DEFAULT '{}',
            version INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    row = db.execute("SELECT id FROM strategy_config WHERE id=1").fetchone()
    if not row:
        db.execute("INSERT INTO strategy_config (id, config_json, version) VALUES (1,?,1)",
                   (json.dumps(DEFAULTS),))
    db.commit()
    db.close()
    _db_ready = True


def get_config() -> dict:
    """获取完整配置（DB优先，fallback 默认）"""
    global _cache
    if _cache is not None:
        return dict(_cache)

    _ensure_db()
    db = get_db()
    row = db.execute("SELECT config_json FROM strategy_config WHERE id=1").fetchone()
    db.close()
    if row and row["config_json"]:
        try:
            cfg = json.loads(row["config_json"])
            _cache = cfg
            return dict(cfg)
        except json.JSONDecodeError:
            pass

    _cache = dict(DEFAULTS)
    return dict(DEFAULTS)


def save_config(data: dict) -> dict:
    """保存配置到DB + 内存 + 同步 analyzer 全局变量"""
    global _cache
    _ensure_db()

    current = get_config()
    merged = _deep_merge(current, data)

    # 同步权重到 analyzer
    if "weights" in merged and isinstance(merged["weights"], dict):
        w = merged["weights"]
        for k in WEIGHTS:
            if k in w and isinstance(w[k], (int, float)):
                WEIGHTS[k] = w[k]

    # 同步阈值到 analyzer
    if "thresholds" in merged and isinstance(merged["thresholds"], dict):
        for k in SIGNAL_THRESHOLDS:
            if k in merged["thresholds"]:
                try:
                    SIGNAL_THRESHOLDS[k] = int(merged["thresholds"][k])
                except (ValueError, TypeError):
                    pass

    # 存 DB
    json_str = json.dumps(merged, ensure_ascii=False)
    db = get_db()
    db.execute(
        "UPDATE strategy_config SET config_json=?, version=version+1, updated_at=datetime('now','localtime') WHERE id=1",
        (json_str,)
    )
    db.commit()
    db.close()

    _cache = merged
    return dict(merged)


def reset_config() -> dict:
    """恢复默认"""
    global _cache
    _cache = dict(DEFAULTS)
    
    # 同步到 analyzer
    for k, v in DEFAULTS["weights"].items():
        if k in WEIGHTS:
            WEIGHTS[k] = v
    for k, v in DEFAULTS["thresholds"].items():
        if k in SIGNAL_THRESHOLDS:
            SIGNAL_THRESHOLDS[k] = v

    _ensure_db()
    db = get_db()
    db.execute(
        "UPDATE strategy_config SET config_json=?, version=version+1, updated_at=datetime('now','localtime') WHERE id=1",
        (json.dumps(DEFAULTS, ensure_ascii=False),)
    )
    db.commit()
    db.close()

    return dict(DEFAULTS)


def _deep_merge(base: dict, override: dict) -> dict:
    """深层合并"""
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result

"""策略配置 API — 可视化配置 + AI 优化"""
import json
from fastapi import APIRouter
from strategy_config import get_config, save_config, reset_config

router = APIRouter(prefix="/strategy", tags=["strategy"])


@router.get("/config")
def api_get_config():
    """获取完整策略配置"""
    c = get_config()
    # 返回时附带版本号和默认值对比信息
    return {
        "data": c,
        "version": _get_version(),
        "defaults": _get_defaults_for_frontend(),
    }


@router.put("/config")
def api_update_config(data: dict):
    """更新策略配置（部分更新即可，missing keys 保持原值）"""
    current = get_config()
    merged = _deep_merge(current, data)
    saved = save_config(merged)
    return {"ok": True, "data": saved, "version": _get_version()}


@router.post("/reset")
def api_reset_config():
    """恢复默认配置"""
    saved = reset_config()
    return {"ok": True, "data": saved, "message": "已恢复默认配置"}


@router.post("/optimize")
def api_optimize_weights(n_iter: int = 30, max_stocks: int = 15):
    """AI 优化因子权重（基于历史信号-收益相关性）"""
    try:
        from weight_optimizer import optimize as run_optimize
        result = run_optimize(n_iter=n_iter, max_stocks=max_stocks)
        
        if result.get("ok") and result.get("best_weights"):
            # 仅更新 weights 部分，不动其他配置
            current = get_config()
            new_weights = result["best_weights"]
            # 归一化
            total = sum(new_weights.values())
            if total > 0:
                new_weights = {k: round(v / total, 4) for k, v in new_weights.items()}
            current["weights"] = new_weights
            saved = save_config(current)
            return {
                "ok": True,
                "weights": saved["weights"],
                "score": result.get("best_score", 0),
                "message": f"AI 已优化权重（评分: {result.get('best_score', 0):.3f}），已保存",
            }
        return {"ok": False, "error": result.get("error", "优化无结果，数据不足")}
    except ImportError:
        return {"ok": False, "error": "weight_optimizer 模块未就绪"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _get_version() -> int:
    from database import get_db
    db = get_db()
    row = db.execute("SELECT version FROM strategy_config WHERE id=1").fetchone()
    db.close()
    return row["version"] if row else 1


def _get_defaults_for_frontend() -> dict:
    """前端可视化用的默认值描述"""
    from strategy_config import DEFAULTS
    return {
        "weight_range": {"min": 0.05, "max": 0.40, "step": 0.01},
        "threshold_range": {"min": -50, "max": 50, "step": 1},
        "bear_factor_range": {"min": 0.1, "max": 1.0, "step": 0.05},
        "max_positions_range": {"min": 1, "max": 15, "step": 1},
    }


def _deep_merge(base: dict, override: dict) -> dict:
    """深层合并：override 中的 dict 值递归合并，其余直接覆盖"""
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result

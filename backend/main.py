"""EMCT — 东方财富CDP量化交易系统 主入口"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from database import init_db, get_db
from config import DEFAULT_POOL
import os

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    db = get_db()
    for s in DEFAULT_POOL:
        db.execute(
            "INSERT OR IGNORE INTO stock_pool (code, name, market, sector) VALUES (?,?,?,?)",
            (s["code"], s["name"], s["market"], s["sector"])
        )
    db.commit()
    db.close()
    print("✅ EMCT 启动完成 — 股票池就绪")
    yield

app = FastAPI(title="EMCT量化交易系统", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── 路由：双前缀（本地 + nginx/CF路径） ──
from routers import stock_pool, positions, signals, orders, data, review_router, sim_router, strategy
for prefix in ["/api", "/emct/api"]:
    app.include_router(stock_pool.router, prefix=prefix)
    app.include_router(positions.router, prefix=prefix)
    app.include_router(signals.router, prefix=prefix)
    app.include_router(orders.router, prefix=prefix)
    app.include_router(data.router, prefix=prefix)
    app.include_router(review_router.router, prefix=prefix)
    app.include_router(sim_router.router, prefix=prefix)
    app.include_router(strategy.router, prefix=prefix)

@app.get("/api/health")
@app.get("/emct/api/health")
def health():
    return {"status": "ok", "service": "emct-trading"}

# ── 前端SPA ──
if os.path.exists(FRONTEND_DIR):
    @app.get("/")
    async def spa_index():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

    @app.get("/emct/{rest:path}")
    async def spa_emct(rest: str):
        return serve_spa(rest)

    @app.get("/{rest:path}")
    async def spa_root(rest: str):
        return serve_spa(rest)

def serve_spa(path: str):
    fp = os.path.join(FRONTEND_DIR, path)
    if path and os.path.isfile(fp):
        resp = FileResponse(fp)
        # JS/CSS 有hash可永久缓存，HTML不缓存
        if fp.endswith('.html'):
            resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        else:
            resp.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
        return resp
    resp = FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8017, reload=True)

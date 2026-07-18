"""EMCT — 数据库模块"""
import sqlite3, os
from config import DB_PATH

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    db = get_db()
    db.executescript("""
        -- 股票池
        CREATE TABLE IF NOT EXISTS stock_pool (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            market TEXT NOT NULL,
            sector TEXT DEFAULT '',
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        -- 日线数据缓存
        CREATE TABLE IF NOT EXISTS daily_kline (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            date TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL,
            volume REAL, amount REAL,
            UNIQUE(code, date)
        );

        -- 信号记录
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            date TEXT NOT NULL,
            signal_type TEXT NOT NULL DEFAULT 'hold',
            strength REAL DEFAULT 0,
            score TEXT DEFAULT '{}',
            reason TEXT DEFAULT '',
            price_ref REAL,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        -- 订单记录
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id INTEGER,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            direction TEXT NOT NULL,
            price REAL,
            volume INTEGER,
            amount REAL,
            order_status TEXT DEFAULT 'created',
            order_ref TEXT DEFAULT '',
            screenshot_path TEXT DEFAULT '',
            error_msg TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );

        -- 持仓记录
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            volume INTEGER NOT NULL,
            avg_cost REAL NOT NULL,
            current_price REAL DEFAULT 0,
            market_value REAL DEFAULT 0,
            profit_loss REAL DEFAULT 0,
            profit_loss_pct REAL DEFAULT 0,
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );

        -- 交易复盘日志
        CREATE TABLE IF NOT EXISTS trade_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            code TEXT NOT NULL,
            action TEXT NOT NULL DEFAULT 'open',
            price REAL,
            volume INTEGER,
            pnl REAL DEFAULT 0,
            pnl_pct REAL DEFAULT 0,
            hold_days INTEGER DEFAULT 0,
            review TEXT DEFAULT '',
            tags TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        -- CDP会话
        CREATE TABLE IF NOT EXISTS cdp_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            status TEXT DEFAULT 'inactive',
            ws_endpoint TEXT DEFAULT '',
            login_at TEXT DEFAULT '',
            expire_at TEXT DEFAULT '',
            cookies TEXT DEFAULT ''
        );

        -- 模拟交易账户
        CREATE TABLE IF NOT EXISTS sim_account (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            initial_cash REAL NOT NULL DEFAULT 1000000,
            cash REAL NOT NULL DEFAULT 1000000,
            total_value REAL DEFAULT 0,
            total_pnl REAL DEFAULT 0,
            total_pnl_pct REAL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );
    """)

    # ── 迁移：已有表加字段 ──
    _migrate(db)

    db.commit()
    db.close()


def _migrate(db):
    """增量迁移，安全添加字段和表"""
    # sim_mode for orders
    try: db.execute("ALTER TABLE orders ADD COLUMN sim_mode INTEGER DEFAULT 0")
    except: pass
    # sim_mode for trade_log
    try: db.execute("ALTER TABLE trade_log ADD COLUMN sim_mode INTEGER DEFAULT 0")
    except: pass
    # sim_mode for positions
    try: db.execute("ALTER TABLE positions ADD COLUMN sim_mode INTEGER DEFAULT 0")
    except: pass
    # buy_date for positions (持仓开仓日期，用于计算持有天数)
    try: db.execute("ALTER TABLE positions ADD COLUMN buy_date TEXT DEFAULT ''")
    except: pass
    # 确保 sim_account 有种子数据
    row = db.execute("SELECT COUNT(*) as c FROM sim_account").fetchone()
    if row and row["c"] == 0:
        db.execute("INSERT INTO sim_account (initial_cash, cash) VALUES (1000000, 1000000)")
    db.commit()

if __name__ == "__main__":
    init_db()
    print("✅ 数据库初始化完成")

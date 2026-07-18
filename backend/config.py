"""EMCT — 东方财富CDP量化交易系统 配置"""
import os

# ── 数据库 ──
DB_PATH = "backend/data/emct.db"

# ── 风控参数 ──
MAX_SINGLE_AMOUNT = 50000       # 单笔最大5万
MAX_DAILY_AMOUNT = 200000       # 单日最大20万
MAX_POSITION_PCT = 0.3          # 单票最大30%仓位
STOP_LOSS_PCT = -0.05           # 止损线 -5%

# ── LLM ──
LLM_PROVIDER = "deepseek"
LLM_MODEL = "deepseek-chat"
LLM_TEMPERATURE = 0.3
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# ── 信号阈值 ──
SIGNAL_THRESHOLD_STRONG = 85    # 强烈买入（仅通知，必须人工）
SIGNAL_THRESHOLD_BUY = 70       # 买入信号
SIGNAL_THRESHOLD_WATCH = 60     # 关注

# ── 定时任务 ──
ANALYSIS_TIME = "15:30"         # 盘后分析时间
MORNING_PREP_TIME = "09:15"     # 盘前准备

# ── CDP ──
CDP_URL = "http://localhost:9222"
EASTMONEY_TRADE_URL = "https://jywg.eastmoney.com/"

# ── 股票池（默认关注） ──
DEFAULT_POOL = [
    {"code": "600519", "name": "贵州茅台", "market": "SH", "sector": "白酒"},
    {"code": "000858", "name": "五粮液", "market": "SZ", "sector": "白酒"},
    {"code": "300750", "name": "宁德时代", "market": "SZ", "sector": "新能源"},
    {"code": "002594", "name": "比亚迪", "market": "SZ", "sector": "新能源"},
    {"code": "601318", "name": "中国平安", "market": "SH", "sector": "金融"},
    {"code": "600036", "name": "招商银行", "market": "SH", "sector": "金融"},
    {"code": "000001", "name": "平安银行", "market": "SZ", "sector": "金融"},
    {"code": "600276", "name": "恒瑞医药", "market": "SH", "sector": "医药"},
]

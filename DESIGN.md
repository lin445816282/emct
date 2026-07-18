# 东方财富CDP量化交易系统 — AI开发设计文档

> **项目代号**: EastMoneyCDP Trader (简称 EMCT)  
> **目标**: Python全栈，从数据采集→分析→信号→下单→复盘，全链路AI驱动  
> **受众**: AI开发者（本文件为AI开发上下文）  
> **端口**: 8017  
> **部署**: ct256.cn/emct/

---

## 一、项目定位

小林现有 stock-aggregator（信息聚合看板），本项目不重复造轮子，聚焦 **交易执行端**：

```
stock-aggregator (看板/盯盘) → EMCT (信号→下单) → 东方财富Web (执行)
```

**核心原则**：
- 半自动化：AI分析+信号推送 → 小林确认 → 自动执行
- 只做A股（沪深），不做期货/期权
- 个人散户规模，不需要低延迟
- 所有订单可追踪、可复盘

---

## 二、系统架构

```
┌─────────────────────────────────────────────────────┐
│                    EMCT 交易系统                       │
│                                                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │ 数据采集  │→│ 分析引擎  │→│ 信号生成  │           │
│  │ AKShare  │  │ TA-Lib   │  │ 多因子    │           │
│  └──────────┘  │ Pandas   │  │ 评分卡    │           │
│                 └──────────┘  └────┬─────┘           │
│                                    ↓                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │ 复盘模块  │←│ 持仓管理  │←│ 下单执行  │           │
│  │ P&L统计  │  │ 风险控制  │  │ CDP自动化 │           │
│  └──────────┘  └──────────┘  └──────────┘           │
│                                                       │
│  ┌────────────────────────────────────────┐          │
│  │        Vue3 管理面板 (port 8017)        │          │
│  │  信号列表 | 持仓监控 | 交易日志 | 复盘   │          │
│  └────────────────────────────────────────┘          │
└─────────────────────────────────────────────────────┘
```

---

## 三、技术选型

| 层次 | 技术 | 理由 |
|------|------|------|
| 数据源 | AKShare | 免费、全量A股数据、支持资金流向 |
| 指标计算 | TA-Lib + pandas | 经典技术指标库 |
| LLM分析 | DeepSeek API | 已在用、便宜、支持中文金融分析 |
| 浏览器自动化 | Playwright CDP | Node.js直连Windows Edge，同淘宝发品套路 |
| 后端 | Python FastAPI | 统一技术栈，8003已验证 |
| 前端 | Vue3 + Vant4 | 统一技术栈，移动端优先 |
| 数据库 | SQLite | 轻量、够用 |
| 调度 | APScheduler | 定时任务（收盘信号、开盘前准备） |

---

## 四、数据库设计

### 4.1 表结构

```sql
-- 股票池
CREATE TABLE stock_pool (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,       -- '600519'
    name TEXT NOT NULL,              -- '贵州茅台'
    market TEXT NOT NULL,            -- 'SH' / 'SZ'
    sector TEXT DEFAULT '',          -- '白酒'
    active INTEGER DEFAULT 1,        -- 是否启用
    created_at TEXT DEFAULT (datetime('now','localtime'))
);

-- 日线数据缓存
CREATE TABLE daily_kline (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL,
    volume REAL, amount REAL,
    UNIQUE(code, date)
);

-- 信号记录（分析产出）
CREATE TABLE signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    date TEXT NOT NULL,
    signal_type TEXT NOT NULL,       -- 'buy' / 'sell' / 'hold' / 'alert'
    strength REAL DEFAULT 0,         -- 信号强度 0-100
    score JSON,                      -- 多因子评分详情
    reason TEXT,                     -- AI分析理由
    price_ref REAL,                  -- 参考价
    status TEXT DEFAULT 'pending',   -- pending/confirmed/executed/expired
    created_at TEXT DEFAULT (datetime('now','localtime'))
);

-- 订单记录
CREATE TABLE orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    direction TEXT NOT NULL,          -- 'buy' / 'sell'
    price REAL,                       -- 成交价
    volume INTEGER,                   -- 股数（100的倍数）
    amount REAL,                      -- 金额
    order_status TEXT DEFAULT 'created', 
    -- created/submitted/filled/cancelled/error
    order_ref TEXT,                   -- 东方财富订单号
    screenshot_path TEXT,             -- 下单截图
    error_msg TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (signal_id) REFERENCES signals(id)
);

-- 持仓记录
CREATE TABLE positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    volume INTEGER NOT NULL,          -- 持仓股数
    avg_cost REAL NOT NULL,           -- 平均成本
    current_price REAL,               -- 最新价
    market_value REAL,                -- 市值
    profit_loss REAL,                 -- 浮动盈亏
    profit_loss_pct REAL,             -- 盈亏比例
    updated_at TEXT DEFAULT (datetime('now','localtime'))
);

-- 交易日志（复盘用）
CREATE TABLE trade_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER,
    code TEXT NOT NULL,
    action TEXT NOT NULL,             -- 'open' / 'close' / 'add' / 'reduce'
    price REAL,
    volume INTEGER,
    pnl REAL,                         -- 本次盈亏
    pnl_pct REAL,
    hold_days INTEGER,                -- 持仓天数
    review TEXT,                      -- AI复盘总结
    tags TEXT,                        -- 标签（追高/抄底/止损...）
    created_at TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (order_id) REFERENCES orders(id)
);

-- CDP会话管理
CREATE TABLE cdp_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT DEFAULT 'inactive',    -- active/inactive/error
    ws_endpoint TEXT,                  -- CDP WebSocket地址
    login_at TEXT,
    expire_at TEXT,
    cookies TEXT
);
```

### 4.2 数据流

```
AKShare日线 → daily_kline (缓存7天)
        ↓
  分析引擎(每天15:30跑) → signals表
        ↓
  小林手机确认 → signals.status='confirmed'
        ↓
  CDP执行 → orders表 → positions表
        ↓
  平仓时 → trade_log (复盘)
```

---

## 五、模块详细设计

### 5.1 数据采集模块 `data_collector.py`

```python
# 功能清单
class DataCollector:
    def sync_stock_pool()        # 从配置文件同步股票池
    def fetch_daily_kline(code)  # AKShare获取日线 → 写入daily_kline
    def fetch_realtime_quote()   # 实时行情（东方财富WebSocket）
    def fetch_money_flow(code)   # 资金流向（主力/散户净流入）
    def fetch_market_index()     # 大盘指数（上证/深证/创业板）
    def warm_up_cache(days=60)   # 初次启动预热60天数据
```

**AKShare 关键API**:
```python
import akshare as ak
# 日线
df = ak.stock_zh_a_hist(symbol="600519", period="daily", adjust="qfq")
# 资金流向
df = ak.stock_individual_fund_flow(stock="600519", market="sh")
# 龙虎榜
df = ak.stock_sina_lhb_detail_daily(trade_date="20260715")
```

**定时任务**:
- 每交易日 15:30 → 拉取当日日线
- 每交易日 09:15 → 拉取集合竞价数据
- 实时 → 东方财富WebSocket推送行情

---

### 5.2 分析引擎 `analysis_engine.py`

**多因子评分模型**（总分100）：

| 因子类别 | 因子 | 权重 | 数据来源 |
|----------|------|------|----------|
| 趋势 | MA多头排列 | 15 | TA-Lib |
| 趋势 | MACD金叉 | 10 | TA-Lib |
| 动量 | RSI(14) | 10 | TA-Lib |
| 量价 | 量比 | 10 | 实时数据 |
| 资金 | 主力净流入 | 15 | 东方财富 |
| 资金 | 北向资金 | 10 | AKShare |
| 大盘 | 市场情绪 | 10 | 涨跌家数比 |
| 风控 | 波动率 | 10 | 布林带宽度 |
| AI | LLM综合研判 | 10 | DeepSeek |

```python
class AnalysisEngine:
    def calc_technical_indicators(code)  # 计算全部技术指标
    def calc_fund_flow_score(code)       # 资金面评分
    def calc_market_sentiment()          # 市场情绪
    def llm_analysis(code, indicators)   # DeepSeek综合分析
    def generate_score_card(code)        # 输出评分卡JSON
    def rank_signals()                   # 全市场排序
```

**LLM分析Prompt**:
```
你是A股交易分析师。基于以下数据对{code} {name}进行研判：

技术面：MA5={ma5}, MA20={ma20}, MACD={macd}, RSI={rsi}
资金面：主力净流入={main_inflow}万，北向={north_flow}万
大盘：上证涨跌比={market_ratio}

请输出：
1. 趋势判断：上涨/震荡/下跌
2. 操作建议：买入/持有/卖出/观望
3. 支撑位/压力位
4. 风险提示（1句话）

JSON格式回复。
```

---

### 5.3 信号生成 `signal_generator.py`

```python
class SignalGenerator:
    def run_daily_scan()          # 盘后全市场扫描（15:30）
    def filter_by_score(min=60)   # 评分阈值过滤
    def deduplicate_signals()     # 去重（同股票连续信号）
    def push_to_mobile(signals)   # 推送到微信/企业微信
    def confirm_signal(id)        # 小林确认后标记
```

**信号优先级**:
- 🔴 强烈买入 (≥85分) — 忽略，必须人工
- 🟠 买入 (70-84分) — 推送，可确认自动下单
- 🟡 关注 (60-69分) — 仅通知
- ⚪ 观望 (<60分) — 不推送

---

### 5.4 CDP下单执行 `trade_executor.py`

**这是核心难点模块，参考淘宝发品CDP经验。**

#### 5.4.1 东方财富Web端结构

```
登录页: https://jywg.eastmoney.com/
├── 账号密码登录 → 短信验证码（卡点1）
├── 登录态保持（cookie有效期约2小时）
└── 交易页面（需要登录态）
    ├── 买入页
    │   ├── 输入框: 股票代码
    │   ├── 显示: 股票名称、最新价
    │   ├── 输入框: 买入价格
    │   ├── 输入框: 买入数量
    │   ├── 按钮: 买入（需要二次确认）
    │   └── 弹窗: 确认下单（卡点2）
    └── 卖出页（结构类似）
```

#### 5.4.2 CDP操作流程

```python
class TradeExecutor:
    def __init__(self):
        self.browser = None       # Playwright browser
        self.page = None          # 交易页面
        self.logged_in = False
    
    # 步骤1: 启动CDP连接
    async def connect_browser():
        """连接Windows本地Edge浏览器（已有登录态）"""
        browser = await playwright.chromium.connect_over_cdp(
            "http://localhost:9222"
        )
    
    # 步骤2: 检查登录态
    async def check_login():
        """导航到东方财富交易页，检查是否已登录"""
        await page.goto("https://jywg.eastmoney.com/")
        # 检测页面是否跳转到登录页
        # 如果已登录，直接进入交易页
    
    # 步骤3: 如需登录，走登录流程
    async def login(account, password):
        """CDP自动化登录（含短信验证码处理）"""
        # 填账号密码
        # 触发短信验证码
        # 等待小林输入验证码（通过前端界面）
        # 提交登录
    
    # 步骤4: 下单
    async def place_order(code, direction, price, volume):
        """
        完整下单流程：
        1. 导航到买入/卖出页
        2. 输入股票代码 → 等待页面刷新股票信息
        3. 校验股票名称是否正确
        4. 输入价格
        5. 输入数量（100的整数倍）
        6. 截图保存（order confirmation）
        7. 点击"买入/卖出"按钮
        8. 处理确认弹窗：再次截图 + 点击确认
        9. 等待结果：成功/失败
        10. 截图保存结果页
        11. 写入orders表
        """
    
    # 步骤5: 撤单
    async def cancel_order(order_ref):
        """撤销未成交订单"""
    
    # 步骤6: 查持仓
    async def fetch_positions():
        """抓取当前持仓 → 更新positions表"""
```

#### 5.4.3 CDP关键选择器（待实战验证）

```javascript
// 东方财富Web交易端 — 预期DOM结构（以实际为准）
const SELECTORS = {
    // 登录页
    account_input: '#txtLoginAccount',
    password_input: '#txtLoginPwd',
    login_btn: '#btnLogin',
    sms_input: '#txtSmsCode',
    sms_btn: '#btnGetSms',
    
    // 买入页
    stock_code_input: '#stockCode',
    stock_name_display: '.stock-name',
    price_input: '#price',
    volume_input: '#amount',
    buy_btn: '#btnBuy',
    
    // 确认弹窗
    confirm_dialog: '.confirm-dialog',
    confirm_btn: '.confirm-btn',
    cancel_btn: '.cancel-btn',
    
    // 结果
    result_msg: '.result-msg',
    
    // 持仓表格
    position_table: '#positionTable',
    position_rows: '#positionTable tr',
}
```

#### 5.4.4 安全机制

```python
class TradeSafety:
    MAX_SINGLE_AMOUNT = 50000      # 单笔最大5万
    MAX_DAILY_AMOUNT = 200000      # 单日最大20万
    MAX_POSITION_PCT = 0.3         # 单票最大30%仓位
    STOP_LOSS_PCT = -0.05          # 止损线 -5%
    
    def check_order(order):
        """下单前校验"""
    def check_position_limit(code):
        """仓位上限检查"""
    def check_daily_limit():
        """日交易额上限"""
```

---

### 5.5 复盘模块 `trade_review.py`

```python
class TradeReview:
    def calc_trade_pnl(order_id)        # 计算单笔盈亏
    def generate_daily_report()         # 每日交易报告
    def generate_weekly_report()        # 周报
    def llm_review(trade_log_id)        # DeepSeek复盘分析
    def tag_trade(trade_log_id, tags)   # 打标签分类
    def win_rate_stats(period)          # 胜率统计
    def max_drawdown(period)            # 最大回撤
    def sharpe_ratio(period)            # 夏普比率
```

**复盘Prompt**:
```
复盘交易：
股票：{name}({code})
方向：{direction}  |  买入价：{entry}  |  卖出价：{exit}
盈亏：{pnl}元 ({pnl_pct}%)  |  持仓{days}天

买入时技术面：{entry_indicators}
卖出时技术面：{exit_indicators}

请分析：
1. 这笔交易决策是否正确？
2. 买入和卖出时机是否合适？
3. 教训总结（1句话）
```

---

## 六、前端界面设计

### 6.1 页面结构

```
EMCT 交易系统 (Vue3 + Vant4, 移动端)
├── Tab1: 信号
│   ├── 信号列表卡片（评分/理由/操作按钮）
│   ├── 点击「确认下单」→ 填入预设价格/数量
│   └── 点击「忽略」→ 标记expired
├── Tab2: 持仓
│   ├── 持仓汇总（总市值/总盈亏/仓位比例）
│   ├── 持仓列表（代码/成本/现价/盈亏）
│   └── 卖出按钮 → 弹出卖出确认
├── Tab3: 订单
│   ├── 今日订单列表
│   ├── 历史订单搜索
│   └── 状态筛选（待确认/已成交/已撤销）
├── Tab4: 复盘
│   ├── 盈亏日历
│   ├── 胜率曲线
│   └── AI周报复盘
└── 底部: CDP状态指示灯（🟢已连接 / 🔴断开）
```

### 6.2 管理后台 `/emct/admin/`

```
密码：同 purchase/admin 独立管理
功能：股票池管理、CDP配置、手动下单、日志查看
```

---

## 七、开发路线图

### Phase 1: 数据基础（1-2天）
- [ ] 项目初始化（FastAPI + Vue3 + SQLite, port 8017）
- [ ] 数据库建表 + AKShare数据采集
- [ ] 股票池管理界面
- [ ] 日线缓存 + 预热脚本

### Phase 2: 分析引擎（2-3天）
- [ ] TA-Lib技术指标计算
- [ ] 多因子评分模型
- [ ] DeepSeek LLM分析集成
- [ ] 信号生成 + 推送

### Phase 3: CDP交易（3-5天，核心难点）
- [ ] Playwright CDP连接东方财富
- [ ] 登录流程（含验证码交互）
- [ ] 买入/卖出自动化
- [ ] 持仓抓取
- [ ] 安全校验层
- [ ] 前端CDP控制面板

### Phase 4: 复盘系统（1-2天）
- [ ] 交易日志 + P&L计算
- [ ] AI复盘分析
- [ ] 图表统计（胜率/回撤/夏普）
- [ ] 周报生成

### Phase 5: 部署上线（1天）
- [ ] nginx反向代理 `/emct/`
- [ ] Cloudflare Tunnel路由
- [ ] APScheduler定时任务配置

---

## 八、关键风险与对策

| 风险 | 影响 | 对策 |
|------|------|------|
| 东方财富改版DOM | CDP选择器失效 | 抽象选择器配置层，加自动截图诊断 |
| 短信验证码 | 阻塞自动登录 | 前端弹窗等待人工输入，登录态维持 |
| 交易确认弹窗 | 无法完全自动化 | 第二步确认由小林手动点击 |
| 行情延迟 | 下单价格偏差 | 限价单为主，市价单谨慎 |
| CDP断连 | 订单丢失 | 断连重试+订单状态轮询 |

---

## 九、文件结构

```
emct/
├── backend/
│   ├── main.py              # FastAPI入口
│   ├── database.py          # SQLite ORM
│   ├── config.py            # 配置（API key、风控参数）
│   ├── data_collector.py    # AKShare数据采集
│   ├── analysis_engine.py   # 技术分析 + 多因子
│   ├── signal_generator.py  # 信号生成
│   ├── trade_executor.py    # CDP下单
│   ├── trade_safety.py      # 风控校验
│   ├── trade_review.py      # 复盘分析
│   ├── llm_client.py        # DeepSeek调用封装
│   ├── scheduler.py         # 定时任务
│   ├── admin.py             # 管理后台
│   └── data/                # SQLite数据
├── cdp/
│   ├── playwright_bridge.js # Playwright CDP桥接脚本
│   ├── selectors.yaml       # DOM选择器配置
│   └── eastmoney_login.js   # 东方财富登录专用脚本
├── frontend/
│   ├── src/
│   │   ├── views/
│   │   │   ├── Signals.vue      # 信号页
│   │   │   ├── Positions.vue    # 持仓页
│   │   │   ├── Orders.vue       # 订单页
│   │   │   ├── Review.vue       # 复盘页
│   │   │   └── Admin.vue        # 管理后台
│   │   ├── components/
│   │   │   ├── SignalCard.vue   # 信号卡片
│   │   │   ├── PositionCard.vue # 持仓卡片
│   │   │   ├── OrderConfirm.vue # 下单确认弹窗
│   │   │   └── CdpStatus.vue    # CDP状态指示器
│   │   └── stores/
│   │       └── trading.js       # Pinia交易状态
│   └── package.json
└── README.md
```

---

## 十、AI开发指令

> 以下为AI开发者（Claude/DeepSeek等）的上下文片段，可直接嵌入prompt使用。

```
你是小林的技术伙伴。你正在开发「东方财富CDP量化交易系统」(EMCT)。

项目路径: ~/projects/emct/
后端端口: 8017 (uvicorn main:app --port 8017)
前端端口: 5173 (vite dev, 仅本地)
部署: nginx /emct/ → 8017

技术栈: Python3.12 + FastAPI + SQLite + AKShare + TA-Lib + DeepSeek API
前端: Vue3 + Vant4 (移动端)
CDP: Playwright (Node.js) 连接 Windows Edge

核心原则:
1. 半自动化 — 信号推送人工确认后才执行
2. 每次下单截图保存
3. 所有操作有日志可追溯
4. CDP选择器独立配置，方便适配页面变化
5. 移动端优先 — 小林主要在手机上看

不要做的事:
- 不要自行下单，跳过确认步骤
- 不要修改 stock-aggregator 的数据库
- 不要添加期货/期权等其他市场
```

---

## 十一、快速启动命令

```bash
# 初始化
cd ~/projects/emct
python -m venv venv && source venv/bin/activate
pip install fastapi uvicorn akshare TA-Lib sqlite3 pandas
pip install playwright

# 启动后端
uvicorn backend.main:app --host 0.0.0.0 --port 8017 --reload

# 前端开发
cd frontend && npm run dev

# 数据预热
python backend/data_collector.py --warmup 60

# 手动运行分析
python backend/signal_generator.py --run

# CDP连接测试
node cdp/playwright_bridge.js --test
```

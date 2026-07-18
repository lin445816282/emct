<template>
  <div class="sim-page">
    <!-- 实时账户卡片 -->
    <div v-if="account" class="account-card">
      <div class="acct-row">
        <span class="acct-label">💰 模拟账户</span>
        <van-tag type="warning" size="small">实时</van-tag>
      </div>
      <div class="acct-stats">
        <div class="acct-stat">
          <div class="acct-val">¥{{ fmt(account.total_value) }}</div>
          <div class="acct-lbl">总资产</div>
        </div>
        <div class="acct-stat">
          <div class="acct-val">¥{{ fmt(account.cash) }}</div>
          <div class="acct-lbl">可用现金</div>
        </div>
        <div class="acct-stat">
          <div class="acct-val" :class="account.total_pnl >= 0 ? 'up' : 'down'">
            {{ account.total_pnl >= 0 ? '+' : '' }}¥{{ fmt(account.total_pnl) }}
          </div>
          <div class="acct-lbl">累计盈亏</div>
        </div>
      </div>
    </div>

    <!-- 当前持仓 -->
    <div v-if="positions.length" class="section">
      <div class="section-title">📦 当前持仓 ({{ positions.length }})</div>
      <div v-for="p in positions" :key="p.code" class="pos-item">
        <div class="pos-head">
          <span class="pos-name">{{ p.name }}</span>
          <span class="pos-code">{{ p.code }}</span>
        </div>
        <div class="pos-body">
          <span>{{ p.volume }}股 @¥{{ fmt(p.avg_cost) }} → ¥{{ fmt(p.current_price) }}</span>
          <span :class="p.profit_loss >= 0 ? 'up' : 'down'">
            市值 ¥{{ fmt(p.market_value) }}
            <span v-if="p.profit_loss"> ({{ p.profit_loss_pct }}%)</span>
          </span>
        </div>
      </div>
    </div>

    <!-- 最近成交 -->
    <div v-if="recentOrders.length" class="section">
      <div class="section-title">📋 最近成交 ({{ recentOrders.length }})</div>
      <div v-for="o in recentOrders" :key="o.id" class="order-item">
        <van-tag :type="o.direction === 'buy' ? 'danger' : 'success'" size="mini">{{ o.direction === 'buy' ? '买' : '卖' }}</van-tag>
        <span class="order-name">{{ o.name }}</span>
        <span class="order-info">{{ o.volume }}股 ¥{{ fmt(o.amount) }}</span>
        <van-tag type="success" size="mini" v-if="o.order_status==='filled'">✓</van-tag>
      </div>
    </div>

    <div class="divider">━━ 回测 ━━</div>
    <div class="actions">
      <van-button type="primary" size="small" :loading="btLoading" @click="runBacktest">
        ▶ 运行回测
      </van-button>
      <van-button plain size="small" :loading="syncing" @click="syncBenchmark">
        📥 同步基准
      </van-button>
    </div>

    <!-- 绩效卡片 -->
    <div v-if="summary" class="stats">
      <div class="stat-card">
        <div class="stat-val" :class="summary.total_return >= 0 ? 'up' : 'down'">
          {{ summary.total_return >= 0 ? '+' : '' }}{{ summary.total_return }}%
        </div>
        <div class="stat-label">总收益</div>
      </div>
      <div class="stat-card">
        <div class="stat-val">{{ summary.cagr }}%</div>
        <div class="stat-label">年化</div>
      </div>
      <div class="stat-card">
        <div class="stat-val down-val">{{ summary.max_drawdown }}%</div>
        <div class="stat-label">最大回撤</div>
      </div>
      <div class="stat-card">
        <div class="stat-val">{{ displayBtWinRate }}</div>
        <div class="stat-label">胜率</div>
      </div>
      <div class="stat-card">
        <div class="stat-val">{{ summary.profit_factor }}</div>
        <div class="stat-label">盈亏比</div>
      </div>
      <div class="stat-card">
        <div class="stat-val">{{ summary.total_trades }}</div>
        <div class="stat-label">交易数</div>
      </div>
    </div>

    <!-- 图表区 -->
    <div v-if="equityCurve.length" class="chart-container">
      <div class="chart-title">📈 净值 vs 沪深300</div>
      <div ref="chartRef" class="chart"></div>
      <div class="chart-x-label">{{ chartRange }}</div>
    </div>
    <van-empty v-if="btLoaded && !equityCurve.length" description="运行回测以查看净值曲线" />

    <!-- 交易记录 -->
    <div v-if="trades.length" class="trades-section">
      <div class="section-title">交易记录 ({{ trades.length }})</div>
      <div class="trade-list">
        <div v-for="(t, i) in trades.slice().reverse()" :key="i" class="trade-item">
          <div class="trade-head">
            <span class="trade-name">{{ t.name }}</span>
            <span class="trade-code">{{ t.code }}</span>
            <van-tag :type="t.type === 'buy' ? 'danger' : 'success'" size="mini">
              {{ t.type === 'buy' ? '买入' : '卖出' }}
            </van-tag>
          </div>
          <div class="trade-body">
            <span>{{ t.date }} | ¥{{ t.price }} | {{ t.shares }}股</span>
            <span v-if="t.pnl != null" :class="t.pnl >= 0 ? 'up' : 'down'">
              {{ t.pnl >= 0 ? '+' : '' }}¥{{ fmt(t.pnl) }} ({{ t.pnl_pct }}%)
            </span>
          </div>
          <div v-if="t.reason" class="trade-reason">{{ t.reason }}</div>
        </div>
      </div>
    </div>

    <!-- 回测后端消息 -->
    <div v-if="btMsg && !summary" class="bt-msg">{{ btMsg }}</div>
  </div>
</template>

<script setup>
import { ref, nextTick, watch, onMounted, computed } from 'vue'
import { showToast } from 'vant'
import * as echarts from 'echarts'

const btLoading = ref(false)
const syncing = ref(false)
const btLoaded = ref(false)
const btMsg = ref('')
const summary = ref(null)
const equityCurve = ref([])
const benchmark = ref([])
const trades = ref([])
const chartRange = ref('')
const chartRef = ref(null)
let chart = null

// 胜率显示：数值加%，文本直接显示
const displayBtWinRate = computed(() => {
  const v = summary.value?.win_rate
  if (v == null) return '--'
  return typeof v === 'number' || !isNaN(v) ? v + '%' : v
})

// 实时数据
const account = ref(null)
const positions = ref([])
const recentOrders = ref([])

// 加载实时模拟数据
async function loadLiveData() {
  try {
    const [ar, pr, or_] = await Promise.all([
      fetch('/emct/api/sim/account').then(r => r.json()),
      fetch('/emct/api/sim/positions').then(r => r.json()),
      fetch('/emct/api/sim/orders?limit=10').then(r => r.json()),
    ])
    account.value = ar
    positions.value = pr.rows || []
    recentOrders.value = (or_.rows || []).filter(o => o.order_status === 'filled')
  } catch { /* ignore */ }
}

// 格式化
function fmt(v) {
  if (v == null) return '0'
  return Number(v).toLocaleString('zh-CN', { maximumFractionDigits: 0 })
}

// 归一化：都从 100 起步，转为百分比
function normalizeData(rows, key = 'total') {
  if (!rows.length) return []
  const base = rows[0][key]
  if (!base || base === 0) return []
  return rows.map(r => ({
    date: r.date,
    value: +((r[key] / base) * 100).toFixed(2),
  }))
}

// 运行回测
async function runBacktest() {
  btLoading.value = true
  btMsg.value = ''
  try {
    const r = await fetch('/emct/api/sim/backtest')
    const data = await r.json()
    if (!data.ok) {
      btMsg.value = data.error || '回测失败'
      showToast(btMsg.value)
      return
    }
    summary.value = data.summary
    equityCurve.value = data.equity_curve
    trades.value = data.trades
    btLoaded.value = true
    await loadBenchmark()
    showToast('回测完成')
  } catch (e) {
    btMsg.value = '网络错误'
    showToast('网络错误')
  } finally {
    btLoading.value = false
  }
}

// 加载基准
async function loadBenchmark() {
  try {
    const r = await fetch('/emct/api/sim/benchmark')
    const data = await r.json()
    if (data.rows && data.rows.length) {
      benchmark.value = data.rows
      chartRange.value = data.range || ''
    }
    await nextTick()
    renderChart()
  } catch { /* 忽略 */ }
}

// 同步基准
async function syncBenchmark() {
  syncing.value = true
  try {
    const r = await fetch('/emct/api/sim/sync-benchmark', { method: 'POST' })
    const data = await r.json()
    if (data.ok) {
      showToast(`同步 ${data.inserted} 条`)
      loadBenchmark()
    } else {
      showToast(data.error || '同步失败')
    }
  } catch {
    showToast('网络错误')
  } finally {
    syncing.value = false
  }
}

// 渲染图表
function renderChart() {
  if (!chartRef.value || !equityCurve.value.length) return
  if (chart) chart.dispose()

  chart = echarts.init(chartRef.value)

  // 对齐基准的起点日期
  const eq = normalizeData(equityCurve.value, 'total')
  const bmDates = new Map(benchmark.value.map(r => [r.date, r.close]))
  const bm = []
  const eqStartDate = equityCurve.value[0]?.date
  for (const r of benchmark.value) {
    if (eqStartDate && r.date < eqStartDate) continue
    if (!bm.length && r.close) {
      bm.push({ date: r.date, value: 100 })
    } else if (bm.length && r.close) {
      const baseClose = benchmark.value.find(b => b.date === bm[0].date)?.close || r.close
      bm.push({ date: r.date, value: +((r.close / baseClose) * 100).toFixed(2) })
    }
  }

  const option = {
    tooltip: { trigger: 'axis' },
    legend: {
      data: ['策略净值', '沪深300'],
      top: 0,
      textStyle: { color: '#999', fontSize: 11 },
    },
    grid: { top: 30, left: 12, right: 16, bottom: 8 },
    xAxis: {
      type: 'category',
      data: eq.map(d => d.date),
      axisLabel: { fontSize: 9, color: '#999', interval: Math.max(1, Math.floor(eq.length / 6) - 1) },
      axisLine: { lineStyle: { color: '#333' } },
    },
    yAxis: {
      type: 'value',
      axisLabel: { fontSize: 9, color: '#999', formatter: '{value}' },
      splitLine: { lineStyle: { color: '#222' } },
    },
    series: [
      {
        name: '策略净值',
        type: 'line',
        data: eq.map(d => d.value),
        smooth: true,
        symbol: 'none',
        lineStyle: { color: '#5470c6', width: 2 },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(84,112,198,0.3)' },
            { offset: 1, color: 'rgba(84,112,198,0.02)' },
          ]),
        },
      },
      {
        name: '沪深300',
        type: 'line',
        data: bm.map(d => d.value),
        smooth: true,
        symbol: 'none',
        lineStyle: { color: '#91cc75', width: 1.5, type: 'dashed' },
        itemStyle: { color: '#91cc75' },
      },
    ],
  }

  chart.setOption(option)
  window.addEventListener('resize', () => chart?.resize())
}

// 监听数据变化重绘
watch([equityCurve, benchmark], () => {
  nextTick(() => renderChart())
})

onMounted(loadLiveData)
</script>

<style scoped>
.sim-page { padding: 0 12px 20px; }

/* 实时账户 */
.account-card { background: linear-gradient(135deg, #1a1a2e, #16213e); border-radius: 10px; padding: 14px; margin-bottom: 10px; }
.acct-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.acct-label { font-size: 14px; font-weight: 700; color: #fff; }
.acct-stats { display: flex; gap: 8px; }
.acct-stat { flex: 1; text-align: center; background: rgba(255,255,255,0.05); border-radius: 8px; padding: 8px 4px; }
.acct-val { font-size: 16px; font-weight: 800; color: #fff; }
.acct-lbl { font-size: 10px; color: #888; margin-top: 2px; }

/* 分区 */
.section { margin-bottom: 10px; }
.section-title { font-size: 13px; font-weight: 600; color: #ccc; margin-bottom: 6px; }
.divider { text-align: center; color: #555; font-size: 11px; margin: 16px 0 8px; }

/* 持仓 */
.pos-item { background: linear-gradient(135deg, #1a1a2e, #16213e); border-radius: 8px; padding: 10px 12px; margin-bottom: 4px; }
.pos-head { display: flex; align-items: center; gap: 6px; margin-bottom: 3px; }
.pos-name { font-size: 13px; font-weight: 600; color: #fff; }
.pos-code { font-size: 10px; color: #666; }
.pos-body { display: flex; justify-content: space-between; font-size: 11px; color: #999; }

/* 订单 */
.order-item { display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: rgba(255,255,255,0.03); border-radius: 6px; margin-bottom: 3px; font-size: 12px; }
.order-name { font-weight: 600; color: #ddd; flex: 1; }
.order-info { color: #999; }

.actions {
  display: flex; gap: 8px; margin: 10px 0;
}

.stats {
  display: grid; grid-template-columns: 1fr 1fr 1fr;
  gap: 8px; margin: 8px 0 14px;
}

.stat-card {
  background: linear-gradient(135deg, #1a1a2e, #16213e);
  border-radius: 8px; padding: 10px 8px; text-align: center;
}
.stat-val { font-size: 18px; font-weight: 800; color: #fff; }
.stat-label { font-size: 10px; color: #999; margin-top: 2px; }
.up { color: #e74c3c !important; }
.down { color: #2ecc71 !important; }
.down-val { color: #f39c12 !important; }

.chart-container {
  background: linear-gradient(135deg, #1a1a2e, #16213e);
  border-radius: 8px; padding: 12px 8px; margin: 0 0 14px;
}
.chart-title { font-size: 13px; color: #ccc; margin-bottom: 8px; }
.chart { width: 100%; height: 260px; }
.chart-x-label { font-size: 9px; color: #666; text-align: center; margin-top: 4px; }

.trades-section { margin-top: 8px; }
.section-title { font-size: 13px; font-weight: 600; color: #ccc; margin-bottom: 8px; }
.trade-item {
  background: linear-gradient(135deg, #1a1a2e, #16213e);
  border-radius: 8px; padding: 10px 12px; margin-bottom: 6px;
}
.trade-head { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.trade-name { font-size: 13px; font-weight: 600; color: #fff; }
.trade-code { font-size: 10px; color: #666; }
.trade-body { display: flex; justify-content: space-between; font-size: 11px; color: #999; }
.trade-reason { font-size: 10px; color: #5470c6; margin-top: 2px; }
.bt-msg { text-align: center; color: #999; font-size: 12px; margin-top: 40px; }
</style>

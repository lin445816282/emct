<template>
  <div class="review-page">
    <!-- 统计卡片 -->
    <div class="stat-cards">
      <div class="stat-card">
        <div class="card-val" :class="stats.total_pnl >= 0 ? 'up' : 'down'">
          ¥{{ fmt(stats.total_pnl) }}
        </div>
        <div class="card-label">总盈亏</div>
      </div>
      <div class="stat-card">
        <div class="card-val">{{ stats.win_rate }}%</div>
        <div class="card-label">胜率</div>
      </div>
      <div class="stat-card">
        <div class="card-val">{{ stats.profit_factor }}</div>
        <div class="card-label">盈亏比</div>
      </div>
      <div class="stat-card">
        <div class="card-val">{{ stats.closed_trades }}</div>
        <div class="card-label">平仓笔数</div>
      </div>
    </div>

    <div class="sub-stats">
      <div class="sub-row"><span>平均盈亏</span><span class="val" :class="stats.avg_pnl_pct >= 0 ? 'up' : 'down'">{{ stats.avg_pnl_pct }}%</span></div>
      <div class="sub-row"><span>平均持仓</span><span class="val">{{ stats.avg_hold_days }}天</span></div>
      <div class="sub-row"><span>最佳单笔</span><span class="val up">¥{{ fmt(stats.best_trade) }}</span></div>
      <div class="sub-row"><span>最差单笔</span><span class="val down">¥{{ fmt(stats.worst_trade) }}</span></div>
    </div>

    <!-- 净值曲线 -->
    <div v-if="equityCurve.length" class="section" style="padding:8px">
      <div class="section-title">📈 净值曲线</div>
      <div ref="chartRef" style="width:100%;height:220px"></div>
    </div>

    <!-- 操作按钮 -->
    <div class="action-bar">
      <van-button size="small" @click="doSync" :loading="syncing">同步订单</van-button>
      <van-button size="small" type="primary" @click="doAIAnalyze" :loading="aiLoading">AI分析</van-button>
      <van-button size="small" type="warning" @click="doBacktest" :loading="btLoading">回测</van-button>
    </div>

    <!-- 回测结果 -->
    <div v-if="btResult" class="bt-section">
      <div class="section-title">🎯 回测结果</div>
      <div class="bt-summary">
        <div class="bt-item"><span class="bt-label">总收益</span><span class="bt-val" :class="btResult.summary.total_return>=0?'up':'down'">{{ btResult.summary.total_return }}%</span></div>
        <div class="bt-item"><span class="bt-label">年化</span><span class="bt-val">{{ btResult.summary.cagr }}%</span></div>
        <div class="bt-item"><span class="bt-label">胜率</span><span class="bt-val">{{ btResult.summary.win_rate }}%</span></div>
        <div class="bt-item"><span class="bt-label">盈亏比</span><span class="bt-val">{{ btResult.summary.profit_factor }}</span></div>
        <div class="bt-item"><span class="bt-label">最大回撤</span><span class="bt-val down">{{ btResult.summary.max_drawdown }}%</span></div>
        <div class="bt-item"><span class="bt-label">交易笔数</span><span class="bt-val">{{ btResult.summary.total_trades }}</span></div>
      </div>
      <div v-if="btResult.diagnostic && btResult.summary.total_trades===0" class="bt-note">
        ⚠️ {{ btResult.diagnostic.skilled_no_kline || btResult.diagnostic.skipped_no_kline }}/{{ btResult.diagnostic.signals_total }} 信号无后续K线（数据未更新）
      </div>
    </div>

    <!-- AI分析结果 -->
    <div v-if="aiResult" class="ai-box">
      <div class="ai-title">🤖 DeepSeek 分析</div>
      <div class="ai-content">{{ aiResult }}</div>
    </div>

    <!-- 笔记弹窗 -->
    <van-dialog v-model:show="noteShow" title="交易笔记" show-cancel-button @confirm="saveNote">
      <div style="padding:16px">
        <div style="font-size:13px;color:#666;margin-bottom:8px">{{ noteTarget?.code }} {{ noteTarget?.name }}</div>
        <van-field v-model="noteText" rows="3" type="textarea" placeholder="记录这笔交易的思考..." />
      </div>
    </van-dialog>

    <!-- 月度盈亏 -->
    <div v-if="monthly.length" class="section">
      <div class="section-title">📅 月度盈亏</div>
      <div v-for="m in monthly" :key="m.month" class="month-row">
        <span>{{ m.month }}</span>
        <span class="val" :class="m.pnl >= 0 ? 'up' : 'down'">¥{{ fmt(m.pnl) }}</span>
        <span class="wl">{{ m.wins }}W / {{ m.losses }}L</span>
      </div>
    </div>

    <!-- 股票排行 -->
    <div v-if="stockPerf.length" class="section">
      <div class="section-title">📈 股票排行</div>
      <div v-for="s in stockPerf" :key="s.code" class="stock-row">
        <div class="stock-info">
          <span class="stock-name">{{ s.name }}</span>
          <span class="stock-code">{{ s.code }}</span>
        </div>
        <span class="val" :class="s.total_pnl >= 0 ? 'up' : 'down'">¥{{ fmt(s.total_pnl) }}</span>
        <span class="wl">{{ s.wins }}W / {{ s.losses }}L</span>
      </div>
    </div>

    <!-- 交易时间线 -->
    <div v-if="timeline.length" class="section">
      <div class="section-title">🕐 交易时间线</div>
      <div v-for="t in timeline" :key="t.id" class="timeline-item">
        <div class="tl-header">
          <van-tag :type="t.action === 'open' ? 'danger' : 'success'" size="small">
            {{ t.action === 'open' ? '开仓' : '平仓' }}
          </van-tag>
          <span class="tl-code">{{ t.code }}</span>
          <span class="tl-date">{{ t.created_at?.slice(0, 10) }}</span>
        </div>
        <div class="tl-body">
          <span>¥{{ t.price }} × {{ t.volume }}股</span>
          <span v-if="t.action === 'close'" class="pnl" :class="t.pnl >= 0 ? 'up' : 'down'">
            {{ t.pnl >= 0 ? '+' : '' }}¥{{ fmt(t.pnl) }}
          </span>
        </div>
        <div v-if="t.review" class="tl-review">💬 {{ t.review }}</div>
        <van-button v-if="!t.review" size="mini" plain @click="openNote(t)">+笔记</van-button>
        <van-button v-else size="mini" plain @click="openNote(t)">编辑</van-button>
      </div>
    </div>

    <van-loading v-if="loading" style="display:flex;justify-content:center;padding:40px" />
    <van-empty v-else-if="!stats.total_trades && !aiResult" description="暂无交易记录，执行下单后将自动生成" />
  </div>
</template>

<script setup>
import { ref, onMounted, watch, nextTick } from 'vue'
import { showToast } from 'vant'
import * as echarts from 'echarts'

const stats = ref({})
const monthly = ref([])
const stockPerf = ref([])
const timeline = ref([])
const aiResult = ref('')
const syncing = ref(false)
const aiLoading = ref(false)
const btLoading = ref(false)
const btResult = ref(null)
const equityCurve = ref([])
const chartRef = ref(null)
const loading = ref(true)
const noteShow = ref(false)
const noteTarget = ref(null)
const noteText = ref('')
let chartInstance = null

onMounted(() => { refresh(); loadEquityCurve() })

async function refresh() {
  try {
    const [s, m, p, t] = await Promise.all([
      fetch('/emct/api/review/stats').then(r => r.json()),
      fetch('/emct/api/review/monthly').then(r => r.json()),
      fetch('/emct/api/review/stocks').then(r => r.json()),
      fetch('/emct/api/review/timeline?limit=30').then(r => r.json()),
    ])
    stats.value = s
    monthly.value = m.rows || []
    stockPerf.value = p.rows || []
    timeline.value = t.rows || []
  } catch { /* empty */ }
  loading.value = false
}

async function doSync() {
  syncing.value = true
  try {
    const res = await fetch('/emct/api/review/sync', { method: 'POST' })
    const data = await res.json()
    showToast(`同步 ${data.synced || 0} 条`)
    refresh()
  } catch { showToast('同步失败') }
  syncing.value = false
}

async function doAIAnalyze() {
  aiLoading.value = true
  try {
    const res = await fetch('/emct/api/review/analyze')
    const data = await res.json()
    aiResult.value = data.analysis || 'AI分析无返回'
  } catch { showToast('分析失败，请刷新重试') }
  aiLoading.value = false
}

async function doBacktest() {
  btLoading.value = true
  try {
    const r = await fetch('/emct/api/sim/backtest')
    btResult.value = await r.json()
  } catch { showToast('回测失败') }
  btLoading.value = false
}

async function loadEquityCurve() {
  try {
    const r = await fetch('/emct/api/sim/equity-curve')
    const data = await r.json()
    equityCurve.value = data.rows || []
    await nextTick()
    renderChart()
  } catch { /* */ }
}

function renderChart() {
  if (!chartRef.value || !equityCurve.value.length) return
  if (chartInstance) chartInstance.dispose()
  chartInstance = echarts.init(chartRef.value)

  const dates = equityCurve.value.map(d => d.date.slice(5))  // MM-DD
  const totals = equityCurve.value.map(d => d.total)
  const baseline = equityCurve.value.length ? equityCurve.value[0].total : 50000

  chartInstance.setOption({
    grid: { top: 10, right: 16, bottom: 24, left: 48 },
    tooltip: { trigger: 'axis', formatter: p => `${p[0].axisValue}<br/>总资产 ¥${p[0].value.toLocaleString()}` },
    xAxis: { type: 'category', data: dates, axisLabel: { fontSize: 10, rotate: 45 } },
    yAxis: { type: 'value', min: v => Math.floor(v.min * 0.98), axisLabel: { formatter: v => '¥' + (v/10000).toFixed(0) + '万' } },
    series: [{
      data: totals, type: 'line', smooth: true,
      lineStyle: { color: '#1989fa', width: 2 },
      areaStyle: { color: new echarts.graphic.LinearGradient(0,0,0,1, [
        { offset: 0, color: 'rgba(25,137,250,0.3)' },
        { offset: 1, color: 'rgba(25,137,250,0.02)' }
      ])},
      itemStyle: { color: '#1989fa' },
      markLine: { silent: true, data: [{ yAxis: baseline, label: { formatter: '本金' }, lineStyle: { color: '#999', type: 'dashed' } }] }
    }]
  })
}

function fmt(v) { return (v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 0, maximumFractionDigits: 0 }) }

function openNote(t) {
  noteTarget.value = t
  noteText.value = t.review || ''
  noteShow.value = true
}

async function saveNote() {
  const t = noteTarget.value
  if (!t || !noteText.value.trim()) return
  try {
    await fetch(`/emct/api/review/${t.id}/note?review=${encodeURIComponent(noteText.value.trim())}`, { method: 'POST' })
    showToast('已保存')
    refresh()
  } catch { showToast('保存失败') }
}
</script>

<style scoped>
.stat-cards { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 12px; }
.stat-card { background: #fff; border-radius: 8px; padding: 14px; text-align: center; }
.card-val { font-size: 22px; font-weight: 700; color: #333; }
.card-val.up { color: #e74c3c; }
.card-val.down { color: #2ecc71; }
.card-label { font-size: 12px; color: #999; margin-top: 4px; }
.sub-stats { background: #fff; border-radius: 8px; padding: 8px 14px; margin-bottom: 12px; }
.sub-row { display: flex; justify-content: space-between; padding: 4px 0; font-size: 13px; }
.sub-row span:first-child { color: #666; }
.val { font-weight: 600; }
.val.up { color: #e74c3c; }
.val.down { color: #2ecc71; }
.action-bar { display: flex; gap: 8px; margin-bottom: 12px; }
.ai-box { background: #f0f7ff; border-radius: 8px; padding: 12px 14px; margin-bottom: 12px; white-space: pre-wrap; font-size: 13px; line-height: 1.6; }
.ai-title { font-weight: 600; margin-bottom: 6px; color: #1989fa; }
.ai-content { color: #333; }
.section { background: #fff; border-radius: 8px; padding: 10px 14px; margin-bottom: 12px; }
.section-title { font-size: 14px; font-weight: 600; margin-bottom: 8px; color: #333; }
.month-row, .stock-row { display: flex; justify-content: space-between; align-items: center; padding: 6px 0; font-size: 13px; border-bottom: 1px solid #f5f5f5; }
.month-row:last-child, .stock-row:last-child { border-bottom: none; }
.wl { color: #999; font-size: 12px; min-width: 70px; text-align: right; }
.stock-info { display: flex; flex-direction: column; }
.stock-name { font-weight: 500; }
.stock-code { font-size: 11px; color: #999; }
.timeline-item { padding: 8px 0; border-bottom: 1px solid #f0f0f0; }
.timeline-item:last-child { border-bottom: none; }
.tl-header { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.tl-code { font-weight: 500; font-size: 13px; }
.tl-date { color: #999; font-size: 11px; }
.tl-body { font-size: 12px; color: #666; display: flex; justify-content: space-between; }
.pnl { font-weight: 600; }
.tl-review { font-size: 12px; color: #1989fa; margin-top: 2px; }
.bt-section { background: #fff; border-radius: 8px; padding: 10px 14px; margin-bottom: 12px; }
.bt-summary { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 6px; }
.bt-item { text-align: center; padding: 6px 0; }
.bt-label { font-size: 11px; color: #999; display: block; }
.bt-val { font-size: 16px; font-weight: 700; color: #333; }
.bt-val.up { color: #e74c3c; }
.bt-val.down { color: #2ecc71; }
.bt-note { font-size: 11px; color: #e6a23c; margin-top: 6px; padding: 4px 8px; background: #fef0e6; border-radius: 4px; }
</style>

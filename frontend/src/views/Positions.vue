<template>
  <div class="positions-page">
    <!-- 模拟模式提醒 -->
    <div v-if="simStore.enabled" style="background:#e3f2fd;border-radius:8px;padding:6px 12px;margin-bottom:12px;font-size:12px;color:#1976d2">
      🎮 模拟持仓 · 非真实账户数据
    </div>

    <div class="summary-card">
      <div class="sum-item">
        <span class="label">总市值</span>
        <span class="value">¥{{ fmt(simStore.enabled ? simStore.totalValue : summary.total_value) }}</span>
      </div>
      <div class="sum-item">
        <span class="label">持仓数</span>
        <span class="value">{{ displayList.length }}</span>
      </div>
      <div class="sum-item">
        <span class="label">总盈亏</span>
        <span class="value" :class="(simStore.enabled ? simStore.totalPnl : summary.total_pnl) >= 0 ? 'up' : 'down'">
          {{ (simStore.enabled ? simStore.totalPnl : summary.total_pnl) >= 0 ? '+' : '' }}{{ fmt(simStore.enabled ? simStore.totalPnl : summary.total_pnl) }}
        </span>
      </div>
      <div class="sum-item">
        <span class="label">收益率</span>
        <span class="value" :class="(simStore.enabled ? simStore.totalPnlPct : summary.pnl_pct) >= 0 ? 'up' : 'down'">
          {{ (simStore.enabled ? simStore.totalPnlPct : summary.pnl_pct) >= 0 ? '+' : '' }}{{ simStore.enabled ? simStore.totalPnlPct : summary.pnl_pct }}%
        </span>
      </div>
    </div>

    <!-- 风控警告 -->
    <div v-if="riskData.warnings?.length" class="risk-warnings">
      <div v-for="(w, i) in riskData.warnings" :key="i" class="warn-item" :class="w.includes('止损') ? 'danger' : w.includes('止盈') ? 'info' : 'warn'">
        {{ w }}
      </div>
    </div>

    <!-- 仓位饼图 -->
    <div v-if="!simStore.enabled && displayList.length" class="chart-card">
      <div class="chart-title">📊 仓位分布</div>
      <div ref="chartRef" class="pie-chart"></div>
    </div>

    <van-loading v-if="loading" style="display:flex;justify-content:center;padding:40px" />
    <van-empty v-else-if="!displayList.length" :description="simStore.enabled ? '暂无模拟持仓，先去订单页下单' : '暂无持仓'" />

    <van-card v-for="p in displayList" :key="p.id" :title="p.name" :desc="p.code">
      <template #price>
        <div class="pos-detail">
          <span>成本 ¥{{ fmt(p.avg_cost) }} | 现价 ¥{{ fmt(p.current_price) }}</span>
        </div>
      </template>
      <template #footer>
        <div class="pos-footer">
          <div class="pos-info">
            <span>{{ p.volume }}股 · 市值 ¥{{ fmt(p.market_value) }}</span>
            <span class="pnl" :class="p.profit_loss >= 0 ? 'up' : 'down'">
              {{ p.profit_loss >= 0 ? '+' : '' }}{{ fmt(p.profit_loss) }} ({{ p.profit_loss_pct >= 0 ? '+' : '' }}{{ p.profit_loss_pct }}%)
            </span>
          </div>
          <van-button v-if="simStore.enabled" size="small" type="danger" plain @click="openSell(p)">卖出</van-button>
        </div>
      </template>
    </van-card>

    <!-- 卖出弹窗 -->
    <van-dialog v-model:show="sellShow" title="卖出确认" show-cancel-button @confirm="doSell">
      <div style="padding:16px">
        <div style="margin-bottom:12px;font-size:14px">{{ sellTarget?.name }} ({{ sellTarget?.code }})</div>
        <div style="margin-bottom:8px;color:#666;font-size:12px">
          持仓 {{ sellTarget?.volume || 0 }}股 · 成本 ¥{{ fmt(sellTarget?.avg_cost) }} · 现价 ¥{{ fmt(sellTarget?.current_price) }}
        </div>
        <van-stepper v-model="sellVolume" :min="100" :max="sellTarget?.volume || 0" :step="100" style="margin:8px auto;display:flex;justify-content:center" />
        <div style="text-align:center;color:#999;font-size:12px;margin-top:4px">
          预计 ¥{{ fmt((sellTarget?.current_price || 0) * sellVolume) }}
        </div>
      </div>
    </van-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { positions } from '../api/index.js'
import { useSimStore } from '../stores/sim'
import { showToast } from 'vant'
import * as echarts from 'echarts'

const simStore = useSimStore()
const posList = ref([])
const summary = ref({ total_value: 0, total_pnl: 0, total_cost: 0, pnl_pct: 0 })
const riskData = ref({ warnings: [], positions: [] })
const loading = ref(true)

const displayList = computed(() => {
  return simStore.enabled ? simStore.positions : posList.value
})

// 卖出相关
const sellShow = ref(false)
const sellTarget = ref(null)
const sellVolume = ref(100)

const chartRef = ref(null)
let chart = null

onMounted(refresh)
watch(() => simStore.enabled, refresh)
watch(displayList, () => nextTick(() => renderPie()))

async function refresh() {
  try {
    if (simStore.enabled) {
      await simStore.refreshPrices()
    } else {
      const [posData, sumData, riskRes] = await Promise.all([
        positions.list(), positions.summary(),
        fetch('/emct/api/orders/risk/summary').then(r => r.json()).catch(() => ({ warnings: [], positions: [] }))
      ])
      posList.value = posData.rows || []
      summary.value = sumData
      riskData.value = riskRes
      await nextTick()
      renderPie()
    }
  } catch { /* empty */ }
  loading.value = false
}

function openSell(p) {
  sellTarget.value = p
  sellVolume.value = Math.min(100, p.volume)  // 默认100股
  sellShow.value = true
}

async function doSell() {
  const p = sellTarget.value
  if (!p) return
  try {
    const result = await simStore.quickTrade(p.code, p.name, 'sell', p.current_price, sellVolume.value)
    if (result.ok) {
      showToast(`卖出 ${sellVolume.value}股 成功`)
    } else {
      showToast(result.error || '卖出失败')
    }
  } catch { showToast('网络错误') }
}

function renderPie() {
  if (!chartRef.value) return
  const posData = riskData.value.positions || posList.value
  if (!posData.length) return
  if (chart) chart.dispose()

  chart = echarts.init(chartRef.value)
  const data = posData.map(p => ({
    name: p.name,
    value: p.market_value || 0
  }))

  chart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: ¥{c} ({d}%)' },
    series: [{
      type: 'pie',
      radius: ['45%', '75%'],
      center: ['50%', '50%'],
      data: data,
      emphasis: { itemStyle: { shadowBlur: 10, shadowOffsetX: 0 } },
      label: { fontSize: 10, color: '#666' },
    }]
  })
  window.addEventListener('resize', () => chart?.resize())
}

function fmt(v) { return (v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
</script>

<style scoped>
.summary-card { 
  display: flex; justify-content: space-around; padding: 16px; 
  background: #fff; border-radius: 8px; margin-bottom: 12px;
}
.sum-item { text-align: center; }
.sum-item .label { display: block; font-size: 12px; color: #999; }
.sum-item .value { display: block; font-size: 16px; font-weight: bold; margin-top: 4px; }
.up { color: #e74c3c; }
.down { color: #2ecc71; }
.pos-detail { font-size: 12px; color: #666; }
.pos-footer { 
  display: flex; justify-content: space-between; align-items: center;
  gap: 8px;
}
.pos-info { display: flex; flex-direction: column; font-size: 12px; }
.pnl { font-weight: bold; font-size: 14px; }

/* 风控 */
.risk-warnings { margin-bottom: 10px; }
.warn-item { padding: 6px 10px; border-radius: 6px; font-size: 12px; margin-bottom: 4px; }
.warn-item.danger { background: #fff0f0; color: #e74c3c; border-left: 3px solid #e74c3c; }
.warn-item.info { background: #f0f7ff; color: #2ecc71; border-left: 3px solid #2ecc71; }
.warn-item.warn { background: #fff8e6; color: #e6a23c; border-left: 3px solid #e6a23c; }

/* 饼图 */
.chart-card { background: #fff; border-radius: 8px; padding: 10px 8px; margin-bottom: 12px; }
.chart-title { font-size: 13px; font-weight: 600; color: #333; margin-bottom: 6px; }
.pie-chart { width: 100%; height: 220px; }
</style>

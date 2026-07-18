<template>
  <div class="orders-page">
    <!-- 模式提示 -->
    <div class="mode-bar" :class="simStore.enabled ? 'sim' : 'real'">
      <span>{{ simStore.enabled ? '🎮 模拟模式' : '📡 实盘CDP' }}</span>
      <span style="font-size:11px;opacity:0.7">{{ simStore.enabled ? '资金不影响真实账户' : cdpOk ? '已连接' : '未连接 · 点检检测' }}</span>
      <van-button v-if="!simStore.enabled" size="mini" @click="checkCDP">检测</van-button>
    </div>

    <!-- 快捷下单（模拟模式） -->
    <div v-if="simStore.enabled" class="quick-order">
      <van-field v-model="form.code" placeholder="股票代码" style="flex:1" />
      <van-field v-model="form.name" placeholder="名称" style="flex:1" />
      <van-field v-model.number="form.price" placeholder="价格" style="flex:0.6" />
      <van-field v-model.number="form.volume" placeholder="股数" style="flex:0.6" />
      <div class="qo-btns">
        <van-button size="small" type="danger" :loading="trading" @click="doQuick('buy')">买入</van-button>
        <van-button size="small" type="success" :loading="trading" @click="doQuick('sell')">卖出</van-button>
      </div>
    </div>

    <van-empty v-if="!orderList.length" description="暂无订单，上方快捷下单" />

    <!-- 风控总览 -->
    <div v-if="!simStore.enabled && riskSummary.total_value" class="risk-panel">
      <div class="risk-title">🛡️ 风控总览</div>
      <div class="risk-stats">
        <div class="risk-item"><span>总市值</span><b>¥{{ fmt(riskSummary.total_value) }}</b></div>
        <div class="risk-item"><span>持仓数</span><b>{{ riskSummary.position_count }}</b></div>
      </div>
      <div v-if="riskSummary.warnings?.length" class="risk-warn-list">
        <div v-for="(w, i) in riskSummary.warnings" :key="i" class="risk-warn">{{ w }}</div>
      </div>
    </div>

    <van-cell-group v-for="o in orderList" :key="o.id" inset style="margin-bottom:8px">
      <van-cell :title="o.name + ' (' + o.code + ')'" :label="'#' + o.id + ' · ' + o.created_at">
        <template #right-icon>
          <van-tag :type="o.sim_mode ? 'warning' : ''" size="small" style="margin-right:4px" v-if="o.sim_mode">模拟</van-tag>
          <van-tag :type="orderColor(o.direction)" size="small">{{ o.direction === 'buy' ? '买入' : '卖出' }}</van-tag>
        </template>
      </van-cell>
      <van-cell title="价格" :value="'¥' + fmt(o.price)" />
      <van-cell title="数量" :value="o.volume + '股'" />
      <van-cell title="金额" :value="'¥' + fmt(o.amount)" />
      <van-cell title="状态">
        <van-tag :type="statusColor(o.order_status)">{{ statusLabel(o.order_status) }}</van-tag>
      </van-cell>
      <van-cell v-if="o.error_msg" title="错误信息" :value="o.error_msg" label-class="error" />
      <div v-if="o.order_status === 'created'" class="cell-action">
        <van-button size="small" type="danger" :loading="execId === o.id" @click="doExecute(o)">
          ▶ {{ o.sim_mode ? '模拟执行' : '执行下单' }}
        </van-button>
      </div>
      <div v-if="o.order_status === 'filled' && o.sim_mode" class="cell-action">
        <van-tag type="success" size="medium">✅ 已成交</van-tag>
      </div>
    </van-cell-group>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { orders as ordersApi } from '../api/index.js'
import { useSimStore } from '../stores/sim'
import { showToast } from 'vant'

const simStore = useSimStore()
const orderList = ref([])
const cdpOk = ref(false)
const execId = ref(0)
const trading = ref(false)
const riskSummary = ref({ total_value: 0, position_count: 0, warnings: [] })

const form = ref({ code: '', name: '', price: 0, volume: 100 })

onMounted(refresh)

watch(() => simStore.enabled, refresh)

async function refresh() {
  if (simStore.enabled) {
    try {
      const res = await fetch('/emct/api/sim/orders?limit=30')
      const data = await res.json()
      orderList.value = data.rows || []
    } catch { orderList.value = [] }
  } else {
    try {
      const data = await ordersApi.list()
      orderList.value = data.rows || []
      checkCDP()
      loadRisk()
    } catch { orderList.value = [] }
  }
}

async function checkCDP() {
  try {
    const res = await fetch('/emct/api/orders/cdp/status')
    const data = await res.json()
    cdpOk.value = data.connected
  } catch { cdpOk.value = false }
}

async function loadRisk() {
  try {
    const res = await fetch('/emct/api/orders/risk/summary')
    riskSummary.value = await res.json()
  } catch { riskSummary.value = { total_value: 0, position_count: 0, warnings: [] } }
}

async function doQuick(direction) {
  const { code, name, price, volume } = form.value
  // 模拟模式价格可省略（后端取日线收盘价），实盘必填
  const needPrice = !simStore.enabled && !price
  if (!code || !name || needPrice || !volume) {
    showToast('请填写完整信息'); return
  }
  trading.value = true
  try {
    if (simStore.enabled) {
      const result = await simStore.quickTrade(code, name, direction, price, volume)
      if (result.ok) {
        showToast(`${direction === 'buy' ? '买入' : '卖出'}成功`)
        form.value = { code: '', name: '', price: 0, volume: 100 }
      } else {
        showToast(result.error || '交易失败')
      }
    } else {
      const params = new URLSearchParams({ code, name, direction, price, volume })
      const res = await fetch(`/emct/api/orders/quick-buy?${params}`, { method: 'POST' })
      const data = await res.json()
      if (data.ok) showToast('已提交')
      else showToast(data.error || '失败')
    }
  } catch (e) {
    showToast('网络错误')
  }
  trading.value = false
  refresh()
}

async function doExecute(o) {
  execId.value = o.id
  try {
    if (o.sim_mode) {
      const res = await fetch(`/emct/api/sim/order/${o.id}/execute`, { method: 'POST' })
      const data = await res.json()
      if (data.ok) {
        showToast(data.pnl != null ? `成交 · P&L ¥${data.pnl}` : '成交')
        simStore.refresh()
      } else {
        showToast(data.error || '执行失败')
      }
    } else {
      const res = await fetch(`/emct/api/orders/${o.id}/execute`, { method: 'POST' })
      const data = await res.json()
      if (data.ok) showToast('已提交')
      else showToast(data.error || '执行失败')
    }
  } catch { showToast('网络错误') }
  execId.value = 0
  refresh()
}

function fmt(v) { return (v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
function orderColor(d) { return d === 'buy' ? 'danger' : 'success' }
function statusColor(s) {
  return { filled: 'success', submitted: 'primary', created: 'warning', executing: 'primary', cancelled: 'default', failed: 'danger' }[s] || 'default'
}
function statusLabel(s) {
  return { filled: '已成交', submitted: '已提交', created: '待执行', executing: '执行中', cancelled: '已取消', failed: '失败' }[s] || s
}
</script>

<style scoped>
.mode-bar { display: flex; justify-content: space-between; align-items: center; padding: 8px 12px; border-radius: 8px; margin-bottom: 12px; font-size: 13px; }
.mode-bar.sim { background: #e3f2fd; }
.mode-bar.real { background: #fff3e0; }
.mode-bar.real.connected { background: #e8f5e9; }
.quick-order { background: #fff; border-radius: 8px; padding: 8px; margin-bottom: 12px; display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
.quick-order :deep(.van-field) { background: #f5f6f8; border-radius: 4px; padding: 4px 8px; }
.quick-order :deep(.van-field__control) { font-size: 13px; }
.qo-btns { display: flex; gap: 6px; width: 100%; justify-content: flex-end; padding-top: 6px; }
.cell-action { padding: 8px 16px; text-align: right; }
.error { color: #e74c3c !important; }

/* 风控面板 */
.risk-panel { background: #fff; border-radius: 8px; padding: 10px 14px; margin-bottom: 12px; }
.risk-title { font-size: 13px; font-weight: 600; color: #333; margin-bottom: 8px; }
.risk-stats { display: flex; gap: 20px; margin-bottom: 6px; }
.risk-item { display: flex; gap: 6px; font-size: 13px; color: #666; }
.risk-item b { color: #333; }
.risk-warn-list { margin-top: 4px; }
.risk-warn { padding: 3px 8px; background: #fff0f0; border-radius: 4px; font-size: 11px; color: #e74c3c; margin-bottom: 3px; }
</style>

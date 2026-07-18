<template>
  <div class="settings-page">
    <!-- 数据面板 -->
    <div class="section">
      <div class="sec-title">📊 数据状态</div>
      <div class="stat-row">
        <span class="label">股票池</span>
        <span class="value">{{ poolList.length }}只</span>
      </div>
      <div class="stat-row">
        <span class="label">日线缓存</span>
        <span class="value">{{ dataStats.total || 0 }}条 ({{ dataStats.stocks || 0 }}只)</span>
      </div>
      <div class="stat-row" v-if="dataStats.latest">
        <span class="label">最新日期</span>
        <span class="value">{{ dataStats.latest }}</span>
      </div>
      <div class="panel-btns">
        <van-button size="small" type="primary" :loading="syncing" @click="doSync">同步日线</van-button>
        <van-button size="small" type="warning" :loading="scanning" @click="doScan">分析扫描</van-button>
      </div>
    </div>

    <!-- AI 复盘 -->
    <div class="section">
      <div class="sec-title">🤖 AI 复盘</div>
      <van-button type="primary" block :loading="reviewing" @click="doReview">执行 AI 复盘分析</van-button>
      <div class="review-result" v-if="reviewResult" v-html="reviewResult"></div>
    </div>

    <!-- 股票池 -->
    <div class="section">
      <div class="sec-title">
        <span>📋 股票池 ({{ poolList.length }})</span>
        <van-button size="mini" type="primary" @click="showPoolAdd = true">+添加</van-button>
      </div>
      <div class="pool-list">
        <div v-for="s in poolList" :key="s.code" class="pool-item" :class="{ inactive: !s.active }">
          <div class="pool-info">
            <span class="pool-name">{{ s.name }}</span>
            <span class="pool-code">{{ s.code }}</span>
            <van-tag v-if="s.sector" size="mini" type="default">{{ s.sector }}</van-tag>
            <van-tag size="mini" :type="s.active ? 'success' : 'default'">{{ s.active ? '启用' : '禁用' }}</van-tag>
          </div>
          <div class="pool-acts">
            <van-button size="mini" plain @click="doToggle(s.code)">{{ s.active ? '禁用' : '启用' }}</van-button>
            <van-button size="mini" plain type="danger" @click="doRemove(s.code)">删除</van-button>
          </div>
        </div>
      </div>
    </div>

    <!-- 因子权重 -->
    <div class="section">
      <div class="sec-title">⚖️ 因子权重</div>
      <div class="weight-list">
        <div v-for="(w, k) in weights" :key="k" class="weight-item">
          <span class="w-label">{{ weightLabels[k] || k }}</span>
          <van-progress :percentage="w * 100" stroke-width="6" :show-pivot="false" />
          <span class="w-val">{{ (w * 100).toFixed(0) }}%</span>
        </div>
      </div>
    </div>

    <!-- 添加股票弹窗 -->
    <van-popup v-model:show="showPoolAdd" position="bottom" :style="{ height: '50%' }">
      <div class="pool-form">
        <div class="pop-title">添加股票</div>
        <van-field v-model="poolForm.code" label="代码" placeholder="如 600519" />
        <van-field v-model="poolForm.name" label="名称" placeholder="如 贵州茅台" />
        <van-field v-model="poolForm.market" label="市场" placeholder="SH / SZ" />
        <van-field v-model="poolForm.sector" label="板块" placeholder="如 白酒" />
        <van-button type="primary" block :loading="adding" @click="doAdd">确认添加</van-button>
      </div>
    </van-popup>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { stockPool } from '../api/index.js'
import { showToast } from 'vant'

const poolList = ref([])
const dataStats = ref({})
const syncing = ref(false)
const scanning = ref(false)
const reviewing = ref(false)
const reviewResult = ref('')
const showPoolAdd = ref(false)
const adding = ref(false)
const poolForm = ref({ code: '', name: '', market: 'SH', sector: '' })

const weights = ref({})

const weightLabels = {
  ma_trend: '均线趋势', macd: 'MACD', rsi: 'RSI',
  bollinger: '布林带', volume: '量价', momentum: '动量',
}

onMounted(() => { loadData(); loadWeights() })

async function loadData() {
  const [pool, stats] = await Promise.all([
    stockPool.list(),
    fetch('/emct/api/data/stats').then(r => r.json())
  ])
  poolList.value = pool.rows || []
  dataStats.value = stats
}

async function loadWeights() {
  try {
    const r = await fetch('/emct/api/signals/weights')
    if (r.ok) weights.value = await r.json()
  } catch { /* weights API may not exist yet */ }
}

async function doSync() {
  syncing.value = true
  try {
    const res = await fetch('/emct/api/data/sync?days=60', { method: 'POST' })
    const data = await res.json()
    showToast(data.msg || '已开始同步')
    setTimeout(() => { loadData(); syncing.value = false }, 3000)
  } catch {
    showToast('同步失败')
    syncing.value = false
  }
}

async function doScan() {
  scanning.value = true
  try {
    const { signals } = await import('../api/index.js')
    const data = await signals.scan()
    showToast(`扫描完成: ${data.saved}只`)
  } catch { showToast('扫描失败') }
  scanning.value = false
}

async function doReview() {
  reviewing.value = true
  try {
    const r = await fetch('/emct/api/review/analyze')
    const data = await r.json()
    reviewResult.value = data.analysis || '分析完成'
  } catch { showToast('AI复盘失败') }
  reviewing.value = false
}

async function doAdd() {
  const { code, name, market, sector } = poolForm.value
  if (!code || !name) { showToast('请填代码和名称'); return }
  adding.value = true
  try {
    const res = await fetch(`/emct/api/stock-pool/add?code=${code}&name=${encodeURIComponent(name)}&market=${market}&sector=${encodeURIComponent(sector)}`, { method: 'POST' })
    if (res.ok) { showToast('已添加'); showPoolAdd.value = false; poolForm.value = { code: '', name: '', market: 'SH', sector: '' }; loadData() }
    else { showToast('添加失败') }
  } catch { showToast('网络错误') }
  adding.value = false
}

async function doToggle(code) {
  try {
    const res = await fetch(`/emct/api/stock-pool/toggle?code=${code}`, { method: 'POST' })
    if (res.ok) loadData()
  } catch { /* */ }
}

async function doRemove(code) {
  try {
    await fetch(`/emct/api/stock-pool/remove?code=${code}`, { method: 'DELETE' })
    loadData()
  } catch { /* */ }
}
</script>

<style scoped>
.settings-page { padding-bottom: 20px; }
.section {
  background: #fff; border-radius: 8px; padding: 12px 14px; margin-bottom: 12px;
}
.sec-title {
  display: flex; justify-content: space-between; align-items: center;
  font-size: 14px; font-weight: 600; color: #333; margin-bottom: 10px;
}
.stat-row { display: flex; justify-content: space-between; padding: 4px 0; font-size: 13px; }
.stat-row .label { color: #666; }
.stat-row .value { color: #333; font-weight: 500; }
.panel-btns { display: flex; gap: 8px; margin-top: 8px; }
.panel-btns .van-button { flex: 1; }

.review-result {
  margin-top: 10px; padding: 10px; background: #f8f9fb; border-radius: 6px;
  font-size: 13px; line-height: 1.6; white-space: pre-wrap;
}

.pool-list { max-height: 220px; overflow-y: auto; }
.pool-item { display: flex; justify-content: space-between; align-items: center; padding: 5px 0; border-bottom: 1px solid #f5f5f5; }
.pool-item.inactive { opacity: 0.5; }
.pool-info { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; flex: 1; }
.pool-name { font-size: 12px; font-weight: 500; }
.pool-code { font-size: 10px; color: #999; }
.pool-acts { display: flex; gap: 4px; }

.weight-list { display: flex; flex-direction: column; gap: 8px; }
.weight-item { display: flex; align-items: center; gap: 8px; }
.w-label { font-size: 12px; color: #666; min-width: 56px; }
.w-val { font-size: 12px; color: #333; min-width: 32px; text-align: right; }

.pool-form { padding: 16px; }
.pop-title { font-size: 15px; font-weight: 700; margin-bottom: 12px; text-align: center; }
.pool-form .van-button { margin-top: 12px; }
</style>

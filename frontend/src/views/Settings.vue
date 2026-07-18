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

    <!-- 策略配置 -->
    <div class="section">
      <div class="sec-title">⚙️ 策略配置</div>

      <van-tabs v-model:active="configTab" type="card" class="cfg-tabs">
        <van-tab title="因子权重">
          <div class="slider-group">
            <div v-for="k in wKeys" :key="k" class="slider-item">
              <div class="slider-label">
                <span>{{ weightLabels[k] }}</span>
                <span class="w-pct">{{ (wgts[k] * 100).toFixed(0) }}%</span>
              </div>
              <van-slider v-model="wgts[k]" :min="0.05" :max="0.35" :step="0.01" bar-height="4px" @update:model-value="autoBalance(k)" />
            </div>
            <div class="slider-total" :class="{ ok: totalWeight === 100 }">
              合计: {{ totalWeight }}% {{ totalWeight === 100 ? '✓' : '⚠ 需=100%' }}
            </div>
          </div>
        </van-tab>

        <van-tab title="信号阀值">
          <div class="slider-group">
            <div v-for="(t, k) in cfg.thresholds" :key="k" class="slider-item">
              <div class="slider-label">
                <span>{{ tlabels[k] }}</span>
                <span class="w-pct">{{ t }}</span>
              </div>
              <van-slider v-model="cfg.thresholds[k]" :min="k.includes('sell') ? -60 : 0" :max="k.includes('sell') ? -2 : 60" :step="1" bar-height="4px" />
            </div>
          </div>
        </van-tab>

        <van-tab title="风控参数">
          <div class="slider-group">
            <div class="slider-item">
              <div class="slider-label"><span>🐻 熊市因子</span><span class="w-pct">{{ (cfg.bear_factor * 100).toFixed(0) }}%</span></div>
              <van-slider v-model="cfg.bear_factor" :min="0.1" :max="1.0" :step="0.05" bar-height="4px" />
            </div>
            <div class="slider-item">
              <div class="slider-label"><span>📊 满仓数</span><span class="w-pct">{{ cfg.max_positions }}只</span></div>
              <van-slider v-model="cfg.max_positions" :min="2" :max="20" :step="1" bar-height="4px" />
            </div>
            <div class="slider-item">
              <div class="slider-label"><span>⚡ 最低评分</span><span class="w-pct">{{ cfg.min_strength }}</span></div>
              <van-slider v-model="cfg.min_strength" :min="5" :max="25" :step="1" bar-height="4px" />
            </div>
            <div class="slider-item">
              <div class="slider-label"><span>💰 单笔上限</span><span class="w-pct">¥{{ cfg.max_single_amount.toLocaleString() }}</span></div>
              <van-slider v-model="cfg.max_single_amount" :min="1000" :max="20000" :step="500" bar-height="4px" />
            </div>
            <div class="slider-item">
              <div class="slider-label"><span>🛑 止损线</span><span class="w-pct">{{ cfg.stop_loss_pct }}%</span></div>
              <van-slider v-model="cfg.stop_loss_pct" :min="-20" :max="-2" :step="1" bar-height="4px" />
            </div>
            <div class="slider-item">
              <div class="slider-label"><span>🎯 止盈线</span><span class="w-pct">{{ cfg.take_profit_pct }}%</span></div>
              <van-slider v-model="cfg.take_profit_pct" :min="5" :max="30" :step="1" bar-height="4px" />
            </div>
            <div class="slider-item">
              <div class="slider-label"><span>📅 持仓天数</span><span class="w-pct">{{ cfg.max_hold_days }}天</span></div>
              <van-slider v-model="cfg.max_hold_days" :min="3" :max="20" :step="1" bar-height="4px" />
            </div>
          </div>
        </van-tab>
      </van-tabs>

      <div class="cfg-actions">
        <van-button size="small" type="primary" :loading="saving" @click="doSaveCfg">💾 保存</van-button>
        <van-button size="small" type="warning" :loading="optimizing" @click="doOptimize">🤖 AI优化</van-button>
        <van-button size="small" plain @click="doResetCfg">🔄 默认</van-button>
      </div>

      <div class="opt-result" v-if="optResult">
        <div class="opt-title">{{ optResult.reason || 'AI优化建议' }}</div>
        <div class="opt-actions">
          <van-button size="small" type="success" @click="applyOptimize">✅ 应用</van-button>
          <van-button size="small" plain @click="optResult = null">忽略</van-button>
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
import { ref, computed, onMounted } from 'vue'
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

const weights = ref({
  ma_trend: 0.18, macd: 0.18, rsi: 0.14,
  bollinger: 0.17, volume: 0.17, momentum: 0.16
})
const wKeys = ['ma_trend', 'macd', 'rsi', 'bollinger', 'volume', 'momentum']
const wgts = ref({
  ma_trend: 0.18, macd: 0.18, rsi: 0.14,
  bollinger: 0.17, volume: 0.17, momentum: 0.16
})
const configTab = ref(0)
const saving = ref(false), optimizing = ref(false), resetting = ref(false)
const optResult = ref(null)

const cfg = ref({
  thresholds: { strong_buy: 28, buy: 10, sell: -10, strong_sell: -28 },
  bear_factor: 0.5, max_positions: 8, min_strength: 10,
  max_single_amount: 5000, stop_loss_pct: -8, take_profit_pct: 15, max_hold_days: 10
})

const tlabels = { strong_buy: '强烈买入', buy: '买入', sell: '卖出', strong_sell: '强烈卖出' }

const weightLabels = {
  ma_trend: '均线趋势', macd: 'MACD', rsi: 'RSI',
  bollinger: '布林带', volume: '量价', momentum: '动量',
}

onMounted(() => { loadData(); loadCfg() })

async function loadData() {
  const [pool, stats] = await Promise.all([
    stockPool.list(),
    fetch('/emct/api/data/stats').then(r => r.json())
  ])
  poolList.value = pool.rows || []
  dataStats.value = stats
}

// ── 策略配置 ──
const totalWeight = computed(() => Math.round(Object.values(wgts.value).reduce((a, b) => a + b, 0) * 100))

function autoBalance(changed) {
  const others = wKeys.filter(k => k !== changed)
  const current = Object.values(wgts.value).reduce((a, b) => a + b, 0)
  const target = 0.18 * (wKeys.length - 1) // 其余默认值
  const diff = (current - wgts.value[changed]) - target
  others.forEach(k => { wgts.value[k] = Math.round((wgts.value[k] - diff / others.length) * 100) / 100 })
  // 归一化
  const sum = Object.values(wgts.value).reduce((a, b) => a + b, 0)
  if (sum > 0) wKeys.forEach(k => { wgts.value[k] = Math.round(wgts.value[k] / sum * 100) / 100 })
}

async function loadCfg() {
  try {
    const r = await fetch('/emct/api/strategy/config')
    if (r.ok) {
      const data = await r.json()
      wgts.value = { ...data.weights }
      cfg.value = { ...data, weights: undefined, thresholds: { ...data.thresholds } }
    }
  } catch (e) {
    // fallback to loaded weights
    wgts.value = { ...weights.value }
  }
}

async function doSaveCfg() {
  saving.value = true
  try {
    const payload = {
      ...cfg.value,
      weights: { ...wgts.value }
    }
    const r = await fetch('/emct/api/strategy/config', {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    const data = await r.json()
    if (data.ok) showToast('配置已保存')
    else showToast('保存失败: ' + (data.error || ''))
  } catch { showToast('网络错误') }
  saving.value = false
}

async function doOptimize() {
  optimizing.value = true
  optResult.value = null
  try {
    const r = await fetch('/emct/api/strategy/optimize', { method: 'POST' })
    const data = await r.json()
    if (data.suggestion) {
      optResult.value = data
    } else {
      showToast(data.error || '无可优化建议')
    }
  } catch { showToast('优化失败') }
  optimizing.value = false
}

function applyOptimize() {
  if (!optResult.value?.suggestion) return
  const { weights: w, ...rest } = optResult.value.suggestion
  if (w) wgts.value = { ...w }
  cfg.value = { ...cfg.value, ...rest, thresholds: rest.thresholds || cfg.value.thresholds }
  optResult.value = null
  showToast('已应用优化配置')
}

async function doResetCfg() {
  resetting.value = true
  try {
    const r = await fetch('/emct/api/strategy/reset', { method: 'POST' })
    const data = await r.json()
    if (data.ok) {
      wgts.value = { ...data.weights }
      cfg.value = { ...data, weights: undefined, thresholds: { ...data.thresholds } }
      showToast('已恢复默认')
    }
  } catch { showToast('复位失败') }
  resetting.value = false
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

/* 策略配置 */
.cfg-tabs { margin-bottom: 10px; }
.slider-group { padding: 4px 0; }
.slider-item { margin-bottom: 12px; }
.slider-label { display: flex; justify-content: space-between; align-items: center; font-size: 12px; color: #333; margin-bottom: 4px; }
.slider-label .w-pct { font-weight: 600; color: #1989fa; }
.slider-total { text-align: center; font-size: 13px; color: #ee0a24; margin-top: 6px; }
.slider-total.ok { color: #07c160; }
.slider-score { font-size: 11px; min-width: 36px; text-align: right; }
.cfg-actions { display: flex; gap: 8px; margin-top: 12px; justify-content: center; }
.opt-result { margin-top: 10px; padding: 10px; background: #f8f9fb; border-radius: 6px; }
.opt-title { font-size: 13px; color: #333; margin-bottom: 8px; white-space: pre-wrap; }
.opt-actions { display: flex; gap: 8px; }

.pool-form { padding: 16px; }
.pop-title { font-size: 15px; font-weight: 700; margin-bottom: 12px; text-align: center; }
.pool-form .van-button { margin-top: 12px; }
</style>

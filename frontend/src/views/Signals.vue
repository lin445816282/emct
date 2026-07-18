<template>
  <div class="signals-page">
    <!-- 信号类型卡片 + 下方股票 -->
    <div class="type-cards" v-if="signalsList.length">
      <!-- 卡片定义数组 -->
      <template v-for="type in typeDefs" :key="type.key">
        <div class="type-card" :class="[type.key, { expanded: expandedType === type.key }]" @click="toggleType(type.key)" v-if="typeCount[type.key] > 0 || type.key !== 'strong_sell'">
          <div class="type-row">
            <span class="type-label">{{ type.icon }} {{ type.label }}</span>
            <span class="type-num">{{ typeCount[type.key] }}</span>
            <span class="type-arrow">{{ expandedType === type.key ? '▲' : '▼' }}</span>
          </div>
          <!-- 展开：该类型股票列表 -->
          <div class="type-signals" v-if="expandedType === type.key">
            <van-card
              v-for="s in getSignals(type.key)" :key="s.id"
              :title="s.name + ' (' + s.code + ')'"
              :thumb="''"
              class="signal-card"
              @click.stop="toggleExpand(s.id)"
            >
              <template #desc>
                <van-tag :type="typeColor(s.signal_type)" size="small">{{ signalLabel(s.signal_type) }}</van-tag>
                <span class="score">评分 {{ s.strength || s.score }}</span>
                <span class="price" v-if="s.price_ref">参考价 ¥{{ s.price_ref }}</span>
                <span class="expand-arrow">{{ expandedIds.has(s.id) ? '▲' : '▼' }}</span>
              </template>
              <template #footer>
                <div class="card-footer">
                  <div class="reason-list" v-show="expandedIds.has(s.id)">
                    <van-tag
                      v-for="(r, i) in (s.reason || '').split(' | ')"
                      :key="i"
                      size="small"
                      plain
                      class="reason-tag"
                    >{{ r.replace(/^\[.*?\]\s*/, '') }}</van-tag>
                  </div>
                  <div class="btns" v-if="s.status === 'pending'">
                    <van-button size="small" type="primary" :disabled="!isTradingTime()" @click.stop="doOrder(s)">下单</van-button>
                    <van-button size="small" type="danger" plain @click.stop="doConfirm(s.id)">确认</van-button>
                    <van-button size="small" plain @click.stop="doExpire(s.id)">忽略</van-button>
                  </div>
                  <van-tag v-else :type="statusColor(s.status)">{{ s.status }}</van-tag>
                </div>
              </template>
            </van-card>
          </div>
        </div>
      </template>
    </div>

    <!-- 信号列表（卡片全部折叠时显示全部） -->
    <div class="summary-bar">
      <span>今日信号 <b>{{ signalsList.length }}</b></span>
      <div style="display:flex;gap:6px">
        <van-button v-if="simStore.enabled && signalsList.length" size="small" type="danger" :loading="batching" :disabled="!isTradingTime()" @click="doBatchOrder">
          一键跟单
        </van-button>
        <van-button v-if="!signalsList.length" size="small" type="warning" :loading="scanning" @click="doScan">
          开始扫描
        </van-button>
      </div>
    </div>
    <div v-if="simStore.enabled && !isTradingTime() && signalsList.length" style="text-align:center;padding:4px 0;color:#999;font-size:12px">
      ⏸ 非交易时间 · 开盘 9:30-11:30 / 13:00-15:00
    </div>

    <van-empty v-if="!signalsList.length && !scanning" description="点击「分析扫描」生成信号" />

    <!-- 一键跟单预览弹窗 -->
    <van-dialog v-model:show="showBatchPreview" title="一键跟单预览" show-cancel-button
      @confirm="doBatchConfirm" confirm-button-text="确认下单" cancel-button-text="取消"
      :confirm-loading="batching">
      <div class="batch-preview">
        <div class="batch-hint">将对以下 {{ batchList.length }} 只股票下单（每只100股）：</div>
        <div class="batch-item" v-for="b in batchList" :key="b.id">
          <div class="bi-check">
            <input type="checkbox" v-model="b.checked" />
          </div>
          <div class="bi-info">
            <span class="bi-name">{{ b.name }}</span>
            <van-tag size="mini" :type="b.signal_type.includes('buy')?'danger':'success'">
              {{ signalLabel(b.signal_type) }}
            </van-tag>
          </div>
          <div class="bi-price">¥{{ b.price_ref || '--' }}</div>
        </div>
      </div>
    </van-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { signals } from '../api/index.js'
import { showToast } from 'vant'
import { useSimStore } from '../stores/sim'
import { signalBadge } from '../stores/signalBadge'

const simStore = useSimStore()

// A股交易时间：工作日 9:30-11:30 / 13:00-15:00
function isTradingTime() {
  const now = new Date()
  const day = now.getDay()
  if (day === 0 || day === 6) return false
  const h = now.getHours(), m = now.getMinutes()
  const t = h * 60 + m
  return (t >= 570 && t <= 690) || (t >= 780 && t <= 900)  // 9:30-11:30, 13:00-15:00
}

const signalsList = ref([])
const scanning = ref(false)
const batching = ref(false)          // 一键跟单loading
const showBatchPreview = ref(false)  // 跟单预览弹窗
const batchList = ref([])            // 跟单预览列表
const expandedIds = ref(new Set())
const expandedType = ref(null)

const typeDefs = [
  { key: 'strong_buy', label: '强烈买入', icon: '🟢' },
  { key: 'buy', label: '买入', icon: '🟢' },
  { key: 'hold', label: '观望', icon: '⚪' },
  { key: 'sell', label: '卖出', icon: '🔴' },
  { key: 'strong_sell', label: '强烈卖出', icon: '🔴' },
]

function toggleType(key) {
  expandedType.value = expandedType.value === key ? null : key
}
function getSignals(key) {
  return signalsList.value.filter(s => s.signal_type === key)
}

function toggleExpand(id) {
  const s = new Set(expandedIds.value)
  s.has(id) ? s.delete(id) : s.add(id)
  expandedIds.value = s
}

const typeCount = computed(() => {
  const c = { strong_buy: 0, buy: 0, hold: 0, sell: 0, strong_sell: 0 }
  signalsList.value.forEach(s => {
    if (c[s.signal_type] !== undefined) c[s.signal_type]++
  })
  return c
})

onMounted(refresh)
onMounted(() => {
  // 盘中自动刷新信号：每60秒
  const timer = setInterval(() => {
    if (isTradingTime()) refresh()
  }, 60000)
  onUnmounted(() => clearInterval(timer))
})

async function refresh() {
  const data = await signals.list('pending')
  signalsList.value = data.rows || []
  signalBadge.value = signalsList.value.length
}

async function doScan() {
  scanning.value = true
  try {
    const data = await signals.scan()
    showToast(`扫描完成: ${data.saved}只`)
    refresh()
  } catch {
    showToast('扫描失败')
  }
  scanning.value = false
}

async function doConfirm(id) { await signals.confirm(id); showToast('已确认'); refresh() }
async function doExpire(id) { await signals.expire(id); refresh() }

async function doOrder(s) {
  const dir = s.signal_type.includes('buy') ? 'buy' : s.signal_type.includes('sell') ? 'sell' : 'buy'
  const price = s.price_ref || 0
  const vol = 100

  if (simStore.enabled) {
    // 模拟模式：直接成交，用信号真实价格
    try {
      const result = await simStore.quickTrade(s.code, s.name, dir, price, vol)
      if (result.ok) {
        showToast(`已成交 #${result.order_id} ${dir==='buy'?'买入':'卖出'} ${s.name} ${vol}股@${price}`)
        signals.confirm(s.id) // 自动确认信号
      } else {
        showToast(result.error || '交易失败')
      }
    } catch { showToast('交易失败') }
  } else {
    // 实盘模式：创建订单待执行
    try {
      const res = await fetch(`/emct/api/orders/create?signal_id=${s.id}&code=${s.code}&name=${encodeURIComponent(s.name)}&direction=${dir}&price=${price}&volume=${vol}`, { method: 'POST' })
      const data = await res.json()
      if (data.ok) {
        showToast(`订单已创建 #${data.order_id}`)
      } else {
        showToast(data.error || '创建失败')
      }
    } catch { showToast('创建失败') }
  }
}

// 一键跟单：打开预览弹窗
function doBatchOrder() {
  const pending = signalsList.value.filter(s => s.status === 'pending')
  if (!pending.length) { showToast('没有待处理信号'); return }
  batchList.value = pending.map(s => ({
    ...s, checked: true  // 默认全选
  }))
  showBatchPreview.value = true
}

// 确认执行跟单
async function doBatchConfirm() {
  batching.value = true
  const selected = batchList.value.filter(b => b.checked)
  let ok = 0, fail = 0
  for (const s of selected) {
    try {
      const dir = s.signal_type.includes('buy') ? 'buy' : s.signal_type.includes('sell') ? 'sell' : 'buy'
      const price = s.price_ref || 0
      if (simStore.enabled) {
        const result = await simStore.quickTrade(s.code, s.name, dir, price, 100)
        if (result.ok) { ok++; signals.confirm(s.id) } else { fail++ }
      } else {
        const res = await fetch(`/emct/api/orders/create?signal_id=${s.id}&code=${s.code}&name=${encodeURIComponent(s.name)}&direction=${dir}&price=${price}&volume=100`, { method: 'POST' })
        const data = await res.json()
        if (data.ok) ok++; else fail++
      }
    } catch { fail++ }
  }
  batching.value = false
  showBatchPreview.value = false
  showToast(`完成: ${ok}成功${fail ? ', '+fail+'失败' : ''}`)
  refresh()
}

function typeColor(t) {
  return { strong_buy: 'danger', buy: 'warning', hold: 'default', sell: 'primary', strong_sell: 'success' }[t] || 'default'
}
function signalLabel(t) {
  return { strong_buy: '强烈买入', buy: '买入', hold: '持有', sell: '卖出', strong_sell: '强烈卖出' }[t] || t
}
function statusColor(s) { return s === 'confirmed' ? 'success' : s === 'executed' ? 'primary' : 'warning' }
</script>

<style scoped>
.summary-bar { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; font-size: 13px; color: #666; }
.summary-bar b { color: #e74c3c; }
/* 信号类型卡片 */
.type-cards {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px;
}
.type-card {
  border-radius: 10px;
  background: #f8f9fb;
  cursor: pointer;
  transition: transform .15s, box-shadow .15s;
  overflow: hidden;
}
.type-card:active { transform: scale(0.98); }
.type-card.expanded {
  box-shadow: 0 0 0 2px #1989fa;
}
.type-row {
  display: flex;
  align-items: center;
  padding: 14px 16px;
  gap: 10px;
}
.type-label {
  font-size: 13px;
  color: #666;
  font-weight: 500;
  flex: 1;
}
.type-num {
  font-size: 22px;
  font-weight: 700;
}
.type-arrow {
  font-size: 11px;
  color: #999;
  margin-left: 4px;
}
/* 展开区信号 */
.type-signals {
  border-top: 1px solid rgba(0,0,0,.06);
  padding: 8px 12px 12px;
  background: rgba(255,255,255,.5);
}
.type-card.strong-buy { background: #fff0f0; }
.type-card.strong-buy .type-num { color: #e53e3e; }
.type-card.buy { background: #fff7ed; }
.type-card.buy .type-num { color: #ea580c; }
.type-card.hold { background: #f0f0f0; }
.type-card.hold .type-num { color: #999; }
.type-card.sell { background: #e8f5e9; }
.type-card.sell .type-num { color: #2e7d32; }
.type-card.strong-sell { background: #e3f2fd; }
.type-card.strong-sell .type-num { color: #1565c0; }
.scan-summary-old { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 8px; }
.score { margin-left: 8px; color: #e67e22; font-size: 12px; }
.price { margin-left: 8px; color: #333; font-size: 12px; }
.signal-card { cursor: pointer; }
.expand-arrow { margin-left: auto; color: #999; font-size: 11px; }
.card-footer { display: flex; flex-direction: column; gap: 6px; }
.reason-list { display: flex; flex-wrap: wrap; gap: 4px; }
.reason-tag { --van-tag-font-size: 11px; }
.btns { display: flex; gap: 8px; }

/* 一键跟单预览 */
.batch-preview { padding: 0 16px 8px; max-height: 50vh; overflow-y: auto; }
.batch-hint { font-size: 12px; color: #888; margin-bottom: 10px; text-align: center; }
.batch-item { display: flex; align-items: center; gap: 8px; padding: 8px 0; border-bottom: 1px solid #f5f5f5; }
.batch-item:last-child { border-bottom: none; }
.bi-check input { width: 18px; height: 18px; accent-color: #1989fa; }
.bi-info { flex: 1; display: flex; align-items: center; gap: 6px; }
.bi-name { font-size: 13px; font-weight: 500; }
.bi-price { font-size: 13px; color: #e74c3c; font-weight: 600; }
</style>

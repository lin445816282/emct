<template>
  <div class="dashboard">
    <!-- 账户概览卡片 -->
    <div class="account-card" v-if="simStore.enabled">
      <div class="ac-header">
        <span>💰 模拟账户</span>
        <van-tag size="mini" type="warning">模拟</van-tag>
      </div>
      <div class="ac-grid">
        <div class="ac-item">
          <span class="ac-label">总资产</span>
          <span class="ac-val">¥{{ fmt(acct.total_value || acct.cash) }}</span>
        </div>
        <div class="ac-item">
          <span class="ac-label">可用现金</span>
          <span class="ac-val">¥{{ fmt(acct.cash) }}</span>
        </div>
        <div class="ac-item">
          <span class="ac-label">持仓市值</span>
          <span class="ac-val">¥{{ fmt(acct.market_value) }}</span>
        </div>
        <div class="ac-item">
          <span class="ac-label">累计盈亏</span>
          <span class="ac-val" :class="pnlClass">¥{{ fmt(acct.total_pnl) }}</span>
        </div>
      </div>
      <div class="ac-bar" :class="pnlClass">
        <span>收益率 {{ pnlPct >= 0 ? '+' : '' }}{{ pnlPct }}%</span>
        <span>初始 ¥{{ fmt(acct.initial_cash) }}</span>
      </div>
    </div>

    <!-- 股票池扫描统计 -->
    <div class="pool-card" v-if="pool.total">
      <div class="pool-title">📊 股票池</div>
      <div class="pool-grid">
        <div class="pool-item">
          <span class="pool-num">{{ pool.total }}</span>
          <span class="pool-label">只标的</span>
        </div>
        <div class="pool-item">
          <span class="pool-num">{{ pool.active }}</span>
          <span class="pool-label">已启用</span>
        </div>
        <div class="pool-item" v-if="pool.last_sync">
          <span class="pool-num">{{ pool.last_sync.slice(5) }}</span>
          <span class="pool-label">数据至</span>
        </div>
      </div>
    </div>

    <!-- 今日信号摘要 -->
    <div class="section">
      <div class="sec-title" @click="$router.push('/signals')">
        <span>📡 今日信号</span>
        <van-tag v-if="signals.length" size="small" type="primary">{{ signals.length }}</van-tag>
        <span class="sec-arrow">查看 ›</span>
      </div>
      <div class="sig-summary" v-if="signals.length">
        <div class="sig-row" v-for="t in typeDefs" :key="t.key" v-show="sigCount[t.key]">
          <span class="sig-icon">{{ t.icon }}</span>
          <span class="sig-label">{{ t.label }}</span>
          <span class="sig-num">{{ sigCount[t.key] }}</span>
          <div class="sig-stocks">
            <van-tag v-for="s in topStocks(t.key)" :key="s.code" size="mini" plain class="sig-stock-tag"
              @click.stop="$router.push('/signals')">{{ s.name }}</van-tag>
          </div>
        </div>
      </div>
      <div v-else class="empty-hint" @click="$router.push('/signals')">
        今日暂无信号，点击扫描 →
      </div>
    </div>

    <!-- 最近成交 -->
    <div class="section">
      <div class="sec-title" @click="$router.push('/orders')">
        <span>📋 最近成交</span>
        <span class="sec-arrow">查看 ›</span>
      </div>
      <div v-if="recentOrders.length" class="order-list">
        <div v-for="o in recentOrders" :key="o.id" class="order-item"
             :class="o.direction === 'buy' ? 'buy' : 'sell'"
             @click="$router.push('/review')">
          <div class="oi-main">
            <span class="oi-name">{{ o.name || o.code }}</span>
            <van-tag size="mini" :type="o.direction === 'buy' ? 'danger' : 'success'">
              {{ o.direction === 'buy' ? '买' : '卖' }}
            </van-tag>
          </div>
          <div class="oi-detail">
            <span>{{ o.volume }}股 @¥{{ fmt(o.price) }}</span>
            <span class="oi-date">{{ fmtDate(o.created_at) }}</span>
          </div>
        </div>
      </div>
      <div v-else class="empty-hint" @click="$router.push('/orders')">
        暂无成交记录
      </div>
    </div>

    <!-- 市场状态 -->
    <div class="section" v-if="marketRegime">
      <div class="sec-title">
        <span>🌍 市场状态</span>
      </div>
      <div class="market-card" :class="marketRegime.can_trade ? 'trade' : 'pause'">
        <span>{{ marketRegime.can_trade ? '✅ 可交易' : '🚫 暂停' }}</span>
        <span class="market-msg">{{ marketRegime.msg }}</span>
      </div>
    </div>

    <!-- 快速操作 -->
    <div class="section">
      <div class="quick-actions">
        <van-button size="small" type="primary" icon="scan" @click="$router.push('/signals'); setTimeout(() => document.querySelector('.signal-scan-btn')?.click(), 300)">
          扫描信号
        </van-button>
        <van-button size="small" type="warning" icon="play" @click="$router.push('/sim')">
          运行回测
        </van-button>
        <van-button size="small" type="default" icon="chart-trending-o" @click="$router.push('/review')">
          查看复盘
        </van-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useSimStore } from '../stores/sim'
import { Tag, Button } from 'vant'

const simStore = useSimStore()

const acct = ref({ cash: 0, market_value: 0, total_pnl: 0, total_value: 0, initial_cash: 1000000 })
const signals = ref([])
const recentOrders = ref([])
const marketRegime = ref(null)
const pool = ref({ total: 0, active: 0, last_sync: '' })

const pnlPct = computed(() => {
  const pnl = acct.value.total_pnl || 0
  const base = acct.value.initial_cash || 1000000
  return base ? (pnl / base * 100).toFixed(2) : '0'
})
const pnlClass = computed(() => (acct.value.total_pnl || 0) >= 0 ? 'up' : 'down')

const typeDefs = [
  { key: 'strong_buy', label: '强烈买入', icon: '🟢' },
  { key: 'buy', label: '买入', icon: '🟢' },
  { key: 'hold', label: '观望', icon: '⚪' },
  { key: 'sell', label: '卖出', icon: '🔴' },
  { key: 'strong_sell', label: '强烈卖出', icon: '🔴' },
]

const sigCount = computed(() => {
  const c = {}
  signals.value.forEach(s => {
    c[s.signal_type] = (c[s.signal_type] || 0) + 1
  })
  return c
})

function topStocks(key) {
  return signals.value.filter(s => s.signal_type === key).slice(0, 3)
}

function fmt(v) {
  if (v == null) return '0'
  return Number(v).toLocaleString('zh-CN', { maximumFractionDigits: 0 })
}

function fmtDate(d) {
  if (!d) return ''
  return d.slice(5, 10)  // MM-DD
}

onMounted(async () => {
  // 并行加载
  try {
    const [ar, sr, or_, mr, pr] = await Promise.all([
      fetch('/emct/api/sim/account').then(r => r.json()),
      fetch('/emct/api/signals?status=pending').then(r => r.json()),
      fetch('/emct/api/sim/orders?limit=5').then(r => r.json()),
      fetch('/emct/api/sim/market-regime').then(r => r.json()),
      fetch('/emct/api/stock-pool/count').then(r => r.json()),
    ])
    acct.value = ar
    signals.value = (sr.signals || sr.rows || sr || []).filter(s => s.status === 'pending')
    recentOrders.value = (or_.rows || []).filter(o => o.order_status === 'filled').slice(0, 5)
    marketRegime.value = mr
    pool.value = pr
  } catch {}
})
</script>

<style scoped>
.dashboard { display: flex; flex-direction: column; gap: 10px; padding-bottom: 10px; }

/* 账户卡片 */
.account-card {
  background: linear-gradient(135deg, #1a1a2e, #16213e);
  border-radius: 14px; padding: 16px; color: #fff;
}
.ac-header { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; font-size: 14px; font-weight: 600; }
.ac-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.ac-item { text-align: center; }
.ac-label { font-size: 11px; opacity: .7; display: block; margin-bottom: 4px; }
.ac-val { font-size: 18px; font-weight: 700; display: block; }
.ac-bar { margin-top: 12px; padding-top: 10px; border-top: 1px solid rgba(255,255,255,.1); display: flex; justify-content: space-between; font-size: 11px; opacity: .8; }
.ac-bar.up { color: #ff6b6b; }
.ac-bar.down { color: #51cf66; }

/* common section */
.section { background: #fff; border-radius: 12px; padding: 14px; box-shadow: 0 1px 3px rgba(0,0,0,.04); }
.sec-title { display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 600; color: #333; margin-bottom: 10px; cursor: pointer; }
.sec-arrow { margin-left: auto; font-size: 11px; color: #999; }

/* 信号摘要 */
.sig-summary { display: flex; flex-direction: column; gap: 8px; }
.sig-row { display: flex; align-items: center; gap: 6px; padding: 6px 0; border-bottom: 1px solid #f5f5f5; }
.sig-row:last-child { border-bottom: none; }
.sig-icon { font-size: 14px; }
.sig-label { font-size: 12px; color: #666; min-width: 60px; }
.sig-num { font-size: 16px; font-weight: 700; color: #333; min-width: 24px; text-align: center; }
.sig-stocks { display: flex; gap: 4px; flex-wrap: wrap; flex: 1; }
.sig-stock-tag { cursor: pointer; }

/* 成交列表 */
.order-list { display: flex; flex-direction: column; gap: 6px; }
.order-item { padding: 8px 10px; border-radius: 8px; border-left: 3px solid #eee; cursor: pointer; }
.order-item.buy { border-left-color: #ff6b6b; background: #fff5f5; }
.order-item.sell { border-left-color: #51cf66; background: #f5fff5; }
.oi-main { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.oi-name { font-size: 13px; font-weight: 500; }
.oi-detail { display: flex; justify-content: space-between; font-size: 11px; color: #999; }

/* 市场状态 */
.market-card { display: flex; justify-content: space-between; align-items: center; padding: 10px 12px; border-radius: 8px; font-size: 13px; font-weight: 600; }
.market-card.trade { background: #f0fdf4; color: #16a34a; }
.market-card.pause { background: #fef2f2; color: #dc2626; }
.market-msg { font-size: 11px; font-weight: 400; max-width: 60%; text-align: right; }

/* 快速操作 */
.quick-actions { display: flex; gap: 8px; flex-wrap: wrap; }

/* 股票池卡片 */
.pool-card {
  background: #fff; border-radius: 12px; padding: 14px; box-shadow: 0 1px 3px rgba(0,0,0,.04);
}
.pool-title { font-size: 13px; font-weight: 600; color: #333; margin-bottom: 10px; }
.pool-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; }
.pool-item { text-align: center; }
.pool-num { font-size: 22px; font-weight: 700; color: #1989fa; display: block; }
.pool-label { font-size: 11px; color: #999; }

/* 空状态 */
.empty-hint { font-size: 12px; color: #bbb; text-align: center; padding: 12px 0; cursor: pointer; }
.empty-hint:hover { color: #1989fa; }

/* pnl颜色 */
.up { color: #ff6b6b !important; }
.down { color: #51cf66 !important; }
</style>

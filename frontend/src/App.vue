<template>
  <div class="app">
    <van-nav-bar title="EMCT 交易系统" fixed placeholder>
      <template #right>
        <div :class="['mode-switch', simStore.enabled ? 'sim' : 'real']">
          <van-switch v-model="simStore.enabled" size="20" active-color="#1989fa" @change="onSimToggle" />
          <span class="mode-label">{{ simStore.enabled ? '模拟' : '实盘' }}</span>
        </div>
      </template>
    </van-nav-bar>

    <!-- 模拟账户栏 -->
    <div v-if="simStore.enabled" class="sim-bar" @click="showSimDetail = true">
      <span>💰 ¥{{ fmt(simStore.totalValue) }}</span>
      <span class="pnl" :class="simStore.totalPnl >= 0 ? 'up' : 'down'">
        {{ simStore.totalPnl >= 0 ? '+' : '' }}¥{{ fmt(simStore.totalPnl) }}
        ({{ simStore.totalPnlPct >= 0 ? '+' : '' }}{{ simStore.totalPnlPct }}%)
      </span>
      <span style="font-size:10px;color:#999;margin-left:auto">点击管理 ›</span>
    </div>

    <div class="content">
      <router-view />
    </div>

    <van-tabbar v-model="active" route>
      <van-tabbar-item icon="home-o" to="/dashboard">总览</van-tabbar-item>
      <van-tabbar-item icon="points" to="/signals" :badge="signalBadge || ''">信号</van-tabbar-item>
      <van-tabbar-item icon="balance-list" to="/positions">持仓</van-tabbar-item>
      <van-tabbar-item icon="orders-o" to="/orders">订单</van-tabbar-item>
      <van-tabbar-item icon="chart-trending-o" to="/review">复盘</van-tabbar-item>
      <van-tabbar-item icon="gem-o" to="/sim">模拟</van-tabbar-item>
      <van-tabbar-item icon="setting-o" to="/settings">设置</van-tabbar-item>
    </van-tabbar>

    <!-- 模拟账户弹窗 -->
    <van-popup v-model:show="showSimDetail" position="bottom" :style="{ height: '50%' }">
      <div class="sim-popup">
        <div class="pop-title">模拟账户</div>
        <div class="pop-row"><span>总资产</span><span class="bold">¥{{ fmt(simStore.account.total_value || simStore.account.cash) }}</span></div>
        <div class="pop-row"><span>现金</span><span>¥{{ fmt(simStore.account.cash) }}</span></div>
        <div class="pop-row"><span>持仓市值</span><span>¥{{ fmt(simStore.account.market_value) }}</span></div>
        <div class="pop-row"><span>累计盈亏</span><span :class="simStore.totalPnl >= 0 ? 'up' : 'down'">{{ simStore.totalPnl >= 0 ? '+' : '' }}¥{{ fmt(simStore.totalPnl) }}</span></div>
        <div class="pop-row"><span>初始资金</span><span>¥{{ fmt(simStore.account.initial_cash) }}</span></div>

        <div class="pop-actions">
          <van-button size="small" plain type="danger" @click="doReset">重置账户</van-button>
        </div>

        <div v-if="simStore.positions.length" class="pop-positions">
          <div class="pop-title">当前持仓</div>
          <div v-for="p in simStore.positions" :key="p.code" class="pos-item">
            <div class="pos-info">
              <span class="pos-name">{{ p.name }}</span>
              <span class="pos-code">{{ p.code }}</span>
            </div>
            <div class="pos-data">
              <span>{{ p.volume }}股 @¥{{ p.avg_cost }}</span>
              <span class="pnl" :class="p.profit_loss >= 0 ? 'up' : 'down'">
                ¥{{ fmt(p.profit_loss) }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </van-popup>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useSimStore } from './stores/sim'
import { showToast } from 'vant'
import { signalBadge } from './stores/signalBadge'

const simStore = useSimStore()
const active = ref(0)
const showSimDetail = ref(false)
let autoCheckTimer = null

function isTradingTime() {
  const now = new Date()
  const d = now.getDay()
  if (d === 0 || d === 6) return false
  const t = now.getHours() * 60 + now.getMinutes()
  return (t >= 570 && t <= 690) || (t >= 780 && t <= 900)  // 9:30-11:30 13:00-15:00
}

onMounted(() => {
  if (simStore.enabled) simStore.refresh()
  startAutoCheck()
})

onUnmounted(() => {
  if (autoCheckTimer) clearInterval(autoCheckTimer)
})

function startAutoCheck() {
  if (autoCheckTimer) clearInterval(autoCheckTimer)
  autoCheckTimer = setInterval(async () => {
    if (simStore.enabled && isTradingTime()) {
      try {
        const r = await fetch('/emct/api/sim/auto-check', { method: 'POST' })
        const data = await r.json()
        if (data.triggered > 0) {
          showToast(`🚨 止损/止盈触发 ${data.triggered} 笔`)
          simStore.refresh()
        }
      } catch { /* */ }
    }
  }, 30000)
}

function onSimToggle(val) {
  showToast(val ? '已切换模拟交易' : '已切换实盘交易')
  if (val) simStore.refresh()
}

async function doReset() {
  await simStore.resetAccount(1000000)
  showToast('账户已重置')
  showSimDetail.value = false
}

function fmt(v) {
  if (v == null) return '0'
  return Number(v).toLocaleString('zh-CN', { maximumFractionDigits: 0 })
}
</script>

<style scoped>
.app { min-height: 100vh; padding-bottom: 50px; }
.content { padding: 8px 12px; }

.mode-switch {
  display: flex; align-items: center; gap: 4px;
  padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 600;
}
.mode-switch.sim {
  background: #e6f7ff; border: 1px solid #91d5ff;
}
.mode-switch.real {
  background: #fff2f0; border: 1px solid #ffccc7;
}
.mode-switch.sim .mode-label { color: #1890ff; }
.mode-switch.real .mode-label { color: #ff4d4f; }

.sim-bar {
  display: flex; align-items: center; gap: 8px;
  background: linear-gradient(135deg, #f0f7ff, #e6f7ff);
  padding: 6px 14px; margin-top:4px;
  font-size: 13px; font-weight: 600; cursor: pointer;
}
.sim-bar .pnl { font-size: 12px; }
.up { color: #e74c3c; }
.down { color: #2ecc71; }

.sim-popup { padding: 16px; }
.pop-title { font-size: 15px; font-weight: 700; margin-bottom: 10px; color: #333; }
.pop-row { display: flex; justify-content: space-between; padding: 8px 0; font-size: 13px; border-bottom: 1px solid #f5f5f5; }
.pop-row .bold { font-weight: 700; }
.pop-actions { margin: 14px 0; display: flex; gap: 8px; }
.pop-positions { margin-top: 8px; }
.pos-item { padding: 8px 0; border-bottom: 1px solid #f0f0f0; }
.pos-item:last-child { border-bottom: none; }
.pos-info { display: flex; align-items: center; gap: 6px; margin-bottom: 2px; }
.pos-name { font-weight: 500; font-size: 13px; }
.pos-code { font-size: 11px; color: #999; }
.pos-data { display: flex; justify-content: space-between; font-size: 12px; color: #666; }
</style>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: #f5f6f8; font-family: -apple-system, sans-serif; }
</style>

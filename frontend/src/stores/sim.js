import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useSimStore = defineStore('sim', () => {
  const enabled = ref(true)  // 默认模拟模式
  const account = ref({ cash: 1000000, market_value: 0, total_pnl: 0, total_pnl_pct: 0, initial_cash: 1000000, total_value: 1000000 })
  const positions = ref([])

  const totalValue = computed(() => account.value.total_value || account.value.cash + account.value.market_value)
  const totalPnl = computed(() => account.value.total_pnl || 0)
  const totalPnlPct = computed(() => account.value.total_pnl_pct || 0)

  async function fetchAccount() {
    try {
      const r = await fetch('/emct/api/sim/account')
      account.value = await r.json()
    } catch { /* */ }
  }

  async function fetchPositions() {
    try {
      const r = await fetch('/emct/api/sim/positions')
      const data = await r.json()
      positions.value = data.rows || []
    } catch { /* */ }
  }

  async function refresh() {
    await Promise.all([fetchAccount(), fetchPositions()])
  }

  async function quickTrade(code, name, direction, price, volume) {
    const params = new URLSearchParams({ code, name, direction, price, volume })
    const r = await fetch(`/emct/api/sim/quick-trade?${params}`, { method: 'POST' })
    const data = await r.json()
    if (data.ok) await refresh()
    return data
  }

  async function resetAccount(cash = 1000000) {
    const params = new URLSearchParams({ initial_cash: String(cash) })
    const r = await fetch(`/emct/api/sim/account/reset?${params}`, { method: 'POST' })
    const data = await r.json()
    if (data.ok) await refresh()
    return data
  }

  async function refreshPrices() {
    try {
      const r = await fetch('/emct/api/sim/refresh-prices', { method: 'POST' })
      await r.json()
    } catch { /* 价格刷新失败不影响数据加载 */ }
    await refresh()
  }

  return { enabled, account, positions, totalValue, totalPnl, totalPnlPct,
           fetchAccount, fetchPositions, refresh, quickTrade, resetAccount, refreshPrices }
})

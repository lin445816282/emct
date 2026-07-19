const BASE = '/emct/api'

export async function get(url) {
  const res = await fetch(BASE + url)
  return res.json()
}

export async function post(url, data) {
  const res = await fetch(BASE + url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  })
  return res.json()
}

// Stock pool
export const stockPool = {
  list: (sector) => get('/stock-pool' + (sector ? `?sector=${sector}` : '')),
  add: (data) => post('/stock-pool/add?' + new URLSearchParams(data)),
  toggle: (code) => post('/stock-pool/toggle?code=' + code),
}

// Signals
export const signals = {
  list: (status, signalType) => {
    let q = ''
    if (status) q += `status=${status}&`
    if (signalType) q += `signal_type=${signalType}&`
    return get('/signals' + (q ? '?' + q.slice(0, -1) : ''))
  },
  scan: () => post('/signals/scan'),
  ranked: () => get('/signals/ranked'),
  analyze: (code, name) => get(`/signals/analyze/${code}?name=${encodeURIComponent(name || '')}`),
  confirm: (id) => post(`/signals/${id}/confirm`),
  expire: (id) => post(`/signals/${id}/expire`),
}

// Positions
export const positions = {
  list: () => get('/positions'),
  summary: () => get('/positions/summary'),
}

// Orders
export const orders = {
  list: () => get('/orders'),
  create: (data) => post('/orders/create?' + new URLSearchParams(data)),
  execute: (id) => post(`/orders/${id}/execute`),
  cdpStatus: () => get('/orders/cdp/status'),
  updateStatus: (id, data) => post(`/orders/${id}/status?` + new URLSearchParams(data)),
}

// Review
export const review = {
  sync: () => post('/review/sync'),
  stats: () => get('/review/stats'),
  monthly: () => get('/review/monthly'),
  stocks: () => get('/review/stocks'),
  timeline: (limit = 30) => get(`/review/timeline?limit=${limit}`),
  summary: () => get('/review/summary'),
  addNote: (id, review, tags) => post(`/review/${id}/note?review=${encodeURIComponent(review)}&tags=${encodeURIComponent(tags || '')}`),
}

// Simulated Trading
export const sim = {
  account: () => get('/sim/account'),
  positions: () => get('/sim/positions'),
  orders: (limit = 30) => get(`/sim/orders?limit=${limit}`),
  createOrder: (data) => post('/sim/order/create?' + new URLSearchParams(data)),
  execute: (id) => post(`/sim/order/${id}/execute`),
  quickTrade: (data) => post('/sim/quick-trade?' + new URLSearchParams(data)),
  resetAccount: (cash) => post(`/sim/account/reset?initial_cash=${cash}`),
  deposit: (amount) => post(`/sim/account/deposit?amount=${amount}`),
}

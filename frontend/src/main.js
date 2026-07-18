import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHashHistory } from 'vue-router'
import App from './App.vue'

// Vant4
import 'vant/lib/index.css'
import { Button, Tab, Tabs, Card, Tag, Cell, CellGroup, Field, Form,
         Popup, Dialog, Notify, Toast, Empty, NavBar, Loading, Switch,
         Tabbar, TabbarItem, Progress, Slider } from 'vant'

import Dashboard from './views/Dashboard.vue'
import Signals from './views/Signals.vue'
import Positions from './views/Positions.vue'
import Orders from './views/Orders.vue'
import Review from './views/Review.vue'
import SimPage from './views/SimPage.vue'
import Settings from './views/Settings.vue'

const routes = [
  { path: '/', redirect: '/dashboard' },
  { path: '/dashboard', component: Dashboard },
  { path: '/signals', component: Signals },
  { path: '/positions', component: Positions },
  { path: '/orders', component: Orders },
  { path: '/review', component: Review },
  { path: '/sim', component: SimPage },
  { path: '/settings', component: Settings },
]

const router = createRouter({ history: createWebHashHistory(), routes })
const pinia = createPinia()
const app = createApp(App)

// 注册Vant组件
;[Button, Tab, Tabs, Card, Tag, Cell, CellGroup, Field, Form,
  Popup, Dialog, Notify, Toast, Empty, NavBar, Loading, Switch,
  Tabbar, TabbarItem, Progress, Slider
].forEach(c => app.use(c))

app.use(router).use(pinia).mount('#app')

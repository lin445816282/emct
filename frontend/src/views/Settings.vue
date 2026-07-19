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
      <div class="sec-title">
        <span>⚙️ 策略配置 <van-tag size="mini" type="default" v-if="cfgVersion">v{{ cfgVersion }}</van-tag></span>
        <van-button size="mini" icon="info-o" type="primary" plain @click="showDoc = true">📖 文档</van-button>
      </div>

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
            <div class="slider-item">
              <div class="slider-label"><span>🚫 熔断线</span><span class="w-pct">{{ cfg.circuit_breaker_pct }}%</span></div>
              <van-slider v-model="cfg.circuit_breaker_pct" :min="-30" :max="-5" :step="1" bar-height="4px" />
            </div>
            <div class="slider-item">
              <div class="slider-label"><span>⚠️ 谨慎回撤线</span><span class="w-pct">{{ cfg.caution_drawdown_pct }}%</span></div>
              <van-slider v-model="cfg.caution_drawdown_pct" :min="-15" :max="-3" :step="1" bar-height="4px" />
            </div>
            <div class="slider-item">
              <div class="slider-label"><span>🔻 谨慎因子</span><span class="w-pct">{{ (cfg.caution_factor * 100).toFixed(0) }}%</span></div>
              <van-slider v-model="cfg.caution_factor" :min="0.2" :max="1.0" :step="0.1" bar-height="4px" />
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

    <!-- 策略文档弹窗 -->
    <van-popup v-model:show="showDoc" position="bottom" :style="{ height: '75%' }" round>
      <div class="doc-panel">
        <div class="doc-header">
          <span class="doc-title">📖 策略因子权重详解</span>
          <van-icon name="cross" size="20" @click="showDoc = false" />
        </div>
        <div class="doc-body">

          <!-- AI 结构化摘要 -->
          <div class="doc-ai-block">
            <div class="doc-ai-tag">🤖 AI 可解析摘要</div>
            <pre class="doc-ai-json">{
  "scoring": "weighted_sum(scores × weights)",
  "factors": [
    { "id":"ma_trend",   "range":[-100,100], "signal":"趋势方向",
      "logic":"MA5/10/20/60排列(+40)+乖离(+15)+斜率(+12)+MA60距(+20)" },
    { "id":"macd",       "range":[-100,100], "signal":"动能转折",
      "logic":"金叉/死叉(±60)+柱方向(±20)+零轴位(±20)" },
    { "id":"rsi",        "range":[-100,100], "signal":"超买超卖",
      "logic":"超卖<30(+50)→超买>70(-50)渐变+方向(+15)" },
    { "id":"bollinger",  "range":[-100,100], "signal":"通道位置",
      "logic":"触下轨(+60)→近中轨0→触上轨(-60)+带宽(+15)+中轨突破(±25)" },
    { "id":"volume",     "range":[-100,100], "signal":"量价配合",
      "logic":"量比>2涨(+30)/跌(-30)→>1.5涨(+20)/跌(-20)+量能趋势(+15)" },
    { "id":"momentum",   "range":[-100,100], "signal":"短期动量",
      "logic":"5日涨跌±(15~30)+20日反转(>10%超买-20,<-10%超跌+20)" }
  ],
  "note": "每因子满分±100; total_score ∈ [-100,100]; signal=strong_buy≥28|buy≥10|sell≤-10|strong_sell≤-28; 权重越高该因子分歧越大对总分扰动越强"
}</pre>
          </div>

          <!-- 人类可读详解 -->
          <div class="doc-human">
            <h3>🎯 总分公式</h3>
            <p><b>total_score = Σ(score_i × weight_i)</b></p>
            <p>每因子独立评分（-100~100），乘以权重后求和。阈值判定：<b>≥28 强烈买入</b> | <b>≥10 买入</b> | <b>≤-10 卖出</b> | <b>≤-28 强烈卖出</b>。</p>

            <h3>📊 六因子详解</h3>

            <div class="doc-factor">
              <h4>1. 均线趋势 (ma_trend) — 默认 18%</h4>
              <p><b>测什么：</b>中短期价格趋势方向与强度。考察 MA5/10/20/60 四条均线的排列形态、价格相对 MA5 的乖离率、MA5 的 5 日斜率、价格距 MA60（牛熊分界线）的距离。</p>
              <p><b>正分条件：</b>多头排列（MA5>MA10>MA20>MA60）、站上 MA5、MA5 斜率向上、股价高于 MA60。</p>
              <p><b>负分条件：</b>空头排列、跌破 MA5、MA5 斜率向下、股价深跌 MA60。</p>
              <p><b>调高影响：</b>↑ 趋势跟随更强，牛市顺势吃肉；熊市被均线误导追高概率增大。</p>
              <p><b>调低影响：</b>↓ 减少追涨杀跌，更依赖其他因子发现转折；可能错过明确趋势行情。</p>
              <p><b>推荐场景：</b>单边趋势市（牛/熊）↑ 至 22%+；震荡市 ↓ 至 12% 以下。</p>
            </div>

            <div class="doc-factor">
              <h4>2. MACD (macd) — 默认 18%</h4>
              <p><b>测什么：</b>趋势动能转折点。金叉/死叉信号（histogram 从负转正/正转负）、红绿柱放大缩小方向、MACD 线在零轴上方还是下方。</p>
              <p><b>正分条件：</b>刚发生金叉（+60）、红柱连续放大、MACD 线在零轴上方。</p>
              <p><b>负分条件：</b>刚发生死叉（-60）、绿柱连续放大、MACD 线在零轴下方。</p>
              <p><b>调高影响：</b>↑ 对转折点极度敏感，金叉死叉直接贡献 ±60 分——捕捉拐点快，但假信号也增多。</p>
              <p><b>调低影响：</b>↓ 忽略短期波动，减少假金叉/假死叉干扰；但真正的趋势反转可能延迟识别。</p>
              <p><b>推荐场景：</b>趋势转折期（股票池整体由跌转涨）↑ 至 20%+；趋势延续期 ↓ 至 14%。</p>
            </div>

            <div class="doc-factor">
              <h4>3. RSI (rsi) — 默认 14%</h4>
              <p><b>测什么：</b>超买超卖状态。14 日 RSI 数值（<30 超卖 = 反弹机会；>70 超买 = 回调风险）+ RSI 的 3 日方向变化。</p>
              <p><b>正分条件：</b>RSI < 30（+50 超卖机会）、RSI 30-40（+25 偏弱）、RSI 向上抬升。</p>
              <p><b>负分条件：</b>RSI > 70（-50 超买风险）、RSI 60-70（-25 偏强）。</p>
              <p><b>调高影响：</b>↑ 左侧抄底倾向强——超卖股得分暴增；但单边下跌中（RSI 持续<30）会反复抄底被套。</p>
              <p><b>调低影响：</b>↓ 减少左侧抄底，更倾向右侧确认；可能错过 V 型反转最佳买点。</p>
              <p><b>推荐场景：</b>震荡市 ↑ 至 18-20%；单边熊市 ↓ 至 8-10%（超卖≠见底）。</p>
            </div>

            <div class="doc-factor">
              <h4>4. 布林带 (bollinger) — 默认 17%</h4>
              <p><b>测什么：</b>价格在 20 日布林带通道中的相对位置（0=下轨，1=上轨），带宽收窄/扩张，价格突破中轨。</p>
              <p><b>正分条件：</b>触下轨（position<0.1，+60）、近下轨（<0.25，+30）、突破中轨向上（+25）、带宽收窄（+15 酝酿突破）。</p>
              <p><b>负分条件：</b>触上轨（>0.9，-60）、近上轨（>0.75，-30）、跌破中轨（-25）。</p>
              <p><b>调高影响：</b>↑ 均值回归偏好——低位买入、高位卖出；在趋势中（价格贴轨运行）会过早离场。</p>
              <p><b>调低影响：</b>↓ 减少逆势操作，更愿意在趋势中持仓；可能在高位接盘或低位不敢抄。</p>
              <p><b>推荐场景：</b>震荡市 ↑ 至 20-22%（均值回归有效）；单边趋势 ↓ 至 12-14%（贴轨是趋势加速信号不是反转信号）。</p>
            </div>

            <div class="doc-factor">
              <h4>5. 量价配合 (volume) — 默认 17%</h4>
              <p><b>测什么：</b>今日成交量相对 10 日均量的倍数 × 当日涨跌方向；5 日均量 vs 10 日均量的量能趋势。</p>
              <p><b>正分条件：</b>放量上涨（量比>2 涨+30，>1.5 涨+20）、量能趋势放大（5日均量>10日均量×1.2，+15）。</p>
              <p><b>负分条件：</b>放量下跌（量比>2 跌-30，>1.5 跌-20）。缩量（量比<0.5）微弱+5。</p>
              <p><b>调高影响：</b>↑ 更注重量能确认——量价配合好的信号更受偏爱；缩量突破会被惩罚。</p>
              <p><b>调低影响：</b>↓ 减少对成交量的依赖，更相信价格因子；可能在无量的虚涨中入场。</p>
              <p><b>推荐场景：</b>A 股一般保持 15-18%（量在价先是铁律）；极低换手率品种可适度降低。</p>
            </div>

            <div class="doc-factor">
              <h4>6. 动量 (momentum) — 默认 16%</h4>
              <p><b>测什么：</b>短期涨跌幅。5 日涨跌幅（趋势惯性）+ 20 日涨跌幅（均值回归判断——涨太多回调风险、跌太多反弹机会）。</p>
              <p><b>正分条件：</b>5 日涨 2-5%（+15~30，短期强势）、20 日跌超 10%（+20，超跌反弹机会）。</p>
              <p><b>负分条件：</b>5 日跌 2-5%（-15~30，短期弱势）、20 日涨超 10%（-20，涨幅过大回调风险）。</p>
              <p><b>调高影响：</b>↑ 增强追涨/抄底双向敏感度——短期走强的高分、超跌的也高分；可能反复抄底半山腰。</p>
              <p><b>调低影响：</b>↓ 减少对短期价格波动的反应，更依赖中长期因子（均线/MACD）判断。</p>
              <p><b>注意：</b>5 日和 20 日逻辑相反——5 日追涨（趋势）、20 日抄底（反转）。调高权重时两者同时放大，需观察实际效果。</p>
            </div>

            <h3>⚖️ 权重平衡铁律</h3>
            <p>六因子权重<b>必须合计 100%</b>。系统自动归一化以保证数学严谨性。滑块拖动一个因子时，其余因子按比例缩放保持合计 100%。</p>

            <h3>🔗 因子间交互</h3>
            <div class="doc-interact">
              <p><b>趋势三兄弟（均线 + MACD + 动量）</b>——同向时共振强烈（如多头排列+金叉+5日涨=高分），三者合计默认 52%。趋势市中提高可锐化方向判断。</p>
              <p><b>反转双雄（RSI + 布林带）</b>——天然均值回归倾向，超卖区+触下轨同时出现时抄底信号极强。震荡市中提高可多抓波段。</p>
              <p><b>量价独行（volume）</b>——独立维度，不与其他因子存在天然相关性。量价配合好的信号可信度更高，量价背离是危险信号。</p>
            </div>

            <h3>🐻 熊市因子说明</h3>
            <p>熊市因子（默认 0.5）<b>直接乘以总分缩小买入信号强度</b>：<code>adjusted_score = total_score × bear_factor</code>。设为 0.3 = 所有信号打三折，极致保守；设为 1.0 = 不衰减，正常评分。于市场整体弱势时压低可大幅减少假买入信号。</p>

            <h3>🔒 三层风控引擎说明</h3>
            <div class="doc-interact">
              <p><b>🛑 止损线（默认 -8%）：</b>个股跌破买入价触发无条件平仓。第一道防线。</p>
              <p><b>🚫 熔断线（默认 -10%）：</b>账户总回撤超此线→禁止新订单（熔断）。第二道防线。</p>
              <p><b>⚠️ 谨慎回撤线（默认 -5%）：</b>账户总回撤超此线→信号减弱。第三道防线。</p>
              <p><b>🔻 谨慎因子（默认 0.5）：</b>进入谨慎区后买入评分=原评分×谨慎因子。数值越低越保守。</p>
              <p>调整建议：<b>激进风格</b>→熔断线-15%、谨慎因子0.8；<b>保守风格</b>→熔断线-6%、谨慎因子0.3。</p>
            </div>

            <h3>💡 实战调参经验</h3>
            <div class="doc-tips">
              <p>• <b>信号太多但胜率低</b> → 提高信号阀值（strong_buy 28→35, buy 10→15），降低均线/MACD 权重，提高量价权重。</p>
              <p>• <b>信号太少错过行情</b> → 降低阀值，提高 RSI/布林带权重（左侧抄底型因子）。</p>
              <p>• <b>牛市跑不赢指数</b> → 提高均线+动量权重（趋势跟随），降低 RSI+布林带（过早止盈）。</p>
              <p>• <b>熊市亏损过大</b> → 降低总权重至 50% 以下、提高熊市因子至 0.3、提高信号阀值。</p>
              <p>• <b>震荡市反复被打脸</b> → 提高 RSI+布林带（均值回归）、降低 MACD+均线（假突破）。</p>
            </div>
          </div>
        </div>
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

const showDoc = ref(false)  // 策略文档弹窗
const cfgVersion = ref(0)   // 策略配置版本号

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
  max_single_amount: 5000, stop_loss_pct: -8, take_profit_pct: 15, max_hold_days: 10,
  circuit_breaker_pct: -15, caution_drawdown_pct: -7, caution_factor: 0.6
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
      cfgVersion.value = data.version || 0
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
    if (data.ok) {
      cfgVersion.value = data.version || (cfgVersion.value + 1)  // 保存后版本+1
      showToast('配置已保存')
    } else showToast('保存失败: ' + (data.error || ''))
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

/* 策略文档弹窗 */
.doc-panel { height: 100%; display: flex; flex-direction: column; }
.doc-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 14px 16px; border-bottom: 1px solid #eee; flex-shrink: 0;
}
.doc-title { font-size: 15px; font-weight: 700; }
.doc-body {
  flex: 1; overflow-y: auto; padding: 16px;
  -webkit-overflow-scrolling: touch;
}
.doc-ai-block {
  background: #1a1a2e; border-radius: 8px; padding: 12px; margin-bottom: 16px;
}
.doc-ai-tag {
  font-size: 12px; color: #7ec8e3; font-weight: 600; margin-bottom: 8px;
}
.doc-ai-json {
  font-size: 11px; color: #a8d8a8; line-height: 1.55;
  background: transparent; margin: 0; padding: 0;
  white-space: pre-wrap; word-break: break-all;
  font-family: 'SF Mono', 'Monaco', 'Menlo', monospace;
}
.doc-human h3 {
  font-size: 14px; color: #333; margin: 16px 0 8px;
  padding-bottom: 4px; border-bottom: 1px solid #f0f0f0;
}
.doc-human h4 {
  font-size: 13px; color: #1989fa; margin: 12px 0 4px;
}
.doc-human p {
  font-size: 12px; color: #555; line-height: 1.7; margin: 3px 0;
}
.doc-human code {
  background: #f5f5f5; padding: 1px 4px; border-radius: 3px;
  font-size: 11px; color: #e74c3c;
}
.doc-factor {
  background: #fafbfc; border-left: 3px solid #1989fa;
  padding: 8px 12px; margin: 8px 0; border-radius: 0 6px 6px 0;
}
.doc-interact {
  background: #fff8e1; padding: 10px 14px; border-radius: 6px;
}
.doc-interact p { font-size: 12px; line-height: 1.7; }
.doc-tips p {
  font-size: 12px; color: #555; line-height: 1.8; margin: 2px 0;
}
</style>

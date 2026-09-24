<template>
  <section class="page" data-module="alarm">
    <header class="page-head">
      <div>
        <h2>告警中心管理</h2>
        <p class="page-desc">值班看板按告警等级 × 处理状态汇总；数字可点开查看对应告警事件，交接班先看矩阵左上角。</p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="exportRows">导出告警中心清单</button>
      </div>
    </header>

    <!-- 值班看板 -->
    <section class="board-card">
      <header class="board-head">
        <div>
          <h3 class="board-title">值班看板</h3>
          <p class="board-hint">
            <template v-if="board && board.focus">
              交班提示：优先处理 <b>{{ board.focus.level }}</b> 等级「{{ board.focus.status }}」的
              {{ board.focus.count }} 条告警
            </template>
            <template v-else-if="board && !board.total">当前条件下暂无待跟进告警，可安心交接</template>
            <template v-else>矩阵按等级从高到低排列，数字可点开查看对应告警事件</template>
          </p>
        </div>
        <button class="btn ghost board-refresh" type="button" :disabled="boardLoading" @click="loadBoard">
          {{ boardLoading ? '汇总中…' : '刷新看板' }}
        </button>
      </header>

      <div v-if="boardError" class="board-feedback error-state">
        <span>看板数据拉取失败：{{ boardError }}</span>
        <button class="btn primary" type="button" @click="loadBoard">手动重试</button>
      </div>
      <div v-else-if="board && !board.total" class="board-feedback empty-state">
        <p class="feedback-title">暂无告警事件</p>
        <p class="feedback-desc">{{ boardEmptyHint }}</p>
      </div>
      <template v-else-if="board">
        <div class="table-scroll">
          <table class="matrix-table">
            <thead>
              <tr>
                <th class="matrix-corner">告警等级 ＼ 处理状态</th>
                <th v-for="status in board.statuses" :key="status">{{ status }}</th>
                <th class="matrix-total">小计</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in board.matrix" :key="row.level">
                <th class="matrix-level">
                  <span class="level-tag" :class="levelClass(row.level)">{{ row.level }}</span>
                </th>
                <td
                  v-for="status in board.statuses"
                  :key="status"
                  class="matrix-cell"
                  :class="{
                    'is-active': level === row.level && statusFilter === status,
                    'is-zero': !row.counts[status],
                    'is-hot': board.focus && board.focus.level === row.level && board.focus.status === status,
                  }"
                  role="button"
                  :title="cellTitle(row.level, status, row.counts[status])"
                  @click="drilldown(row.level, status)"
                >
                  <span class="cell-number">{{ row.counts[status] }}</span>
                  <span
                    v-if="board.focus && board.focus.level === row.level && board.focus.status === status"
                    class="hot-dot"
                    title="交班优先处理"
                  >优先</span>
                </td>
                <td class="matrix-cell is-total">{{ row.total }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="top-types">
          <h4 class="top-types-title">触发设备最多的告警类型 TOP{{ board.top_types.length }}</h4>
          <p v-if="!board.top_types.length" class="top-types-empty">当前条件下没有可统计的告警类型</p>
          <ol v-else class="top-types-list">
            <li v-for="(item, index) in board.top_types" :key="item.type" class="top-type-item">
              <span class="top-rank" :class="`rank-${index + 1}`">{{ index + 1 }}</span>
              <span class="top-type-name">{{ item.type }}</span>
              <span class="top-type-meta">{{ item.device_count }} 台设备 · {{ item.alarm_count }} 条告警</span>
            </li>
          </ol>
        </div>
      </template>
      <div v-else class="board-feedback empty-state">看板汇总加载中…</div>
    </section>

    <!-- 列表条件：等级切换会同步刷新看板与列表 -->
    <form class="filter-bar" @submit.prevent="applyFilters">
      <label class="filter-item">
        <span>告警编号</span>
        <input v-model="keywordInput" placeholder="按告警编号检索" />
      </label>
      <label class="filter-item">
        <span>告警等级</span>
        <select v-model="level" @change="onLevelChange">
          <option value="">全部等级</option>
          <option v-for="item in levelOptions" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
      <span v-if="statusFilter" class="status-chip">
        已下钻：{{ level || '全部等级' }} / {{ statusFilter }}
        <button class="link" type="button" @click="clearStatus">清除</button>
      </span>
    </form>

    <div ref="listSection">
      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in columns" :key="column">{{ column }}</th>
            <th>可执行动作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="String(row.id)">
            <td>{{ row['告警编号'] ?? '—' }}</td>
            <td>{{ row['告警类型'] ?? '—' }}</td>
            <td>
              <span class="level-tag" :class="levelClass(String(row['告警等级'] ?? ''))">{{ row['告警等级'] ?? '—' }}</span>
            </td>
            <td>{{ row['触发设备'] ?? '—' }}</td>
            <td>{{ row['触发时间'] ?? '—' }}</td>
            <td>{{ row.status ?? '—' }}</td>
            <td>{{ row['处理人'] ?? '—' }}</td>
            <td class="row-actions">
              <button
                v-for="action in actions"
                :key="action"
                class="link"
                type="button"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
            </td>
          </tr>
          <tr v-if="!rows.length">
            <td :colspan="columns.length + 1" class="empty-state">
              {{ hasActiveFilter ? '没有符合当前等级与状态条件的告警，可调整条件或重置后再看' : '暂无告警事件，新告警接入后会在这里列出' }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <footer class="page-foot">
      <span>共 {{ total }} 条告警事件</span>
      <span class="foot-side">
        <span v-if="listLoading" class="loading-text">列表加载中…</span>
        <span v-if="actionMessage" class="error-text">{{ actionMessage }}</span>
        <template v-if="listError">
          <span class="error-text">列表数据拉取失败：{{ listError }}</span>
          <button class="btn" type="button" @click="loadList">手动重试</button>
        </template>
      </span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type BoardSummary = {
  levels: string[]
  statuses: string[]
  matrix: { level: string; counts: Record<string, number>; total: number }[]
  total: number
  top_types: { type: string; device_count: number; alarm_count: number }[]
  focus: { level: string; status: string; count: number } | null
}

const ENDPOINT = '/api/alarm'
// 表头与硬编码单元格对应；处理状态直接取 status 字段，保证动作流转后立即更新。
const columns = ['告警编号', '告警类型', '告警等级', '触发设备', '触发时间', '处理状态', '处理人']
const actions = ['确认告警', '处置告警', '忽略告警']
// 后端不可用时仍能渲染等级下拉；汇总接口成功后会与返回的等级合并。
const FALLBACK_LEVELS = ['紧急', '重要', '次要', '提示']

const rows = ref<Row[]>([])
const total = ref(0)
const board = ref<BoardSummary | null>(null)

// 查询条件：输入框里的关键字与已生效的关键字分开，点查询后才生效。
const keywordInput = ref('')
const keyword = ref('')
const level = ref('')
const statusFilter = ref('')

const boardLoading = ref(false)
const listLoading = ref(false)
const boardError = ref('')
const listError = ref('')
const actionMessage = ref('')

const listSection = ref<HTMLElement | null>(null)

const levelOptions = computed<string[]>(() => {
  const options = [...FALLBACK_LEVELS]
  for (const item of board.value?.levels ?? []) {
    if (!options.includes(item)) options.push(item)
  }
  return options
})
const hasActiveFilter = computed(() => Boolean(keyword.value || level.value || statusFilter.value))
const boardEmptyHint = computed(() => {
  if (keyword.value) return '当前告警编号关键字下没有告警，可更换关键字或重置条件后再看。'
  if (level.value) return '当前等级条件下没有告警，可切换告警等级或重置条件后再看。'
  return '当前没有任何告警事件，值班看板将在新告警接入后自动更新。'
})

function levelClass(name: string): string {
  if (name === '紧急') return 'level-critical'
  if (name === '重要') return 'level-major'
  if (name === '次要') return 'level-minor'
  if (name === '提示') return 'level-info'
  return 'level-unknown'
}

function cellTitle(rowLevel: string, status: string, count: number): string {
  return count > 0
    ? `查看 ${rowLevel} 等级「${status}」的 ${count} 条告警`
    : `${rowLevel} 等级暂无「${status}」告警`
}

function buildQuery(extra?: Record<string, string>): string {
  const params = new URLSearchParams()
  if (keyword.value) params.set('keyword', keyword.value)
  if (level.value) params.set('level', level.value)
  if (statusFilter.value) params.set('status', statusFilter.value)
  if (extra) for (const [key, value] of Object.entries(extra)) params.set(key, value)
  const query = params.toString()
  return query ? `?${query}` : ''
}

async function loadBoard() {
  boardLoading.value = true
  boardError.value = ''
  try {
    const response = await request(`${ENDPOINT}/summary${buildQuery()}`)
    if (!response.ok) throw new Error(`接口返回 ${response.status}`)
    board.value = (await response.json()) as BoardSummary
  } catch (error) {
    board.value = null
    boardError.value = error instanceof Error ? error.message : '看板汇总读取失败'
  } finally {
    boardLoading.value = false
  }
}

async function loadList() {
  listLoading.value = true
  listError.value = ''
  try {
    const response = await request(`${ENDPOINT}${buildQuery()}`)
    if (!response.ok) throw new Error('告警事件列表读取失败')
    const payload = (await response.json()) as { items?: Row[]; total?: number }
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    rows.value = []
    total.value = 0
    listError.value = error instanceof Error ? error.message : '告警中心列表读取失败'
  } finally {
    listLoading.value = false
  }
}

function reloadAll() {
  void loadBoard()
  void loadList()
}

function applyFilters() {
  keyword.value = keywordInput.value.trim()
  reloadAll()
}

// 等级条件切换后看板同步变化；下钻的状态条件只对原等级有效，一并清掉。
function onLevelChange() {
  statusFilter.value = ''
  reloadAll()
}

function resetFilters() {
  keywordInput.value = ''
  keyword.value = ''
  level.value = ''
  statusFilter.value = ''
  reloadAll()
}

// 看板下钻：带上等级与状态两个条件刷新列表，再把视图带到列表区。
function drilldown(rowLevel: string, status: string) {
  const count = board.value?.matrix.find((item) => item.level === rowLevel)?.counts[status] ?? 0
  if (!count) return
  if (level.value === rowLevel && statusFilter.value === status) {
    clearStatus()
    return
  }
  level.value = rowLevel
  statusFilter.value = status
  reloadAll()
  listSection.value?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
}

function clearStatus() {
  statusFilter.value = ''
  reloadAll()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

async function runAction(action: string, row: Row) {
  actionMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) throw new Error('告警中心动作未生效，请稍后重试')
    reloadAll()
  } catch (error) {
    actionMessage.value = error instanceof Error ? error.message : '告警中心操作失败'
  }
}

onMounted(reloadAll)
</script>

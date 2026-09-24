<template>
  <section class="page" data-module="alarm">
    <header class="page-head">
      <div>
        <h2>告警中心管理</h2>
        <p class="page-desc">维护告警事件，围绕告警编号、告警类型、告警等级、触发设备做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记告警事件</button>
        <button class="btn" type="button" @click="exportRows">导出告警中心清单</button>
      </div>
    </header>

    <!-- 值班矩阵看板 -->
    <section class="board-card" :class="{ 'is-scoped': isScoped }">
      <div class="board-head">
        <div>
          <h3>值班看板 · 告警矩阵</h3>
          <p class="board-hint">
            按告警等级 × 处理状态汇总，交接班先看左两列（待确认、已确认），等级从上往下处理。
            <template v-if="isScoped">当前矩阵已随列表筛选条件收窄，共命中 {{ board?.total ?? 0 }} 条。</template>
          </p>
        </div>
        <button class="btn" type="button" :disabled="boardLoading" @click="loadBoard">
          {{ boardLoading ? '刷新中…' : '刷新看板' }}
        </button>
      </div>

      <div v-if="boardError" class="board-feedback error">
        <span>看板数据拉取失败：{{ boardError }}</span>
        <button class="btn primary" type="button" :disabled="boardLoading" @click="loadBoard">手动重试</button>
      </div>

      <template v-else>
        <p v-if="boardLoading" class="board-feedback muted">看板数据加载中…</p>

        <template v-else-if="board && board.total_all === 0">
          <p class="board-feedback empty">当前还没有任何告警事件。</p>
          <p class="board-feedback muted">
            说明：所有等级与处理状态下均无数据，看板暂无可汇总内容；待设备产生告警并登记后，矩阵会自动补齐。
          </p>
        </template>

        <template v-else-if="board">
          <!-- 等级 × 状态矩阵：数字可点开查看对应告警事件 -->
          <div class="matrix-scroll">
            <table class="matrix-table">
              <thead>
                <tr>
                  <th class="matrix-corner">告警等级</th>
                  <th
                    v-for="col in board.statuses"
                    :key="col"
                    class="matrix-col-head"
                    :class="colClass(col)"
                  >
                    {{ col }}
                  </th>
                  <th class="matrix-total-head">合计</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in board.matrix" :key="row.level">
                  <th class="matrix-row-head" :class="levelTone(row.level)">
                    <span class="level-dot" :class="levelTone(row.level)"></span>
                    {{ row.level }}
                  </th>
                  <td v-for="cell in row.cells" :key="cell.status">
                    <button
                      type="button"
                      class="matrix-cell"
                      :class="[
                        levelTone(row.level),
                        { active: isCellActive(row.level, cell.status) },
                      ]"
                      :title="`查看「${row.level} · ${cell.status}」告警事件`"
                      @click="drillCell(row.level, cell.status)"
                    >
                      <span class="cell-num">{{ cell.count }}</span>
                      <span v-if="cell.status in activeStatusMap" class="cell-tag">待办</span>
                    </button>
                  </td>
                  <td class="matrix-row-total">{{ rowTotal(row) }}</td>
                </tr>
                <tr v-if="!board.matrix.length">
                  <td :colspan="board.statuses.length + 2" class="matrix-empty">
                    当前筛选条件下没有匹配的告警事件，可调整或清空筛选条件后再看。
                  </td>
                </tr>
              </tbody>
              <tfoot v-if="board.matrix.length">
                <tr>
                  <th class="matrix-total-head">合计</th>
                  <td v-for="col in board.status_totals" :key="col.status">
                    <button
                      type="button"
                      class="matrix-cell col-total"
                      :class="{ active: filters.status === col.status && !filters.level }"
                      :title="`查看全部「${col.status}」告警事件`"
                      @click="drillStatus(col.status)"
                    >
                      {{ col.count }}
                    </button>
                  </td>
                  <td class="matrix-row-total">{{ board.total }}</td>
                </tr>
              </tfoot>
            </table>
          </div>

          <!-- 触发设备最多的告警类型 -->
          <div class="focus-wrap">
            <h4 class="focus-title">触发设备最多的告警类型 TOP{{ Math.max(board.top_types.length, 1) }}</h4>
            <p v-if="!board.top_types.length" class="board-feedback muted">
              当前范围内没有可统计的告警类型。
            </p>
            <ul v-else class="focus-list">
              <li v-for="item in board.top_types" :key="item.type">
                <button
                  type="button"
                  class="focus-chip"
                  :class="{ active: filters.alarm_type === item.type }"
                  title="只看该类型的告警事件"
                  @click="drillType(item.type)"
                >
                  <span class="focus-name">{{ item.type }}</span>
                  <span class="focus-metric">{{ item.device_count }} 台设备触发</span>
                  <span class="focus-metric">共 {{ item.alarm_count }} 条</span>
                  <span v-if="item.active_count" class="focus-active">待办 {{ item.active_count }}</span>
                </button>
              </li>
            </ul>
            <p class="board-hint shift-tip" v-if="board.active_total">
              交接建议：优先处置矩阵左上区域，当前待办共 {{ board.active_total }} 条（待确认 + 已确认）。
            </p>
          </div>
        </template>
      </template>
    </section>

    <!-- 告警事件列表：等级条件切换后看板同步变化 -->
    <form ref="listAnchor" class="filter-bar" @submit.prevent="submitFilters">
      <label class="filter-item">
        <span>告警编号</span>
        <input v-model="filters.keyword" placeholder="按告警编号检索" />
      </label>
      <label class="filter-item">
        <span>告警等级</span>
        <select v-model="filters.level" @change="onLevelChange">
          <option value="">全部等级</option>
          <option v-for="level in levelOptions" :key="level" :value="level">{{ level }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>告警类型</span>
        <select v-model="filters.alarm_type">
          <option value="">全部类型</option>
          <option v-for="type in typeOptions" :key="type" :value="type">{{ type }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>处理状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>触发设备</span>
        <input v-model="filters.device" placeholder="按触发设备检索" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <!-- 看板/下钻生效中的条件 -->
    <div v-if="activeChips.length" class="chip-row">
      <span class="chip-label">当前条件：</span>
      <button
        v-for="chip in activeChips"
        :key="chip.key"
        type="button"
        class="cond-chip"
        @click="clearFilter(chip.key)"
      >
        {{ chip.label }}：{{ chip.value }} <em>✕</em>
      </button>
      <button type="button" class="link" @click="resetFilters">全部清空</button>
    </div>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="listError">
          <td :colspan="columns.length + 1" class="empty-state">
            <p>告警事件列表拉取失败：{{ listError }}</p>
            <button class="btn primary" type="button" @click="loadList">手动重试</button>
          </td>
        </tr>
        <tr v-else-if="listLoading">
          <td :colspan="columns.length + 1" class="empty-state">告警事件加载中…</td>
        </tr>
        <template v-else>
          <tr v-for="row in rows" :key="String(row.id)">
            <td v-for="column in columns" :key="column">
              <span v-if="column === '告警等级'" class="level-badge" :class="levelTone(String(row[column] ?? ''))">
                {{ row[column] || '—' }}
              </span>
              <template v-else>{{ row[column] || '—' }}</template>
            </td>
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
              <template v-if="isScoped">当前筛选条件下没有匹配的告警事件，可调整或重置筛选条件。</template>
              <template v-else>暂无告警中心数据，可先登记告警事件</template>
            </td>
          </tr>
        </template>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条告警中心记录</span>
      <span v-if="actionMessage" class="error-text">{{ actionMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type FilterKey = 'keyword' | 'level' | 'alarm_type' | 'status' | 'device'
type Filters = Record<FilterKey, string>
type MatrixCell = { status: string; count: number }
type MatrixRow = { level: string; cells: MatrixCell[] }
type Summary = {
  levels: string[]
  statuses: string[]
  matrix: MatrixRow[]
  status_totals: MatrixCell[]
  total: number
  total_all: number
  active_total: number
  top_types: { type: string; device_count: number; alarm_count: number; active_count: number }[]
  filter_options: { levels: string[]; types: string[] }
}

const ENDPOINT = '/api/alarm'
const columns = ["告警编号", "告警类型", "告警等级", "触发设备", "触发时间", "处理状态", "处理人"]
const actions = ["确认告警", "处置告警", "忽略告警"]
const statuses = ["待确认", "已确认", "已处置", "已忽略"]
const activeStatuses = ["待确认", "已确认"]
const activeStatusMap: Record<string, boolean> = Object.fromEntries(
  activeStatuses.map((status) => [status, true]),
)
const emptyFilters = (): Filters => ({ keyword: '', level: '', alarm_type: '', status: '', device: '' })

const rows = ref<Row[]>([])
const total = ref(0)
const actionMessage = ref('')
const filters = ref<Filters>(emptyFilters())
const listAnchor = ref<HTMLElement | null>(null)

const board = ref<Summary | null>(null)
const boardLoading = ref(false)
const boardError = ref('')
const listLoading = ref(false)
const listError = ref('')

const levelOptions = computed(() => board.value?.filter_options.levels ?? [])
const typeOptions = computed(() => board.value?.filter_options.types ?? [])
const isScoped = computed(() => Object.values(filters.value).some((value) => value.trim() !== ''))

const filterLabels: Record<FilterKey, string> = {
  keyword: '告警编号',
  level: '告警等级',
  alarm_type: '告警类型',
  status: '处理状态',
  device: '触发设备',
}
const activeChips = computed(() =>
  (Object.keys(filters.value) as FilterKey[])
    .filter((key) => filters.value[key].trim() !== '')
    .map((key) => ({ key, label: filterLabels[key], value: filters.value[key] })),
)

function queryString() {
  const params = new URLSearchParams()
  if (filters.value.keyword.trim()) params.set('keyword', filters.value.keyword.trim())
  if (filters.value.level) params.set('level', filters.value.level)
  if (filters.value.alarm_type) params.set('alarm_type', filters.value.alarm_type)
  if (filters.value.status) params.set('status', filters.value.status)
  if (filters.value.device.trim()) params.set('device', filters.value.device.trim())
  return params.toString()
}

async function loadBoard() {
  boardLoading.value = true
  boardError.value = ''
  try {
    const query = queryString()
    const response = await request(`${ENDPOINT}/summary${query ? `?${query}` : ''}`)
    if (!response.ok) {
      throw new Error(`接口返回 ${response.status}`)
    }
    board.value = await response.json()
  } catch (error) {
    board.value = null
    boardError.value = error instanceof Error ? error.message : '汇总数据不可用'
  } finally {
    boardLoading.value = false
  }
}

async function loadList() {
  listLoading.value = true
  listError.value = ''
  const query = queryString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('告警事件列表读取失败')
    }
    const payload = await response.json()
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

function reload() {
  void loadBoard()
  void loadList()
}

function applyAndReload() {
  reload()
  listAnchor.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function submitFilters() {
  applyAndReload()
}

// 列表的等级条件切换后，看板按同一口径同步变化。
function onLevelChange() {
  applyAndReload()
}

function resetFilters() {
  filters.value = emptyFilters()
  reload()
}

function clearFilter(key: FilterKey) {
  filters.value[key] = ''
  reload()
}

// 看板数字点开后，列表定位到对应「等级 × 状态」的告警事件。
function drillCell(level: string, status: string) {
  filters.value.level = level
  filters.value.status = status
  applyAndReload()
}

function drillStatus(status: string) {
  filters.value.status = status
  filters.value.level = ''
  applyAndReload()
}

function drillType(type: string) {
  filters.value.alarm_type = filters.value.alarm_type === type ? '' : type
  applyAndReload()
}

function isCellActive(level: string, status: string) {
  return filters.value.level === level && filters.value.status === status
}

function rowTotal(row: MatrixRow) {
  return row.cells.reduce((sum, cell) => sum + cell.count, 0)
}

function colClass(status: string) {
  return activeStatusMap[status] ? 'col-active' : 'col-done'
}

function levelTone(level: string) {
  if (level === '紧急') return 'tone-critical'
  if (level === '重要') return 'tone-major'
  if (level === '次要') return 'tone-minor'
  return 'tone-other'
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  actionMessage.value = '告警事件登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  actionMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('告警中心动作未生效，请稍后重试')
    }
    reload()
  } catch (error) {
    actionMessage.value = error instanceof Error ? error.message : '告警中心操作失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.board-card {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 14px;
  margin-bottom: 14px;
}
.board-card.is-scoped {
  border-color: var(--brand);
  box-shadow: 0 0 0 1px var(--brand) inset;
}
.board-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 10px;
}
.board-head h3 {
  margin: 0 0 2px;
  font-size: 15px;
}
.board-hint {
  margin: 0;
  color: var(--muted);
  font-size: 12px;
}
.shift-tip {
  margin-top: 8px;
  color: #b42318;
}
.board-feedback {
  margin: 6px 0;
  font-size: 13px;
}
.board-feedback.empty {
  color: #1f2937;
  font-weight: 600;
}
.board-feedback.muted {
  color: var(--muted);
}
.board-feedback.error {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  color: #b42318;
}

.matrix-scroll {
  overflow-x: auto;
}
.matrix-table {
  width: 100%;
  border-collapse: collapse;
}
.matrix-table th,
.matrix-table td {
  border: 1px solid var(--border);
  padding: 6px 8px;
  text-align: center;
  font-size: 13px;
}
.matrix-corner,
.matrix-row-head,
.matrix-total-head {
  background: #f8fafc;
  font-weight: 600;
}
.matrix-col-head.col-active {
  color: #b42318;
}
.matrix-col-head.col-done {
  color: var(--muted);
}
.matrix-row-head {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border: none;
  background: transparent;
}
.level-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}
.tone-critical {
  color: #b42318;
}
.tone-major {
  color: #c26a00;
}
.tone-minor {
  color: #1f6feb;
}
.tone-other {
  color: var(--muted);
}
.level-dot.tone-critical {
  background: #d92d20;
}
.level-dot.tone-major {
  background: #f79009;
}
.level-dot.tone-minor {
  background: #2e90fa;
}
.level-dot.tone-other {
  background: #94a3b8;
}
.matrix-cell {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 92px;
  min-height: 46px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: #f8fafc;
  cursor: pointer;
  font-size: 18px;
  font-weight: 700;
  padding: 6px 8px;
  transition: background 0.15s, border-color 0.15s;
}
.matrix-cell:hover {
  background: #eef4ff;
  border-color: var(--brand);
}
.matrix-cell.active {
  border-color: var(--brand);
  box-shadow: 0 0 0 1px var(--brand) inset;
}
.matrix-cell.tone-critical {
  color: #b42318;
}
.matrix-cell.tone-major {
  color: #c26a00;
}
.matrix-cell.tone-minor {
  color: #1f6feb;
}
.matrix-cell.tone-other {
  color: var(--muted);
}
.cell-tag {
  position: absolute;
  top: 3px;
  right: 5px;
  font-size: 10px;
  font-weight: 500;
  color: #b42318;
  border: 1px solid #f3c2bb;
  border-radius: 8px;
  padding: 0 5px;
  line-height: 14px;
}
.matrix-row-total,
.col-total {
  font-weight: 700;
}
.matrix-empty {
  text-align: center;
  color: var(--muted);
  padding: 16px;
}

.focus-wrap {
  margin-top: 12px;
}
.focus-title {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--muted);
}
.focus-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  list-style: none;
  margin: 0;
  padding: 0;
}
.focus-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: #fff;
  padding: 5px 12px;
  cursor: pointer;
  font-size: 12px;
}
.focus-chip:hover,
.focus-chip.active {
  border-color: var(--brand);
  background: #eef4ff;
}
.focus-name {
  font-weight: 700;
  color: #1f2937;
}
.focus-metric {
  color: var(--muted);
}
.focus-active {
  color: #b42318;
  font-weight: 600;
}

.filter-bar select {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 13px;
  background: #fff;
}
.chip-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.chip-label {
  font-size: 12px;
  color: var(--muted);
}
.cond-chip {
  border: 1px solid var(--brand);
  background: #eef4ff;
  color: var(--brand);
  border-radius: 999px;
  padding: 3px 10px;
  font-size: 12px;
  cursor: pointer;
}
.cond-chip em {
  font-style: normal;
  margin-left: 4px;
  opacity: 0.7;
}
.level-badge {
  display: inline-block;
  border-radius: 4px;
  padding: 1px 8px;
  font-size: 12px;
  background: #f1f5f9;
}
.level-badge.tone-critical {
  background: #fee4e2;
}
.level-badge.tone-major {
  background: #fef0c7;
}
.level-badge.tone-minor {
  background: #d1e9ff;
}
</style>

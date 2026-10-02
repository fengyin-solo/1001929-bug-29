<template>
  <section class="page" data-module="yaw">
    <header class="page-head">
      <div>
        <h2>偏航系统管理</h2>
        <p class="page-desc">维护偏航系统，围绕系统编号、所属机组、偏航方式、对风偏差做登记、筛选与状态流转。状态只能按待润滑 → 运行正常 → 对风偏差大 → 已锁定逐步推进。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记偏航系统</button>
        <button class="btn" type="button" @click="exportRows">导出偏航系统清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">详情</button>
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              :disabled="!isActionAllowed(action, row)"
              :title="isActionAllowed(action, row) ? '' : blockedHint(action, row)"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无偏航系统数据，可先登记偏航系统</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条偏航系统记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      <span v-else-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
    </footer>

    <div v-if="detailRow" class="detail-mask" @click.self="closeDetail">
      <div class="detail-panel">
        <header class="detail-head">
          <h3>偏航系统详情</h3>
          <button class="btn ghost" type="button" @click="closeDetail">关闭</button>
        </header>
        <table class="data-table">
          <tbody>
            <tr v-for="column in columns" :key="column">
              <th>{{ column }}</th>
              <td>{{ detailRow[column] ?? '—' }}</td>
            </tr>
          </tbody>
        </table>
        <p class="detail-tip">
          当前状态「{{ detailRow['偏航状态'] }}」；下一步可执行：
          {{ nextAction(detailRow) ?? '已锁定，终态不再接受任何动作' }}
        </p>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>

const ENDPOINT = '/api/yaw'
const columns = ["系统编号", "所属机组", "偏航方式", "对风偏差", "偏航次数", "上次润滑日", "润滑油脂", "偏航状态"]
const actions = ["提交润滑", "登记对风偏差", "锁定偏航"]
const statuses = ["待润滑", "运行正常", "对风偏差大", "已锁定"]
// 每个状态只允许对应“下一步”的那一个动作，其余一律禁用并说明卡在哪一项
const NEXT_ACTION: Record<string, string> = {
  "待润滑": "提交润滑",
  "运行正常": "登记对风偏差",
  "对风偏差大": "锁定偏航",
}

const rows = ref<Row[]>([])
const allRows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const noticeMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
const detailRow = ref<Row | null>(null)

const stats = ref([
  { label: "待润滑偏航", value: 0 },
  { label: "对风偏差台数", value: 0 },
  { label: "本月润滑数", value: 0 },
])

function currentStatus(row: Row): string {
  return String(row['偏航状态'] ?? row.status ?? '')
}

function nextAction(row: Row): string | null {
  return NEXT_ACTION[currentStatus(row)] ?? null
}

function isActionAllowed(action: string, row: Row): boolean {
  return nextAction(row) === action
}

function blockedHint(action: string, row: Row): string {
  const status = currentStatus(row)
  if (status === '已锁定') {
    return `偏航系统已锁定，终态不再接受「${action}」`
  }
  return `当前卡在「${status}」，需先「${nextAction(row)}」才能「${action}」`
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '偏航系统登记入口尚未接入审批流'
}

function openDetail(row: Row) {
  errorMessage.value = ''
  noticeMessage.value = ''
  detailRow.value = row
}

function closeDetail() {
  detailRow.value = null
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  noticeMessage.value = ''
  // 登记对风偏差时把偏差值一并提交；取消或留空则放弃本次操作
  const values: Record<string, string> = {}
  if (action === '登记对风偏差') {
    const previous = row['对风偏差'] == null ? '' : String(row['对风偏差'])
    const input = window.prompt('请输入本次测得的对风偏差（例如 9.2°）', previous)
    if (input === null) {
      return
    }
    const deviation = input.trim()
    if (!deviation) {
      errorMessage.value = '对风偏差不能为空，已放弃本次提交'
      return
    }
    values['对风偏差'] = deviation
  }
  values.action = action
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify(values),
    })
    if (!response.ok) {
      throw new Error('偏航系统动作未生效，请稍后重试')
    }
    const payload = await response.json()
    // 拦截/幂等结果都是 HTTP 200 + ok:false/提示语，必须看业务标志，不能只看 HTTP 状态
    if (payload.ok === false) {
      errorMessage.value = payload.message || '该动作不满足状态流转条件'
      return
    }
    noticeMessage.value = payload.message || `偏航系统已${action}`
    await reload()
    if (detailRow.value && String(detailRow.value.id) === String(row.id)) {
      const latest = allRows.value.find((item) => String(item.id) === String(row.id))
      if (latest) {
        detailRow.value = latest
      }
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '偏航系统操作失败'
  }
}

function refreshStats() {
  const currentMonth = new Date().toISOString().slice(0, 7)
  stats.value = [
    { label: "待润滑偏航", value: allRows.value.filter((row) => currentStatus(row) === '待润滑').length },
    { label: "对风偏差台数", value: allRows.value.filter((row) => currentStatus(row) === '对风偏差大').length },
    {
      label: "本月润滑数",
      value: allRows.value.filter((row) => String(row['上次润滑日'] ?? '').startsWith(currentMonth)).length,
    },
  ]
}

async function reload() {
  errorMessage.value = ''
  noticeMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const [pageResponse, allResponse] = await Promise.all([
      request(`${ENDPOINT}?${query}`),
      request(`${ENDPOINT}?page=1&size=200`),
    ])
    if (!pageResponse.ok || !allResponse.ok) {
      throw new Error('偏航系统列表读取失败')
    }
    const payload = await pageResponse.json()
    const allPayload = await allResponse.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    allRows.value = allPayload.items ?? []
    refreshStats()
    if (detailRow.value) {
      const latest = allRows.value.find((item) => String(item.id) === String(detailRow.value?.id))
      if (latest) {
        detailRow.value = latest
      }
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '偏航系统列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.notice-text {
  color: #b54708;
}

.detail-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  justify-content: flex-end;
  z-index: 20;
}

.detail-panel {
  width: 420px;
  max-width: 90vw;
  height: 100%;
  background: #fff;
  padding: 16px;
  overflow-y: auto;
}

.detail-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.detail-head h3 {
  margin: 0;
  font-size: 16px;
}

.detail-tip {
  margin-top: 12px;
  font-size: 13px;
  color: #64748b;
}

.link:disabled {
  color: #b6beca;
  cursor: not-allowed;
}
</style>

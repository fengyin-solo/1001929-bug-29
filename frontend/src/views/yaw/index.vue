<template>
  <section class="page" data-module="yaw">
    <header class="page-head">
      <div>
        <h2>偏航系统管理</h2>
        <p class="page-desc">维护偏航系统，围绕系统编号、所属机组、偏航方式、对风偏差做登记、筛选与状态流转。</p>
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
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              :disabled="!isAllowed(action, row)"
              :title="isAllowed(action, row) ? action : blockReason(action, row)"
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
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>

const ENDPOINT = '/api/yaw'
const columns = ["系统编号", "所属机组", "偏航方式", "对风偏差", "偏航次数", "上次润滑日", "润滑油脂", "偏航状态"]
const actions = ["提交润滑", "登记对风偏差", "锁定偏航"]
// 与后端状态机同一口径：只有“当前状态对应的下一步动作”可点，跳步按钮直接置灰
const nextActionByStatus: Record<string, string> = {
  "待润滑": "提交润滑",
  "运行正常": "登记对风偏差",
  "对风偏差大": "锁定偏航",
  "已锁定": "",
}
const stats = [{"label": "待润滑偏航", "value": 0}, {"label": "对风偏差台数", "value": 0}, {"label": "本月润滑数", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

function currentStatus(row: Row): string {
  return String(row.status ?? row["偏航状态"] ?? "")
}

function isAllowed(action: string, row: Row): boolean {
  return nextActionByStatus[currentStatus(row)] === action
}

function blockReason(action: string, row: Row): string {
  const status = currentStatus(row)
  if (status === "已锁定") {
    return `偏航系统已锁定，不再接受${action}`
  }
  const next = nextActionByStatus[status]
  return next
    ? `当前状态为「${status}」，请先完成「${next}」，不能直接${action}`
    : `当前状态「${status}」不允许执行${action}`
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

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  if (!isAllowed(action, row)) {
    errorMessage.value = blockReason(action, row)
    return
  }
  const values: Record<string, string> = { action }
  if (action === "登记对风偏差") {
    const input = window.prompt('请输入本次登记的对风偏差')
    if (input === null) return
    const deviation = input.trim()
    if (!deviation) {
      errorMessage.value = '请填写对风偏差后再登记，未填写的偏差不予登记'
      return
    }
    values["对风偏差"] = deviation
  }
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    if (!response.ok) {
      throw new Error('偏航系统动作未生效，请稍后重试')
    }
    const payload = (await response.json()) as { ok: boolean; message: string }
    if (!payload.ok) {
      errorMessage.value = payload.message || '该操作未通过状态校验'
      return
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '偏航系统操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('偏航系统列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '偏航系统列表读取失败'
  }
}

onMounted(reload)
</script>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElAlert, ElButton, ElEmpty, ElSkeleton } from 'element-plus'
import { api } from '../api/client'
import type { Dashboard } from '../api/types'
import { currentUser } from '../stores/session'
import { formatDate } from '../utils/date'
import TaskList from '../components/TaskList.vue'
const data = ref<Dashboard | null>(null), busy = ref(false), error = ref('')
const isManager = computed(() => currentUser.value?.role === 'MANAGER')
const isBoss = computed(() => currentUser.value?.role === 'BOSS')
let request: AbortController | undefined
async function load() {
  request?.abort()
  const controller = new AbortController(); request = controller
  busy.value = true; error.value = ''; data.value = null
  try { const result = await api<Dashboard>('/dashboard', { signal: controller.signal }); if (request === controller) data.value = result }
  catch (cause) { if (request === controller && !controller.signal.aborted) error.value = cause instanceof Error ? cause.message : '加载失败' }
  finally { if (request === controller) busy.value = false }
}
onMounted(load)
onUnmounted(() => { request?.abort(); request = undefined })
</script>
<template>
  <div class="page-heading"><div><p class="eyebrow">{{ isBoss ? '团队工作概览' : isManager ? '部门工作概览' : '我的工作概览' }}</p><h1>{{ currentUser?.name }}，你好。</h1><p class="muted">{{ isBoss ? '了解会议后的执行情况，把注意力放在需要跟进的地方。' : '从今天需要完成的工作开始，及时记录每一步进展。' }}</p></div><ElButton :loading="busy" @click="load">刷新概览</ElButton></div>
  <ElAlert v-if="error" :title="error" type="error" :closable="false" show-icon />
  <ElSkeleton v-if="busy" :rows="8" animated class="panel" />
  <template v-if="data">
    <div class="stat-grid">
      <article class="stat-card"><span>{{ isBoss ? '全部任务' : isManager ? '部门及我参与的任务' : '我的任务' }}</span><strong>{{ data.statistics.total }}</strong><small>已完成 {{ data.statistics.done }} 项</small></article>
      <article class="stat-card"><span>进行中</span><strong>{{ data.statistics.in_progress }}</strong><small>待开始 {{ data.statistics.todo }} 项</small></article>
      <article class="stat-card"><span>今日到期</span><strong>{{ data.statistics.due_today }}</strong><small>按上海时区计算</small></article>
      <article class="stat-card warning"><span>已逾期</span><strong>{{ data.statistics.overdue }}</strong><small>尚未完成的到期任务</small></article>
    </div>
    <div v-if="(isBoss || isManager) && data.pending_supplement_count !== null" class="attention-strip"><span class="attention-mark">!</span><div><strong>{{ data.pending_supplement_count ? `${data.pending_supplement_count} 项会议事项需要补充` : '当前没有待补充的会议事项' }}</strong><p>负责人缺失、来源异常或新版本待选择的事项会在这里计数。</p></div></div>
    <div id="priorities" class="two-columns">
      <section class="panel"><div class="panel-heading"><h2>今日到期</h2><span>{{ data.statistics.due_today }} 项</span></div><TaskList :tasks="data.due_today_tasks" empty-text="今天没有到期任务" /><p v-if="data.statistics.due_today > 5" class="list-note">显示最早到期的 5 项</p></section>
      <section class="panel"><div class="panel-heading"><h2>需要跟进的逾期任务</h2><span>{{ data.statistics.overdue }} 项</span></div><TaskList :tasks="data.overdue_tasks" empty-text="没有逾期任务" /><p v-if="data.statistics.overdue > 5" class="list-note">显示最早到期的 5 项</p></section>
    </div>
    <section id="meetings" class="panel"><div class="panel-heading"><h2>近期会议</h2><span>即将开始 · 最多 5 场</span></div><div v-if="data.upcoming_meetings.length"><article v-for="meeting in data.upcoming_meetings" :key="meeting.id" class="meeting-row"><div class="meeting-date">{{ formatDate(meeting.starts_at, true) }}</div><div><h3>{{ meeting.title }}</h3><p>{{ formatDate(meeting.starts_at) }} · {{ meeting.location || '地点未填写' }}</p></div></article></div><ElEmpty v-else description="暂无即将开始的会议" :image-size="64" /></section>
    <section id="ongoing" class="panel"><div class="panel-heading"><h2>进行中的任务</h2><span>{{ data.statistics.in_progress }} 项</span></div><TaskList :tasks="data.in_progress_tasks" empty-text="暂无进行中的任务" /><p v-if="data.statistics.in_progress > 5" class="list-note">显示最早到期的 5 项</p></section>
    <p class="page-footnote">数据更新于 {{ formatDate(data.as_of) }} · {{ isBoss ? '团队授权范围' : isManager ? '本部门负责的任务及你个人参与的工作；会议按邀请范围显示' : '仅显示与你相关的会议和任务' }}</p>
  </template>
</template>

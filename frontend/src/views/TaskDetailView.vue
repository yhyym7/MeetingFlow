<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { ElAlert, ElButton, ElDialog, ElInput, ElTag, ElPagination, ElMessageBox } from 'element-plus'
import { api } from '../api/client'
import type { Page, TaskDetail, TaskDraft, TaskEvent } from '../api/types'
import { useDirectory } from '../composables/useDirectory'
import { formatDate } from '../utils/date'
import TaskForm from '../components/TaskForm.vue'
import { router } from '../router'
const id = Number(useRoute().params.id), task = ref<TaskDetail | null>(null), events = ref<TaskEvent[]>([])
const page = ref(1), total = ref(0), error = ref(''), dialogError = ref(''), busy = ref(false), saving = ref(false), editing = ref(false), progress = ref('')
const directory = useDirectory(), lifetime = new AbortController()
const canManage = computed(() => task.value?.can_manage === true)
const canStatus = computed(() => task.value?.can_update_status === true)
const statusLabels: Record<string, string> = { TODO: '待开始', IN_PROGRESS: '进行中', DONE: '已完成' }
async function load() {
  busy.value = true; error.value = ''
  try {
    const [record, history] = await Promise.all([api<TaskDetail>(`/tasks/${id}`, { signal: lifetime.signal }), api<Page<TaskEvent>>(`/tasks/${id}/events?page=${page.value}`, { signal: lifetime.signal })])
    task.value = record; events.value = history.items; total.value = history.total
  } catch (cause) { if (!lifetime.signal.aborted) { error.value = (cause as Error).message; task.value = null; events.value = [] } }
  finally { busy.value = false }
}
async function changeStatus(status: string) {
  saving.value = true
  try { await api(`/tasks/${id}/status`, { method: 'PATCH', body: JSON.stringify({ status }), signal: lifetime.signal }); page.value = 1; await load() }
  catch (cause) { error.value = (cause as Error).message }
  finally { saving.value = false }
}
async function addProgress() {
  saving.value = true
  try { await api(`/tasks/${id}/events`, { method: 'POST', body: JSON.stringify({ body: progress.value }), signal: lifetime.signal }); progress.value = ''; page.value = 1; await load() }
  catch (cause) { error.value = (cause as Error).message }
  finally { saving.value = false }
}
function draft(): Partial<TaskDraft> { const t = task.value!; return { title: t.title, description: t.description, owner_id: t.owner_id, collaborator_ids: [...t.collaborator_ids], due_at: t.due_at, priority: t.priority, source_excerpt: t.source_excerpt || '' } }
async function save(value: TaskDraft) {
  saving.value = true; dialogError.value = ''
  try { await api(`/tasks/${id}`, { method: 'PATCH', body: JSON.stringify({ ...value, description: value.description || value.title }), signal: lifetime.signal }); editing.value = false; page.value = 1; await load() }
  catch (cause) { dialogError.value = (cause as Error).message }
  finally { saving.value = false }
}
async function remove() {
  try { await ElMessageBox.confirm('删除后该任务将不再显示，重新分析也不会恢复它。', '删除错误任务', { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }) } catch { return }
  saving.value = true
  try { await api(`/tasks/${id}`, { method: 'DELETE', signal: lifetime.signal }); await router.push('/tasks') }
  catch (cause) { error.value = (cause as Error).message }
  finally { saving.value = false }
}
function eventText(event: TaskEvent) {
  if (event.event_type === 'STATUS_CHANGED') {
    const status = event.changes?.status as { before: string; after: string } | undefined
    return status ? `状态由“${statusLabels[status.before]}”更新为“${statusLabels[status.after]}”` : '更新状态'
  }
  return event.body || '更新任务信息'
}
onMounted(async () => { await load(); try { await directory.load(lifetime.signal) } catch (cause) { error.value = (cause as Error).message } })
onUnmounted(() => lifetime.abort())
</script>
<template>
  <RouterLink to="/tasks" class="text-link">← 返回任务列表</RouterLink>
  <ElAlert v-if="error" :title="error" type="error" :closable="false" class="spaced" />
  <div class="page-heading spaced"><div><p class="eyebrow">任务详情</p><h1>{{ task?.title || '任务记录' }}</h1></div><div class="actions"><ElButton :loading="busy" @click="load">刷新</ElButton><template v-if="canManage && task"><ElButton :disabled="saving" @click="editing = true; dialogError = ''">编辑任务</ElButton><ElButton type="danger" plain :disabled="saving" @click="remove">删除任务</ElButton></template></div></div>
  <template v-if="task">
    <section class="panel"><div class="panel-heading"><h2>任务信息</h2><ElTag :type="task.status === 'DONE' ? 'success' : task.is_overdue ? 'danger' : 'info'">{{ statusLabels[task.status] }}{{ task.is_overdue ? ' · 已逾期' : '' }}</ElTag></div><p class="prewrap">{{ task.description }}</p><dl class="details-grid"><dt>负责人</dt><dd>{{ directory.name(task.owner_id) }}</dd><dt>协作人</dt><dd>{{ task.collaborator_ids.map(directory.name).join('、') || '无' }}</dd><dt>截止时间</dt><dd>{{ task.due_at ? formatDate(task.due_at) : '未指定' }}</dd><dt>优先级</dt><dd>{{ task.priority === 'HIGH' ? '高' : task.priority === 'LOW' ? '低' : '普通' }}</dd><template v-if="task.completed_at"><dt>完成时间</dt><dd>{{ formatDate(task.completed_at) }}</dd></template></dl><div v-if="canStatus" class="actions"><ElButton v-if="task.status === 'TODO'" type="primary" :loading="saving" @click="changeStatus('IN_PROGRESS')">开始任务</ElButton><ElButton v-if="task.status !== 'DONE'" type="success" :loading="saving" @click="changeStatus('DONE')">标记完成</ElButton><ElButton v-if="task.status === 'DONE'" :loading="saving" @click="changeStatus('IN_PROGRESS')">重新打开</ElButton><ElButton v-if="task.status === 'IN_PROGRESS'" :loading="saving" @click="changeStatus('TODO')">设为待开始</ElButton></div></section>
    <section v-if="task.meeting_id || task.source_excerpt" class="panel"><div class="panel-heading"><h2>来源与相关摘录</h2><RouterLink v-if="task.can_view_meeting" class="text-link" :to="`/meetings/${task.meeting_id}`">查看会议</RouterLink></div><p>{{ task.source_meeting_title || '独立任务' }}</p><blockquote v-if="task.source_excerpt" class="prewrap">{{ task.source_excerpt }}</blockquote><p v-if="task.meeting_id && !task.can_view_meeting" class="muted">你未参加这场会议，可以查看与任务相关的摘录。</p></section>
    <section class="panel"><h2>填写进展</h2><form @submit.prevent="addProgress"><ElInput v-model="progress" type="textarea" :rows="3" maxlength="2000" show-word-limit class="spaced" placeholder="记录已完成的工作、遇到的问题或需要协助的事项" aria-label="进展内容" :disabled="saving" /><ElButton native-type="submit" type="primary" class="spaced" :loading="saving" :disabled="!progress.trim()">提交进展</ElButton></form></section>
    <section class="panel"><h2>任务动态</h2><article v-for="event in events" :key="event.id" class="event-row"><p class="muted">{{ directory.name(event.actor_id) }} · {{ formatDate(event.created_at) }}</p><p class="prewrap spaced">{{ eventText(event) }}</p></article><ElPagination v-if="total > 20" v-model:current-page="page" :total="total" :page-size="20" layout="prev, pager, next" @current-change="load" /></section>
  </template>
  <ElDialog v-model="editing" title="编辑任务" width="min(680px, 94vw)" destroy-on-close :close-on-click-modal="!saving"><ElAlert v-if="dialogError" :title="dialogError" type="error" :closable="false" /><TaskForm v-if="task" :initial="draft()" :people="directory.people.value" :label="directory.label" :busy="saving" @save="save" /></ElDialog>
</template>

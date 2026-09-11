<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { ElAlert, ElButton, ElDialog, ElSelect, ElOption, ElTable, ElTableColumn, ElPagination, ElEmpty, ElTag } from 'element-plus'
import { api } from '../api/client'
import type { Page, TaskDetail, TaskDraft } from '../api/types'
import { currentUser } from '../stores/session'
import { useDirectory } from '../composables/useDirectory'
import { formatDate } from '../utils/date'
import TaskForm from '../components/TaskForm.vue'
import { router } from '../router'
const route = useRoute(), rows = ref<TaskDetail[]>([]), page = ref(1), total = ref(0)
const membership = ref('all'), status = ref(''), overdue = ref(route.query.overdue === 'true' ? 'true' : ''), error = ref(''), busy = ref(false)
const creating = ref(false), saving = ref(false), dialogError = ref('')
const isLeader = computed(() => ['BOSS', 'MANAGER'].includes(currentUser.value?.role || '')), directory = useDirectory()
const lifetime = new AbortController()
let controller: AbortController | undefined
const meetingId = Number(route.query.meeting_id) || null
async function load(reset = false) {
  if (reset) page.value = 1
  controller?.abort(); const request = new AbortController(); controller = request
  busy.value = true; error.value = ''; rows.value = []
  const query = new URLSearchParams({ page: String(page.value), membership: membership.value })
  if (status.value) query.set('status', status.value)
  if (overdue.value) query.set('overdue', overdue.value)
  if (meetingId) query.set('meeting_id', String(meetingId))
  try { const result = await api<Page<TaskDetail>>(`/tasks?${query}`, { signal: request.signal }); if (controller === request) { rows.value = result.items; total.value = result.total } }
  catch (cause) { if (!request.signal.aborted) error.value = (cause as Error).message }
  finally { if (controller === request) busy.value = false }
}
async function openCreate() { dialogError.value = ''; creating.value = true; try { await directory.load(lifetime.signal) } catch (cause) { dialogError.value = (cause as Error).message } }
async function create(value: TaskDraft) {
  saving.value = true; dialogError.value = ''
  try { const result = await api<TaskDetail>('/tasks', { method: 'POST', body: JSON.stringify({ ...value, meeting_id: meetingId }), signal: lifetime.signal }); creating.value = false; await router.push(`/tasks/${result.id}`) }
  catch (cause) { dialogError.value = (cause as Error).message }
  finally { saving.value = false }
}
onMounted(async () => { await load(); try { await directory.load(lifetime.signal) } catch (cause) { error.value = (cause as Error).message } })
onUnmounted(() => { lifetime.abort(); controller?.abort() })
</script>
<template>
  <div class="page-heading"><div><p class="eyebrow">行动与进展</p><h1>{{ isLeader ? '任务管理' : '我的任务' }}</h1><p class="muted">{{ meetingId ? '当前按来源会议筛选。' : '明确责任、跟进进度，让每项工作都有结果。' }}</p></div><ElButton v-if="isLeader" type="primary" @click="openCreate">新建任务</ElButton></div>
  <section class="panel"><div class="toolbar"><ElSelect v-model="membership" aria-label="任务关系" @change="load(true)"><ElOption label="全部相关" value="all" /><ElOption label="我负责的" value="owned" /><ElOption label="我协作的" value="collaborating" /></ElSelect><ElSelect v-model="status" aria-label="任务状态筛选" @change="load(true)"><ElOption label="全部状态" value="" /><ElOption label="待开始" value="TODO" /><ElOption label="进行中" value="IN_PROGRESS" /><ElOption label="已完成" value="DONE" /></ElSelect><ElSelect v-model="overdue" aria-label="逾期筛选" @change="load(true)"><ElOption label="全部期限" value="" /><ElOption label="仅逾期" value="true" /></ElSelect><ElButton :loading="busy" @click="load()">刷新</ElButton><RouterLink v-if="meetingId" class="text-link" to="/tasks">清除会议筛选</RouterLink></div>
    <ElAlert v-if="error" :title="error" type="error" :closable="false" />
    <ElTable v-if="rows.length" :data="rows"><ElTableColumn label="任务" min-width="240"><template #default="{ row }"><RouterLink :to="`/tasks/${row.id}`" class="text-link">{{ row.title }}</RouterLink><p class="muted">{{ row.source_meeting_title || '独立任务' }}</p></template></ElTableColumn><ElTableColumn label="负责人" min-width="100"><template #default="{ row }">{{ directory.name(row.owner_id) }}</template></ElTableColumn><ElTableColumn label="期限" min-width="150"><template #default="{ row }">{{ row.due_at ? formatDate(row.due_at) : '未指定' }}</template></ElTableColumn><ElTableColumn label="状态" min-width="110"><template #default="{ row }"><ElTag :type="row.is_overdue ? 'danger' : row.status === 'DONE' ? 'success' : 'info'">{{ row.is_overdue ? '已逾期' : row.status === 'DONE' ? '已完成' : row.status === 'IN_PROGRESS' ? '进行中' : '待开始' }}</ElTag></template></ElTableColumn></ElTable>
    <ElEmpty v-else :description="busy ? '正在加载任务' : '暂无符合条件的任务'" :image-size="64" /><ElPagination v-if="total > 20" v-model:current-page="page" :total="total" :page-size="20" layout="prev, pager, next" @current-change="load()" />
  </section>
  <ElDialog v-model="creating" title="新建任务" width="min(680px, 94vw)" destroy-on-close :close-on-click-modal="!saving"><ElAlert v-if="dialogError" :title="dialogError" type="error" :closable="false" /><TaskForm :people="directory.people.value" :label="directory.label" :busy="saving" @save="create" /></ElDialog>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { ElAlert, ElButton, ElDialog, ElInput, ElSelect, ElOption, ElTag, ElEmpty, ElMessage } from 'element-plus'
import { api, ApiError } from '../api/client'
import type { Analysis, Candidate, Job, MeetingDetail, MeetingInput, Page, TaskDraft, TaskSummary } from '../api/types'
import { useDirectory } from '../composables/useDirectory'
import { formatDate } from '../utils/date'
import DepartmentAttendance from '../components/DepartmentAttendance.vue'
import MeetingRecording from '../components/MeetingRecording.vue'
import MeetingSource from '../components/MeetingSource.vue'
import { currentUser } from '../stores/session'
import TaskForm from '../components/TaskForm.vue'
import TaskList from '../components/TaskList.vue'
const id = Number(useRoute().params.id), meeting = ref<MeetingDetail | null>(null), job = ref<Job | null>(null), analysis = ref<Analysis | null>(null)
const candidates = ref<Candidate[]>([]), tasks = ref<TaskSummary[]>([]), totalTasks = ref(0)
const error = ref(''), busy = ref(false), saving = ref(false), text = ref(''), dialogError = ref('')
const selected = ref<Candidate | null>(null), editing = ref(false)
const edit = reactive({ title: '', starts_at: '', location: '', description: '', participant_ids: [] as number[], department_ids: [] as number[] })
const config = ref<{mode: string; demo_text: string | null; audio_max_mb: number; transcription_available: boolean} | null>(null)
const directory = useDirectory(), canManage = computed(() => meeting.value?.can_manage === true)
const active = computed(() => job.value && ['QUEUED', 'RUNNING'].includes(job.value.status))
const lifetime = new AbortController()
let timer: ReturnType<typeof setTimeout> | undefined
let pending: { request_id: string; text: string } | undefined
const labels: Record<string, string> = { QUEUED: '排队中', RUNNING: '处理中', SUCCEEDED: '处理完成', FAILED: '处理失败', SAVED: '原文已保存', NEEDS_INFO: '待补充', REJECTED: '需要纠正', DISCUSSION: '讨论事项', REVIEW: '待选择补建', PUBLISHED: '已生成任务', DISMISSED: '已忽略', READY: '待生成' }
const errors: Record<string, string> = { ANALYSIS_NOT_CONFIGURED: '尚未配置模型接口，原文已保留。', DEMO_SAMPLE_REQUIRED: '演示模式仅处理固定样例，请载入演示样例后提交。', ANALYSIS_TIMEOUT: '分析超时，可以重试。', ANALYSIS_PROVIDER_ERROR: '模型服务暂时不可用，可以稍后重试。' }
async function optionalAnalysis() {
  try { return await api<Analysis>(`/meetings/${id}/analysis`, { signal: lifetime.signal }) }
  catch (cause) { if (cause instanceof ApiError && cause.status === 404) return null; throw cause }
}
Object.assign(errors, { ANALYSIS_AUTH_ERROR: '模型密钥无效或权限不足，请检查本地配置。', ANALYSIS_QUOTA_ERROR: '模型余额不足或达到调用限制，请检查服务账户。', ANALYSIS_INPUT_TOO_LONG: '当前演示版每次最多分析 12000 字，请分段提交。' })
async function load() {
  clearTimeout(timer); busy.value = true; error.value = ''
  try {
    const record = await api<MeetingDetail>(`/meetings/${id}`, { signal: lifetime.signal })
    const [result, taskPage, candidatePage, state] = await Promise.all([
      optionalAnalysis(), api<Page<TaskSummary>>(`/meetings/${id}/tasks?page_size=100`, { signal: lifetime.signal }),
      record.can_manage ? api<Page<Candidate>>(`/meetings/${id}/candidates?page_size=100`, { signal: lifetime.signal }) : null,
      record.current_input?.job_id ? api<Job>(`/jobs/${record.current_input.job_id}`, { signal: lifetime.signal }) : null,
    ])
    meeting.value = record; analysis.value = result; tasks.value = taskPage.items; totalTasks.value = taskPage.total
    candidates.value = candidatePage?.items || []; job.value = state
    if ((state && ['QUEUED', 'RUNNING'].includes(state.status)) || ['QUEUED', 'RUNNING'].includes(record.current_audio?.status || '')) timer = setTimeout(load, 2000)
  } catch (cause) { if (!lifetime.signal.aborted) { error.value = (cause as Error).message; meeting.value = null; analysis.value = null; candidates.value = []; tasks.value = []; job.value = null } }
  finally { busy.value = false }
}
async function submit() {
  saving.value = true; error.value = ''
  if (!pending || pending.text !== text.value) pending = { request_id: crypto.randomUUID(), text: text.value }
  try { await api<MeetingInput>(`/meetings/${id}/inputs`, { method: 'POST', body: JSON.stringify(pending), signal: lifetime.signal }); pending = undefined; text.value = ''; await load() }
  catch (cause) { error.value = (cause as Error).message }
  finally { saving.value = false }
}
async function retry() {
  saving.value = true
  try { await api(`/jobs/${job.value!.id}/retry`, { method: 'POST', signal: lifetime.signal }); await load() }
  catch (cause) { error.value = (cause as Error).message }
  finally { saving.value = false }
}
function candidateDraft(row: Candidate): Partial<TaskDraft> {
  const r = row.resolved, c = r.candidate
  return { title: c?.title || '', description: c?.description || '', source_excerpt: c?.source_quote || '', owner_id: r.owner_id, collaborator_ids: r.collaborator_ids, due_at: r.due_at, priority: c?.priority || 'NORMAL' }
}
async function publish(value: TaskDraft) {
  if (!selected.value) return
  saving.value = true; dialogError.value = ''
  try {
    const row = selected.value
    await api(`/candidates/${row.id}/${row.status === 'PUBLISHED' ? 'collaborators' : 'publish'}`, { method: row.status === 'PUBLISHED' ? 'PATCH' : 'POST', body: JSON.stringify(row.status === 'PUBLISHED' ? { collaborator_ids: value.collaborator_ids } : value), signal: lifetime.signal })
    selected.value = null; await load(); ElMessage.success('已保存')
  } catch (cause) { dialogError.value = (cause as Error).message }
  finally { saving.value = false }
}
async function dismiss(row: Candidate) {
  saving.value = true
  try { await api(`/candidates/${row.id}/dismiss`, { method: 'POST', signal: lifetime.signal }); await load() }
  catch (cause) { error.value = (cause as Error).message }
  finally { saving.value = false }
}
function openEdit() {
  const m = meeting.value!
  const local = new Date(new Date(m.starts_at).getTime() + 8 * 3600000).toISOString().slice(0, 16)
  Object.assign(edit, { title: m.title, starts_at: local, location: m.location || '', description: m.description || '', participant_ids: [...m.direct_participant_ids], department_ids: [...m.department_ids] })
  dialogError.value = ''; editing.value = true
}
async function saveMeeting() {
  saving.value = true; dialogError.value = ''
  try { await api(`/meetings/${id}`, { method: 'PATCH', body: JSON.stringify({ ...edit, starts_at: `${edit.starts_at}:00+08:00`, location: edit.location || null, description: edit.description || null }), signal: lifetime.signal }); editing.value = false; await load() }
  catch (cause) { dialogError.value = (cause as Error).message }
  finally { saving.value = false }
}
onMounted(async () => {
  await load()
  try { await directory.load(lifetime.signal); config.value = await api('/analysis-config', { signal: lifetime.signal }) }
  catch (cause) { if (!lifetime.signal.aborted) error.value = (cause as Error).message }
})
onUnmounted(() => { clearTimeout(timer); lifetime.abort() })
</script>
<template>
  <RouterLink class="text-link" to="/meetings">← 返回会议列表</RouterLink>
  <ElAlert v-if="error" :title="error" type="error" :closable="false" class="spaced" />
  <div class="page-heading spaced"><div><p class="eyebrow">会议详情</p><h1>{{ meeting?.title || '会议记录' }}</h1><p v-if="meeting" class="muted">{{ formatDate(meeting.starts_at) }} · {{ meeting.location || '地点未填写' }}</p></div><div class="actions"><ElButton :loading="busy" @click="load">刷新</ElButton><ElButton v-if="canManage && meeting" @click="openEdit">编辑会议</ElButton></div></div>
  <template v-if="meeting">
    <section class="panel"><p class="muted">参会人：{{ meeting.participant_ids.map(directory.name).join('、') || '未设置' }}</p><p v-if="meeting.description" class="prewrap spaced">{{ meeting.description }}</p></section>
    <DepartmentAttendance :meeting="meeting" :people="directory.people.value" :departments="directory.departments.value" :label="directory.label" @updated="load" />
    <MeetingSource :meeting-id="id" :current-version="meeting.current_input?.version" />
    <MeetingRecording :meeting-id="id" :can-manage="canManage" :current="meeting.current_audio" :max-mb="config?.audio_max_mb || 50" :available="config?.transcription_available === true" @updated="load" @use-text="value => text = value" />
    <section v-if="canManage" class="panel"><div class="panel-heading"><h2>提供会议文本</h2><ElButton v-if="config?.demo_text" :disabled="!!active || saving" @click="text = config!.demo_text!">载入演示样例</ElButton></div><ElAlert v-if="config?.mode === 'demo'" title="当前为演示模式：固定样例用于展示真实业务流程，不代表模型分析能力。" type="info" :closable="false" /><p v-if="meeting.current_input" class="muted">再次提交会创建新版本；已有任务不会自动重复派发。</p><ElInput v-model="text" type="textarea" :rows="6" maxlength="100000" show-word-limit placeholder="粘贴会议原文，提交后自动处理" aria-label="会议原文" class="spaced" :disabled="!!active || saving" /><ElButton type="primary" class="spaced" :loading="saving" :disabled="!text.trim() || !!active" @click="submit">提交并处理</ElButton></section>
    <section v-if="job" class="panel"><div class="panel-heading"><h2>处理进度</h2><ElTag :type="job.status === 'FAILED' ? 'danger' : job.status === 'SUCCEEDED' ? 'success' : 'info'">{{ labels[job.status] }}</ElTag></div><p v-if="active" class="muted">正在处理会议内容，完成后自动更新。</p><p v-else-if="job.status === 'SUCCEEDED'">{{ job.scope === 'ANALYSIS_ONLY' ? '分析已完成。' : '分析与任务生成阶段已完成，请查看下方结果。' }}</p><template v-else-if="job.status === 'FAILED'"><p>{{ errors[job.error_code || ''] || '处理遇到问题，已保存的阶段结果会在重试时复用。' }}</p><ElButton v-if="canManage" class="spaced" :loading="saving" @click="retry">重试处理</ElButton></template></section>
    <section v-if="analysis" class="panel"><div class="panel-heading"><h2>会议纪要</h2><ElTag v-if="['fixture','demo'].includes(analysis.mode)" type="warning">演示结果</ElTag></div><p class="prewrap">{{ analysis.summary }}</p><h3 class="spaced">主要决策</h3><ul v-if="analysis.decisions.length"><li v-for="item in analysis.decisions" :key="item">{{ item }}</li></ul><p v-else class="muted">没有记录明确决策</p><h3 class="spaced">风险与讨论</h3><ul v-if="analysis.risks.length"><li v-for="item in analysis.risks" :key="item">{{ item }}</li></ul><p v-else class="muted">没有记录风险</p></section>
    <section v-if="canManage && candidates.length" class="panel"><div class="panel-heading"><h2>行动事项与待补充</h2></div><article v-for="row in candidates" :key="row.id" class="candidate-row"><div><ElTag size="small">{{ labels[row.status] }}</ElTag><h3 class="spaced">{{ row.resolved.candidate?.title || '结构异常的事项' }}</h3><p v-if="row.resolved.candidate?.deadline_text" class="muted">原期限：{{ row.resolved.candidate.deadline_text }}</p><p v-if="row.status !== 'PUBLISHED' || row.needs_attention" class="muted">{{ row.resolved.issues.join('；') }}</p><blockquote v-if="row.resolved.candidate?.source_quote">{{ row.resolved.candidate.source_quote }}</blockquote></div><div class="actions"><RouterLink v-if="row.task_id && !row.task_deleted" :to="`/tasks/${row.task_id}`" class="text-link">查看任务</RouterLink><ElButton v-if="!row.task_deleted && row.needs_attention" :disabled="saving" @click="selected = row; dialogError = ''">{{ row.status === 'PUBLISHED' ? '补充协作人' : '补充并生成' }}</ElButton><ElButton v-if="!['PUBLISHED','DISMISSED'].includes(row.status)" :disabled="saving" text @click="dismiss(row)">忽略</ElButton><span v-if="row.task_deleted" class="muted">对应任务已删除</span></div></article></section>
    <section class="panel"><div class="panel-heading"><h2>相关任务</h2><RouterLink :to="`/tasks?meeting_id=${id}`" class="text-link">全部 {{ totalTasks }} 项</RouterLink></div><TaskList :tasks="tasks" empty-text="暂无你有权查看的任务" /></section>
    <details v-if="meeting.current_input" class="panel"><summary>查看会议原文 · 第 {{ meeting.current_input.version }} 版</summary><p class="prewrap spaced">{{ meeting.current_input.text }}</p></details>
  </template>
  <ElDialog :model-value="!!selected" :title="selected?.status === 'PUBLISHED' ? '补充协作人' : '补充并生成任务'" width="min(680px, 94vw)" :close-on-click-modal="!saving" @update:model-value="value => { if (!value && !saving) selected = null }"><ElAlert v-if="dialogError" :title="dialogError" type="error" :closable="false" /><template v-if="selected?.status === 'PUBLISHED'"><p class="muted">只补充协作人，其他任务内容保持原样。留空保存表示无需补充。</p><ElSelect v-model="selected.resolved.collaborator_ids" multiple filterable class="spaced" aria-label="补充协作人"><ElOption v-for="person in directory.people.value" :key="person.id" :value="person.id" :label="directory.label(person)" :disabled="person.is_active === false" /></ElSelect><ElButton class="spaced" type="primary" :loading="saving" @click="publish(candidateDraft(selected) as TaskDraft)">保存协作人</ElButton></template><TaskForm v-else-if="selected" :key="selected.id" :initial="candidateDraft(selected)" :people="directory.people.value" :label="directory.label" :busy="saving" submit-label="生成任务" @save="publish" /></ElDialog>
  <ElDialog v-model="editing" title="编辑会议" width="min(620px, 94vw)" :close-on-click-modal="!saving"><ElAlert v-if="dialogError" :title="dialogError" type="error" :closable="false" /><form class="business-form" @submit.prevent="saveMeeting"><label>会议标题<ElInput v-model="edit.title" maxlength="200" required /></label><label>开始时间（上海）<input v-model="edit.starts_at" type="datetime-local" class="native-input" required /></label><label>邀请部门<ElSelect v-model="edit.department_ids" multiple clearable aria-label="邀请部门"><ElOption v-for="d in directory.departments.value.filter(d => currentUser?.role === 'BOSS' || d.id === currentUser?.department_id)" :key="d.id" :value="d.id" :label="d.name" /></ElSelect></label><p class="muted">部门负责人自动参会，并安排本部门人员；也可以在下方直接点名。</p><label>参会人<ElSelect v-model="edit.participant_ids" multiple filterable><ElOption v-for="p in directory.people.value" :key="p.id" :value="p.id" :label="directory.label(p)" :disabled="p.is_active === false" /></ElSelect></label><label>地点<ElInput v-model="edit.location" maxlength="200" /></label><label>说明<ElInput v-model="edit.description" type="textarea" maxlength="10000" /></label><ElButton type="primary" native-type="submit" :loading="saving">保存会议</ElButton></form></ElDialog>
</template>

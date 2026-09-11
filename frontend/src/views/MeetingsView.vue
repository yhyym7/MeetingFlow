<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { ElAlert, ElButton, ElDialog, ElInput, ElSelect, ElOption, ElTable, ElTableColumn, ElPagination, ElEmpty } from 'element-plus'
import { RouterLink } from 'vue-router'
import { api } from '../api/client'
import type { MeetingSummary, Page, MeetingDetail } from '../api/types'
import { currentUser } from '../stores/session'
import { useDirectory } from '../composables/useDirectory'
import { formatDate } from '../utils/date'
import { router } from '../router'
const rows = ref<MeetingSummary[]>([]), page = ref(1), total = ref(0), q = ref(''), busy = ref(false), error = ref('')
const creating = ref(false), saving = ref(false), formError = ref('')
const form = reactive({ title: '', starts_at: '', location: '', description: '', participant_ids: [] as number[], department_ids: [] as number[] })
const isLeader = computed(() => ['BOSS', 'MANAGER'].includes(currentUser.value?.role || ''))
const directory = useDirectory()
let controller: AbortController | undefined
const lifetime = new AbortController()
async function load(reset = false) {
  if (reset) page.value = 1
  controller?.abort(); const request = new AbortController(); controller = request
  busy.value = true; error.value = ''; rows.value = []
  try { const result = await api<Page<MeetingSummary>>(`/meetings?page=${page.value}&q=${encodeURIComponent(q.value)}`, { signal: request.signal }); if (controller === request) { rows.value = result.items; total.value = result.total } }
  catch (cause) { if (!request.signal.aborted) error.value = (cause as Error).message }
  finally { if (controller === request) busy.value = false }
}
async function openCreate() {
  formError.value = ''; creating.value = true
  try { await directory.load(lifetime.signal) } catch (cause) { formError.value = (cause as Error).message }
}
async function create() {
  saving.value = true; formError.value = ''
  try {
    const meeting = await api<MeetingDetail>('/meetings', { method: 'POST', body: JSON.stringify({ ...form, starts_at: `${form.starts_at}:00+08:00`, location: form.location || null, description: form.description || null }), signal: lifetime.signal })
    creating.value = false; await router.push(`/meetings/${meeting.id}`)
  } catch (cause) { formError.value = (cause as Error).message }
  finally { saving.value = false }
}
onMounted(() => load())
onUnmounted(() => { controller?.abort(); lifetime.abort() })
</script>
<template>
  <div class="page-heading"><div><p class="eyebrow">会议空间</p><h1>{{ isLeader ? '会议管理' : '我参加的会议' }}</h1><p class="muted">查看会议记录、结论和后续行动。</p></div><ElButton v-if="isLeader" type="primary" @click="openCreate">创建会议</ElButton></div>
  <section class="panel"><form class="toolbar" @submit.prevent="load(true)"><ElInput v-model="q" placeholder="搜索会议标题" aria-label="搜索会议标题" clearable /><ElButton native-type="submit" :loading="busy">搜索</ElButton></form>
    <ElAlert v-if="error" :title="error" type="error" :closable="false" />
    <ElTable v-if="rows.length" :data="rows"><ElTableColumn label="会议" min-width="220"><template #default="{ row }"><RouterLink class="text-link" :to="`/meetings/${row.id}`">{{ row.title }}</RouterLink></template></ElTableColumn><ElTableColumn label="开始时间（上海）" min-width="150"><template #default="{ row }">{{ formatDate(row.starts_at) }}</template></ElTableColumn><ElTableColumn prop="location" label="地点" min-width="120" /></ElTable>
    <ElEmpty v-else :description="busy ? '正在加载会议' : '暂无符合条件的会议'" :image-size="64" />
    <ElPagination v-if="total > 20" v-model:current-page="page" :page-size="20" :total="total" layout="prev, pager, next" @current-change="load()" />
  </section>
  <ElDialog v-model="creating" title="创建会议" width="min(620px, 94vw)" :close-on-click-modal="!saving" :show-close="!saving">
    <ElAlert v-if="formError" :title="formError" type="error" :closable="false" />
    <form class="business-form" @submit.prevent="create"><label>会议标题<ElInput v-model="form.title" maxlength="200" aria-label="会议标题" required /></label><label>开始时间（上海时区）<input v-model="form.starts_at" type="datetime-local" class="native-input" aria-label="开始时间" required /></label><label>邀请部门<ElSelect v-model="form.department_ids" multiple clearable aria-label="邀请部门"><ElOption v-for="d in directory.departments.value.filter(d => currentUser?.role === 'BOSS' || d.id === currentUser?.department_id)" :key="d.id" :value="d.id" :label="d.name" /></ElSelect></label><p class="muted">部门负责人自动参会，并安排本部门人员；也可以在下方直接点名。</p><label>参会人<ElSelect v-model="form.participant_ids" multiple filterable aria-label="参会人"><ElOption v-for="person in directory.people.value" :key="person.id" :value="person.id" :label="directory.label(person)" :disabled="person.is_active === false" /></ElSelect></label><label>地点<ElInput v-model="form.location" maxlength="200" aria-label="地点" /></label><label>说明<ElInput v-model="form.description" type="textarea" maxlength="10000" aria-label="说明" /></label><ElButton type="primary" native-type="submit" :loading="saving" :disabled="!form.title.trim() || !form.starts_at">创建并打开</ElButton></form>
  </ElDialog>
</template>

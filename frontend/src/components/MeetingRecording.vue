<script setup lang="ts">
import { onUnmounted, ref } from 'vue'
import { ElAlert, ElButton, ElTag } from 'element-plus'
import { api } from '../api/client'
import type { MeetingAudio } from '../api/types'
import { formatDate } from '../utils/date'

const props = defineProps<{ meetingId: number; canManage: boolean; current: MeetingAudio | null; maxMb: number; available: boolean }>()
const emit = defineEmits<{ updated: []; useText: [text: string] }>()
const labels: Record<string, string> = { AWAITING_TRANSCRIPTION: '待转写', QUEUED: '排队中', RUNNING: '转写中', SUCCEEDED: '转写完成', FAILED: '处理失败' }
const file = ref<File | null>(null), input = ref<HTMLInputElement | null>(null)
const busy = ref(false), error = ref(''), saved = ref(false)
const lifetime = new AbortController()
let requestId = crypto.randomUUID()
function choose(event: Event) {
  file.value = (event.target as HTMLInputElement).files?.[0] || null
  requestId = crypto.randomUUID(); error.value = ''; saved.value = false
}
async function upload() {
  if (!file.value || busy.value) return
  const selected = file.value
  error.value = ''; saved.value = false
  if (!/\.(mp3|wav|m4a)$/i.test(selected.name)) { error.value = '仅支持 mp3、wav、m4a 录音'; return }
  if (!selected.size || selected.size > props.maxMb * 1024 * 1024) { error.value = `请选择非空且不超过 ${props.maxMb} MB 的录音`; return }
  busy.value = true
  try {
    const query = new URLSearchParams({ filename: selected.name, request_id: requestId })
    await api<MeetingAudio>(`/meetings/${props.meetingId}/audio?${query}`, {
      method: 'POST', body: selected, headers: { 'Content-Type': 'application/octet-stream' }, signal: lifetime.signal,
    }, 120000)
    file.value = null; if (input.value) input.value.value = ''
    requestId = crypto.randomUUID(); saved.value = true; emit('updated')
  } catch (cause) { if (!lifetime.signal.aborted) error.value = (cause as Error).message }
  finally { busy.value = false }
}
onUnmounted(() => lifetime.abort())
async function retry() {
  if (!props.current || busy.value) return
  busy.value = true; error.value = ''
  try { await api(`/meetings/${props.meetingId}/audio/${props.current.id}/transcribe`, { method: 'POST', signal: lifetime.signal }); emit('updated') }
  catch (cause) { error.value = (cause as Error).message }
  finally { busy.value = false }
}
</script>
<template>
  <section v-if="canManage || current" class="panel">
    <div class="panel-heading"><h2>会议录音</h2><ElTag v-if="current" :type="current.status === 'FAILED' ? 'danger' : 'info'">{{ labels[current.status] }}</ElTag></div>
    <p class="muted">{{ available ? '上传后在本机转写，再自动分析并生成任务。建议使用 1—3 分钟清晰普通话录音。' : '录音可保存和下载，转写服务尚未启用。可先提供会议文本继续处理。' }}</p>
    <template v-if="current">
      <p class="spaced prewrap">{{ current.original_name }} · {{ (current.size_bytes / 1024 / 1024).toFixed(2) }} MB</p>
      <p class="muted">上传于 {{ formatDate(current.created_at) }}</p>
      <a class="text-link" :href="`/api/meetings/${meetingId}/audio/${current.id}/download`" download>下载录音</a>
      <p class="spaced">{{ current.message }}</p>
      <ElButton v-if="canManage && available && ['FAILED', 'AWAITING_TRANSCRIPTION'].includes(current.status)" class="spaced" :loading="busy" @click="retry">{{ current.status === 'FAILED' ? '重试转写处理' : '开始转写' }}</ElButton>
      <details v-if="current.transcript" class="spaced"><summary>查看转写文本</summary><p class="prewrap">{{ current.transcript }}</p><ElButton v-if="canManage" @click="emit('useText', current.transcript)">使用此文本纠错</ElButton></details>
    </template>
    <template v-if="canManage">
      <p class="muted spaced">支持 mp3、wav、m4a，最大 {{ maxMb }} MB。每次上传一份录音；已有会议文本和任务会保留。</p>
      <label class="business-form">选择录音<input ref="input" type="file" accept=".mp3,.wav,.m4a" aria-label="选择录音" :disabled="busy" @change="choose" /></label>
      <ElButton class="spaced" type="primary" :disabled="!file" :loading="busy" @click="upload">{{ busy ? '上传中…' : '上传录音' }}</ElButton>
    </template>
    <ElAlert v-if="saved" :title="available ? '录音已保存，已排队自动处理。' : '录音已保存，等待接入转写服务。'" type="success" :closable="false" class="spaced" />
    <ElAlert v-if="error" :title="error" type="error" :closable="false" class="spaced" />
  </section>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { ElAlert, ElButton, ElInput, ElTag } from 'element-plus'
import { api } from '../api/client'
import type { Source } from '../api/types'
interface Answer { mode: string; search_mode: string | null; answer: string; sources: Source[] }
function sourceLink(source: Source) {
  const base = `/${source.kind === 'task' ? 'tasks' : 'meetings'}/${source.id}`
  return source.chunk_id && source.input_id ? `${base}?input_id=${source.input_id}&chunk_id=${source.chunk_id}#source-excerpt` : base
}
const question = ref(''), result = ref<Answer | null>(null), error = ref(''), busy = ref(false)
const examples = ['查看我的任务', '查看逾期任务', '查看近期会议', '统计任务进度']
const live = ref(false)
onMounted(async () => { try { live.value = (await api<{mode: string}>('/analysis-config')).mode === 'deepseek' } catch {} })
let controller: AbortController | undefined
async function ask(value = question.value) {
  if (!value.trim() || busy.value) return
  question.value = value; result.value = null; error.value = ''; busy.value = true
  controller?.abort(); const request = new AbortController(); controller = request
  try { result.value = await api<Answer>('/assistant/query', { method: 'POST', body: JSON.stringify({ question: value }), signal: request.signal }, 120000) }
  catch (cause) { if (!request.signal.aborted) error.value = (cause as Error).message }
  finally { busy.value = false }
}
onUnmounted(() => { controller?.abort(); result.value = null })
</script>
<template>
  <div class="page-heading"><div><p class="eyebrow">授权数据查询</p><h1>查询助手</h1><p class="muted">快速查看工作与会议，结果可以追溯到来源。</p></div><ElTag type="info">{{ live ? '模型问答' : '演示模式' }}</ElTag></div>
  <section class="panel"><ElAlert :title="live ? '可以自然语言查询工作与会议。下方按钮以及“查找会议：”“语义检索：”入口不调用收费模型；其他问法会使用模型。只读当前账号授权数据。' : '当前为固定问法演示模式。可用“查找会议：关键词”或“语义检索：问题”检索授权原文，不执行修改。'" type="info" :closable="false" /><div class="actions spaced"><ElButton v-for="item in examples" :key="item" :disabled="busy" @click="ask(item)">{{ item }}</ElButton></div><form class="business-form" @submit.prevent="ask()"><label>查询内容<ElInput v-model="question" type="textarea" :rows="3" maxlength="500" placeholder="例如：张三有哪些未完成任务？或 语义检索：接口资料由谁整理" aria-label="查询内容" :disabled="busy" /></label><ElButton type="primary" native-type="submit" :loading="busy" :disabled="!question.trim()">查询</ElButton></form></section>
  <ElAlert v-if="error" :title="error" type="error" :closable="false" />
  <section v-if="result" class="panel"><div class="panel-heading"><h2>查询结果</h2><ElTag v-if="result.search_mode" type="info">{{ result.search_mode === 'semantic' ? '本地语义检索' : '关键词检索' }}</ElTag></div><p class="prewrap">{{ result.answer }}</p><article v-for="source in result.sources" :key="`${source.kind}:${source.id}:${source.chunk_id || ''}`" class="event-row"><RouterLink class="text-link" :to="sourceLink(source)">{{ source.title }}</RouterLink><p v-if="source.input_version" class="muted">第 {{ source.input_version }} 版 · 原文片段</p><blockquote v-if="source.excerpt" class="prewrap">{{ source.excerpt }}</blockquote></article></section>
</template>

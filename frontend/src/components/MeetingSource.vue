<script setup lang="ts">
import { nextTick, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElAlert, ElTag } from 'element-plus'
import { api } from '../api/client'
import type { Source } from '../api/types'

const props = defineProps<{ meetingId: number; currentVersion?: number }>()
const route = useRoute(), source = ref<Source | null>(null), error = ref('')
let controller: AbortController | undefined
watch(() => [props.meetingId, route.query.input_id, route.query.chunk_id], async () => {
  controller?.abort(); source.value = null; error.value = ''
  const inputId = route.query.input_id, chunkId = route.query.chunk_id
  if (typeof inputId !== 'string' || typeof chunkId !== 'string' || !/^\d+$/.test(inputId) || !/^\d+$/.test(chunkId)) return
  const request = new AbortController(); controller = request
  try {
    source.value = await api<Source>(`/meetings/${props.meetingId}/inputs/${inputId}/chunks/${chunkId}`, { signal: request.signal })
    await nextTick()
    if (route.hash === '#source-excerpt') document.getElementById('source-excerpt')?.scrollIntoView({ block: 'start' })
  }
  catch (cause) { if (!request.signal.aborted) error.value = (cause as Error).message }
}, { immediate: true })
onUnmounted(() => controller?.abort())
</script>
<template>
  <section v-if="source || error" id="source-excerpt" class="panel">
    <div class="panel-heading"><h2>引用片段</h2><ElTag v-if="source">第 {{ source.input_version }} 版{{ source.input_version !== currentVersion ? ' · 历史原文' : '' }}</ElTag></div>
    <ElAlert v-if="error" :title="error" type="error" :closable="false" />
    <template v-if="source"><p class="muted">原文第 {{ (source.start_offset || 0) + 1 }}—{{ source.end_offset }} 字</p><blockquote class="prewrap">{{ source.excerpt }}</blockquote></template>
  </section>
</template>

<script setup lang="ts">
import { computed, reactive } from 'vue'
import { ElButton, ElInput, ElSelect, ElOption } from 'element-plus'
import { currentUser } from '../stores/session'
import type { Person, TaskDraft } from '../api/types'
const props = defineProps<{ initial?: Partial<TaskDraft>; people: Person[]; label: (person: Person) => string; busy: boolean; submitLabel?: string }>()
const owners = computed(() => currentUser.value?.role === 'MANAGER' ? props.people.filter(p => p.department_id === currentUser.value?.department_id) : props.people)
const emit = defineEmits<{ save: [value: TaskDraft] }>()
const form = reactive<TaskDraft>({ title: '', description: '', owner_id: null, collaborator_ids: [], due_at: null, priority: 'NORMAL', source_excerpt: '', ...props.initial })
const originalDue = form.due_at
const initialDay = originalDue && originalDue.length > 10 ? new Date(new Date(originalDue).getTime() + 8 * 3600000).toISOString().slice(0, 10) : originalDue
form.due_at = initialDay
function save() { emit('save', { ...form, collaborator_ids: [...form.collaborator_ids], due_at: form.due_at === initialDay ? originalDue : form.due_at || null }) }
</script>
<template>
  <form class="business-form" @submit.prevent="save">
    <label>任务名称<ElInput v-model="form.title" maxlength="200" aria-label="任务名称" required /></label>
    <label>任务说明<ElInput v-model="form.description" type="textarea" :rows="3" maxlength="10000" aria-label="任务说明" /></label>
    <div class="form-grid">
      <label>负责人<ElSelect v-model="form.owner_id" filterable placeholder="选择负责人" aria-label="负责人"><ElOption v-for="p in owners" :key="p.id" :value="p.id" :label="label(p)" :disabled="p.is_active === false" /></ElSelect></label>
      <label>优先级<ElSelect v-model="form.priority" aria-label="优先级"><ElOption label="普通" value="NORMAL" /><ElOption label="高" value="HIGH" /><ElOption label="低" value="LOW" /></ElSelect></label>
    </div>
    <label>协作人<ElSelect v-model="form.collaborator_ids" multiple filterable clearable placeholder="可不选" aria-label="协作人"><ElOption v-for="p in people" :key="p.id" :value="p.id" :label="label(p)" :disabled="p.is_active === false || p.id === form.owner_id" /></ElSelect></label>
    <label>截止日期<input v-model="form.due_at" type="date" aria-label="截止日期" class="native-input" /></label>
    <p class="muted">仅填写日期时，按上海时区当日 23:59 到期；可留空。</p>
    <label>相关原文摘录<ElInput v-model="form.source_excerpt" type="textarea" :rows="3" maxlength="10000" aria-label="相关原文摘录" /></label>
    <ElButton type="primary" native-type="submit" :loading="busy" :disabled="!form.title.trim() || !form.owner_id">{{ submitLabel || '保存任务' }}</ElButton>
  </form>
</template>

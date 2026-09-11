<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { ElAlert, ElButton, ElSelect, ElOption } from 'element-plus'
import type { Department, MeetingDetail, Person } from '../api/types'
import { api } from '../api/client'
const props = defineProps<{ meeting: MeetingDetail; people: Person[]; departments: Department[]; label: (person: Person) => string }>()
const emit = defineEmits<{ updated: [] }>()
const selected = reactive<Record<number, number[]>>({}), saving = ref(false), error = ref('')
watch(() => props.meeting.department_attendance, rows => { for (const row of rows) selected[row.department_id] = [...row.participant_ids] }, { immediate: true })
async function save(departmentId: number) {
  saving.value = true; error.value = ''
  try { await api(`/meetings/${props.meeting.id}/departments/${departmentId}/participants`, { method: 'PATCH', body: JSON.stringify({ participant_ids: selected[departmentId] || [] }) }); emit('updated') }
  catch (cause) { error.value = (cause as Error).message }
  finally { saving.value = false }
}
</script>
<template>
  <section v-if="meeting.department_ids.length" class="panel">
    <h2>部门参会安排</h2>
    <p class="muted spaced">受邀部门的负责人自动参会，并安排本部门人员；直接点名的参会人独立保留。尚未配置负责人的部门可由 Boss 安排名单。</p>
    <ElAlert v-if="error" :title="error" type="error" :closable="false" />
    <div v-for="row in meeting.department_attendance" :key="row.department_id" class="spaced">
      <h3>{{ departments.find(d => d.id === row.department_id)?.name || '历史部门' }}</h3>
      <div v-if="row.can_arrange" class="actions spaced">
        <ElSelect v-model="selected[row.department_id]" multiple filterable :aria-label="`部门参会人-${row.department_id}`" placeholder="选择本部门参会人员" style="min-width: 240px; flex: 1" :disabled="saving">
          <ElOption v-for="person in people.filter(p => p.department_id === row.department_id)" :key="person.id" :value="person.id" :label="label(person)" :disabled="person.is_active === false" />
        </ElSelect>
        <ElButton :loading="saving" @click="save(row.department_id)">保存部门名单</ElButton>
      </div>
      <p v-else class="muted spaced">{{ row.participant_ids.map(id => people.find(p => p.id === id)?.name || '历史人员').join('、') || '尚未安排额外参会人员' }}</p>
    </div>
  </section>
</template>

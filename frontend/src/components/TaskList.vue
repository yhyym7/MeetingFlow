<script setup lang="ts">
import { ElEmpty, ElTag } from 'element-plus'
import { RouterLink } from 'vue-router'
import type { TaskSummary } from '../api/types'
import { formatDate } from '../utils/date'
defineProps<{ tasks: TaskSummary[]; emptyText: string }>()
</script>
<template>
  <div v-if="tasks.length" class="task-list"><article v-for="task in tasks" :key="task.id" class="task-row"><span class="task-dot" :class="{ overdue: task.is_overdue }"></span><div class="task-copy"><h3><RouterLink class="text-link" :to="`/tasks/${task.id}`">{{ task.title }}</RouterLink></h3><p>{{ task.source_meeting_title || '独立任务' }} · {{ task.due_at ? `${formatDate(task.due_at)} 到期` : '未指定期限' }}</p></div><ElTag :type="task.is_overdue ? 'danger' : 'info'" effect="plain" size="small">{{ task.is_overdue ? '已逾期' : task.status === 'IN_PROGRESS' ? '进行中' : task.status === 'DONE' ? '已完成' : '待开始' }}</ElTag></article></div>
  <ElEmpty v-else :description="emptyText" :image-size="64" />
</template>

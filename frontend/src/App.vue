<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink, RouterView } from 'vue-router'
import { ElButton, ElMessage } from 'element-plus'
import { currentUser, signOut } from './stores/session'
import { router } from './router'
const leaving = ref(false)
const links = computed(() => [{ path: '/', title: '工作概览', icon: '◫' }, { path: '/meetings', title: '会议', icon: '▤' }, { path: '/tasks', title: '任务', icon: '◷' }, { path: '/assistant', title: '查询助手', icon: '✧' }, ...(currentUser.value?.role === 'BOSS' ? [{ path: '/people', title: '人员管理', icon: '♧' }] : [])])
async function logout() {
  leaving.value = true
  try { await signOut(); await router.replace('/login') }
  catch (error) { ElMessage.error(error instanceof Error ? error.message : '退出失败，请重试') }
  finally { leaving.value = false }
}
</script>
<template>
  <div v-if="currentUser" class="workspace">
    <aside class="sidebar">
      <RouterLink to="/" class="brand"><span class="brand-mark">M</span>MeetingFlow</RouterLink>
      <p class="sidebar-caption">会议协作空间</p>
      <nav aria-label="主导航"><RouterLink v-for="link in links" :key="link.path" :to="link.path" class="nav-item" :class="{ selected: link.path === '/' ? $route.path === '/' : $route.path.startsWith(link.path) }"><span aria-hidden="true">{{ link.icon }}</span>{{ link.title }}</RouterLink></nav>
      <div class="sidebar-note">让会议中的行动，<br>进入日常工作。</div>
    </aside>
    <div class="workspace-main">
      <header class="topbar"><span>工作台 <span class="divider">/</span> {{ currentUser.role === 'BOSS' ? '团队概览' : currentUser.role === 'MANAGER' ? '部门工作' : '我的工作' }}</span><div class="account"><span class="avatar">{{ currentUser.name.slice(0, 1) }}</span><span>{{ currentUser.name }}</span><span class="role-tag">{{ currentUser.role === 'BOSS' ? 'Boss' : currentUser.role === 'MANAGER' ? '部门负责人' : '员工' }}</span><ElButton text :loading="leaving" @click="logout">退出登录</ElButton></div></header>
      <main class="page-content"><RouterView :key="`${currentUser.id}:${$route.path}:${$route.query.meeting_id || ''}:${$route.query.overdue || ''}`" /></main>
    </div>
  </div>
  <RouterView v-else />
</template>

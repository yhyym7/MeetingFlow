import { createRouter, createWebHistory } from 'vue-router'
import { currentUser, restoreSession } from './stores/session'
export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: () => import('./views/LoginView.vue') },
    { path: '/', component: () => import('./views/DashboardView.vue') },
    { path: '/meetings', component: () => import('./views/MeetingsView.vue') },
    { path: '/meetings/:id', component: () => import('./views/MeetingDetailView.vue') },
    { path: '/tasks', component: () => import('./views/TasksView.vue') },
    { path: '/tasks/:id', component: () => import('./views/TaskDetailView.vue') },
    { path: '/assistant', component: () => import('./views/AssistantView.vue') },
    { path: '/people', component: () => import('./views/PeopleView.vue'), meta: { boss: true } },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
  scrollBehavior(to) { return to.hash ? { el: to.hash, top: 24, behavior: 'smooth' } : { top: 0 } },
})
router.beforeEach(async to => {
  await restoreSession()
  if (!currentUser.value && to.path !== '/login') return '/login'
  if (currentUser.value && to.path === '/login') return '/'
  if (to.meta.boss && currentUser.value?.role !== 'BOSS') return '/'
})

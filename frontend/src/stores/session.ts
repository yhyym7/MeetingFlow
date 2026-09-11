import { ref } from 'vue'
import { api, ApiError, cancelRequests } from '../api/client'
import type { CurrentUser } from '../api/types'
export const currentUser = ref<CurrentUser | null>(null)
export const sessionError = ref('')
let checked = false
export async function restoreSession() {
  if (checked) return
  try { currentUser.value = await api<CurrentUser>('/auth/me'); sessionError.value = ''; checked = true }
  catch (error) {
    if (error instanceof ApiError && error.status === 401) checked = true
    else sessionError.value = error instanceof Error ? error.message : '无法验证登录状态'
  }
}
export async function signIn(username: string, password: string) {
  cancelRequests()
  currentUser.value = await api<CurrentUser>('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) })
  checked = true; sessionError.value = ''
}
export function clearSession() { cancelRequests(); currentUser.value = null; checked = true }
export async function signOut() { await api<void>('/auth/logout', { method: 'POST' }); clearSession() }

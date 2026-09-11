<script setup lang="ts">
import { onMounted, onUnmounted, reactive, ref } from 'vue'
import { ElAlert, ElButton, ElDialog, ElInput, ElSelect, ElOption, ElSwitch, ElTable, ElTableColumn, ElTag } from 'element-plus'
import { api } from '../api/client'
import type { CurrentUser, Person } from '../api/types'
import { clearSession, currentUser } from '../stores/session'
import { useDirectory } from '../composables/useDirectory'
import { router } from '../router'
interface ManagedPerson extends Person { username: string; role: 'BOSS' | 'EMPLOYEE' | 'MANAGER'; is_active: boolean }
const users = ref<ManagedPerson[]>([]), page = ref(1), error = ref(''), busy = ref(false), saving = ref(false), dialogError = ref('')
const personDialog = ref(false), editingId = ref<number | null>(null), departmentDialog = ref(false), departmentId = ref<number | null>(null), departmentName = ref('')
const directory = useDirectory(), lifetime = new AbortController()
const form = reactive({ username: '', name: '', password: '', department_id: null as number | null, role: 'EMPLOYEE' as 'BOSS' | 'EMPLOYEE' | 'MANAGER', is_active: true })
async function load() {
  busy.value = true; error.value = ''
  try { const rows = await api<ManagedPerson[]>(`/users?page=${page.value}&page_size=20`, { signal: lifetime.signal }); users.value = rows; await directory.load(lifetime.signal) }
  catch (cause) { if (!lifetime.signal.aborted) { error.value = (cause as Error).message; users.value = [] } }
  finally { busy.value = false }
}
function openPerson(person?: ManagedPerson) {
  editingId.value = person?.id || null; dialogError.value = ''
  Object.assign(form, { username: '', name: '', password: '', department_id: null, role: 'EMPLOYEE', is_active: true }, person || {}, { password: '' })
  personDialog.value = true
}
async function savePerson() {
  saving.value = true; dialogError.value = ''
  const payload = editingId.value ? { name: form.name, department_id: form.department_id, role: form.role, is_active: form.is_active } : { username: form.username, name: form.name, password: form.password, department_id: form.department_id, role: form.role }
  try {
    const result = await api<CurrentUser & { is_active: boolean }>(editingId.value ? `/users/${editingId.value}` : '/users', { method: editingId.value ? 'PATCH' : 'POST', body: JSON.stringify(payload), signal: lifetime.signal })
    form.password = ''; personDialog.value = false
    if (result.id === currentUser.value?.id) {
      if (!result.is_active || result.role !== currentUser.value.role) { clearSession(); await router.replace('/login'); return }
      currentUser.value = result
    }
    await load()
  } catch (cause) { dialogError.value = (cause as Error).message }
  finally { saving.value = false }
}
function openDepartment(id: number | null = null, name = '') { departmentId.value = id; departmentName.value = name; dialogError.value = ''; departmentDialog.value = true }
async function saveDepartment() {
  saving.value = true; dialogError.value = ''
  try { await api(departmentId.value ? `/departments/${departmentId.value}` : '/departments', { method: departmentId.value ? 'PATCH' : 'POST', body: JSON.stringify({ name: departmentName.value }), signal: lifetime.signal }); departmentDialog.value = false; await load() }
  catch (cause) { dialogError.value = (cause as Error).message }
  finally { saving.value = false }
}
async function turn(delta: number) { page.value += delta; await load() }
onMounted(load)
onUnmounted(() => { lifetime.abort(); form.password = '' })
</script>
<template>
  <div class="page-heading"><div><p class="eyebrow">人员与部门</p><h1>人员管理</h1><p class="muted">维护账号、人员归属和启用状态。</p></div><ElButton type="primary" @click="openPerson()">新建账号</ElButton></div>
  <ElAlert v-if="error" :title="error" type="error" :closable="false" />
  <section class="panel"><ElTable :data="users"><ElTableColumn prop="name" label="姓名" min-width="100" /><ElTableColumn prop="username" label="账号" min-width="130" /><ElTableColumn label="部门" min-width="130"><template #default="{ row }">{{ directory.departments.value.find(d => d.id === row.department_id)?.name || '未分部门' }}</template></ElTableColumn><ElTableColumn label="角色" min-width="100"><template #default="{ row }">{{ row.role === 'BOSS' ? 'Boss' : row.role === 'MANAGER' ? '部门负责人' : '员工' }}</template></ElTableColumn><ElTableColumn label="状态" min-width="90"><template #default="{ row }"><ElTag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? '启用' : '停用' }}</ElTag></template></ElTableColumn><ElTableColumn label="操作" min-width="80"><template #default="{ row }"><ElButton text @click="openPerson(row as ManagedPerson)">编辑</ElButton></template></ElTableColumn></ElTable><div class="actions spaced"><ElButton :disabled="page === 1 || busy" @click="turn(-1)">上一页</ElButton><span>第 {{ page }} 页</span><ElButton :disabled="users.length < 20 || busy" @click="turn(1)">下一页</ElButton><ElButton :loading="busy" @click="load">刷新</ElButton></div></section>
  <section class="panel"><div class="panel-heading"><h2>部门</h2><ElButton @click="openDepartment()">新增部门</ElButton></div><div class="actions"><ElButton v-for="department in directory.departments.value" :key="department.id" @click="openDepartment(department.id, department.name)">{{ department.name }} · 编辑</ElButton></div></section>
  <ElDialog v-model="personDialog" :title="editingId ? '编辑人员' : '新建账号'" width="min(600px,94vw)" :close-on-click-modal="!saving" @closed="form.password = ''"><ElAlert v-if="dialogError" :title="dialogError" type="error" :closable="false" /><form class="business-form" @submit.prevent="savePerson"><label>姓名<ElInput v-model="form.name" aria-label="人员姓名" required maxlength="100" /></label><template v-if="!editingId"><label>登录账号<ElInput v-model="form.username" aria-label="登录账号" required maxlength="50" autocomplete="off" /></label><label>初始密码<ElInput v-model="form.password" type="password" show-password aria-label="初始密码" required minlength="8" maxlength="128" autocomplete="new-password" /></label></template><label>部门<ElSelect v-model="form.department_id" clearable aria-label="人员部门" @clear="form.department_id = null"><ElOption v-for="d in directory.departments.value" :key="d.id" :label="d.name" :value="d.id" /></ElSelect></label><label>角色<ElSelect v-model="form.role" aria-label="人员角色"><ElOption label="员工" value="EMPLOYEE" /><ElOption label="部门负责人（经理/部长）" value="MANAGER" /><ElOption label="Boss" value="BOSS" /></ElSelect></label><label v-if="editingId">启用账号<ElSwitch v-model="form.is_active" aria-label="启用账号" /></label><p v-if="editingId" class="muted">停用、调岗或修改角色会撤销该账号的现有登录会话。部门负责人必须指定部门。至少保留一位启用的管理者。</p><ElButton type="primary" native-type="submit" :loading="saving">保存人员</ElButton></form></ElDialog>
  <ElDialog v-model="departmentDialog" :title="departmentId ? '编辑部门' : '新增部门'" width="min(500px,94vw)" :close-on-click-modal="!saving"><ElAlert v-if="dialogError" :title="dialogError" type="error" :closable="false" /><form class="business-form" @submit.prevent="saveDepartment"><label>部门名称<ElInput v-model="departmentName" aria-label="部门名称" required maxlength="100" /></label><ElButton type="primary" native-type="submit" :loading="saving">保存部门</ElButton></form></ElDialog>
</template>

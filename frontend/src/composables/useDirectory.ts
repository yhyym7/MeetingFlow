import { ref } from 'vue'
import { api } from '../api/client'
import type { Person, Department } from '../api/types'

export function useDirectory() {
  const people = ref<Person[]>([]), departments = ref<Department[]>([])
  async function all<T>(path: string, signal?: AbortSignal): Promise<T[]> {
    const result: T[] = []
    for (let page = 1; ; page++) {
      const rows = await api<T[]>(`${path}?page=${page}&page_size=100`, { signal })
      result.push(...rows)
      if (rows.length < 100) return result
    }
  }
  async function load(signal?: AbortSignal) {
    const [users, groups] = await Promise.all([all<Person>('/users', signal), all<Department>('/departments', signal)])
    people.value = users; departments.value = groups
  }
  function name(id: number) { return people.value.find(p => p.id === id)?.name || '历史人员' }
  function label(person: Person) { return `${person.name} · ${departments.value.find(d => d.id === person.department_id)?.name || '未分部门'}${person.is_active === false ? '（已停用）' : ''}` }
  return { people, departments, load, name, label }
}

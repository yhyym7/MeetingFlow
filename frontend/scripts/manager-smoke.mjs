import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright-core'

const raw = await readFile(new URL('../../backend/.env.demo', import.meta.url), 'utf8')
const password = raw.match(/^DEMO_PASSWORD=(.*)$/m)[1].trim().replace(/^['"]|['"]$/g, '')
const browser = await chromium.launch({ channel: 'chrome', headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
const page = await context.newPage(), base = 'http://127.0.0.1:5173'
const errors = []; page.on('pageerror', error => errors.push(error.name))
async function login(name) {
  await page.goto(base + '/login')
  await page.getByLabel('账号', { exact: true }).fill(name)
  await page.getByLabel('密码', { exact: true }).fill(password)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await page.locator('.stat-grid').waitFor()
}
async function logout() { await page.getByRole('button', { name: '退出登录' }).click(); await page.waitForURL('**/login') }
async function json(path) { const r = await context.request.get(base + '/api' + path); assert.equal(r.status(), 200); return r.json() }
async function choose(label, option) {
  const box = page.getByRole('combobox', { name: label, exact: true })
  await box.focus(); await box.press('ArrowDown')
  await page.getByRole('option', { name: option, exact: true }).click()
  await box.press('Escape')
}
async function ensureMeeting(title, byDepartment) {
  const existing = (await json('/meetings?q=' + encodeURIComponent(title))).items.find(m => m.title === title)
  if (existing) { await page.goto(base + '/meetings/' + existing.id); return existing.id }
  await page.goto(base + '/meetings')
  await page.getByRole('button', { name: '创建会议', exact: true }).click()
  await page.getByLabel('会议标题', { exact: true }).fill(title)
  await page.getByLabel('开始时间', { exact: true }).fill('2026-09-15T10:00')
  if (byDepartment) await choose('邀请部门', '技术部')
  await choose('参会人', '李四 · 技术部')
  await page.getByRole('button', { name: '创建并打开', exact: true }).click()
  await page.waitForURL(/\/meetings\/\d+$/)
  return Number(page.url().split('/').pop())
}
async function screenshot(name) { await page.screenshot({ path: fileURLToPath(new URL('../../work/screenshots/' + name, import.meta.url)), fullPage: true }) }

try {
  await login('boss')
  assert.equal(await page.evaluate(async () => (await (await fetch('/api/analysis-config')).json()).mode), 'demo', 'This demo test requires demo analysis mode; real paid calls are disabled for this script.')
  const users = await json('/users?page_size=100')
  const tech = users.find(p => p.username === 'tech_manager'), zhang = users.find(p => p.username === 'zhangsan'), li = users.find(p => p.username === 'lisi')
  assert.equal(tech.role, 'MANAGER')
  const bossMeeting = await ensureMeeting('经理演示：Boss 邀请技术部', true)
  await page.getByRole('heading', { name: '部门参会安排', exact: true }).waitFor()
  await screenshot('boss-department-invitation.png')
  await logout()
  await login('tech_manager')
  await page.getByText('部门工作概览', { exact: true }).waitFor()
  assert.equal(await page.getByRole('link', { name: '人员管理', exact: true }).count(), 0)
  await page.goto(base + '/meetings/' + bossMeeting)
  await page.getByRole('heading', { name: '部门参会安排', exact: true }).waitFor()
  assert.equal(await page.getByRole('button', { name: '编辑会议', exact: true }).count(), 0)
  assert.equal(await page.getByRole('button', { name: '提交并处理', exact: true }).count(), 0)
  const before = await json('/meetings/' + bossMeeting)
  if (!before.department_attendance.find(d => d.department_id === tech.department_id).participant_ids.includes(zhang.id)) {
    await choose('部门参会人-' + tech.department_id, '张三 · 技术部')
    await page.getByRole('button', { name: '保存部门名单', exact: true }).click()
    await page.waitForResponse(r => r.url().endsWith('/api/meetings/' + bossMeeting) && r.request().method() === 'GET')
  }
  const after = await json('/meetings/' + bossMeeting)
  assert.ok(after.participant_ids.includes(zhang.id) && after.participant_ids.includes(li.id))
  assert.ok(after.direct_participant_ids.includes(li.id))
  await screenshot('manager-attendance.png')
  await logout()
  await login('zhangsan')
  await page.goto(base + '/meetings/' + bossMeeting)
  await page.getByRole('heading', { name: '经理演示：Boss 邀请技术部', exact: true }).waitFor()
  assert.equal(await page.getByRole('button', { name: '保存部门名单', exact: true }).count(), 0)
  await logout()
  await login('product_manager')
  assert.equal((await context.request.get(base + '/api/meetings/' + bossMeeting)).status(), 404)
  await logout()
  await login('tech_manager')
  const ownMeeting = await ensureMeeting('经理演示：技术部工作安排', false)
  let tasks = await json('/meetings/' + ownMeeting + '/tasks')
  if (!tasks.items.length) {
    await page.getByRole('button', { name: '载入演示样例', exact: true }).click()
    await page.getByRole('button', { name: '提交并处理', exact: true }).click()
    await page.getByRole('link', { name: '整理接口清单', exact: true }).waitFor({ timeout: 30000 })
    tasks = await json('/meetings/' + ownMeeting + '/tasks')
  }
  const taskId = tasks.items.find(t => t.title === '整理接口清单').id
  await page.goto(base + '/tasks/' + taskId)
  await page.getByRole('button', { name: '编辑任务', exact: true }).click()
  const ownerBox = page.getByRole('combobox', { name: '负责人', exact: true })
  await ownerBox.focus(); await ownerBox.press('ArrowDown')
  assert.equal(await page.getByRole('option', { name: '王五 · 产品部', exact: true }).count(), 0)
  await ownerBox.press('Escape')
  await page.getByRole('dialog').getByRole('button', { name: 'Close this dialog', exact: true }).click()
  await page.getByRole('dialog').waitFor({ state: 'hidden' })
  if (await page.getByRole('button', { name: '标记完成', exact: true }).count()) {
    await page.getByRole('button', { name: '标记完成', exact: true }).click()
    await page.getByRole('button', { name: '重新打开', exact: true }).waitFor()
  }
  await screenshot('manager-task.png')
  await page.setViewportSize({ width: 390, height: 844 })
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
  await screenshot('manager-mobile-task.png')
  assert.equal(errors.length, 0)
  console.log(`PASS: department invitation, manager delegation, direct invite preservation, employee access, cross-department denial, manager automatic publication and task controls. Meetings ${bossMeeting}/${ownMeeting}, task ${taskId}.`)
} finally {
  await context.request.post(base + '/api/auth/logout', { headers: { Origin: base } }).catch(() => {})
  await browser.close()
}

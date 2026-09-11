import assert from 'node:assert/strict'
import { readFile, mkdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright-core'

// Intentionally keeps one named demonstration meeting for the user to inspect.
const raw = await readFile(new URL('../../backend/.env.demo', import.meta.url), 'utf8')
const password = raw.match(/^DEMO_PASSWORD=(.*)$/m)[1].trim().replace(/^['"]|['"]$/g, '')
const screenshots = new URL('../../work/screenshots/', import.meta.url)
await mkdir(screenshots, { recursive: true })
const base = 'http://127.0.0.1:5173'
const browser = await chromium.launch({ channel: 'chrome', headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 1050 } })
const page = await context.newPage()
const runtimeErrors = []
page.on('pageerror', error => runtimeErrors.push(error.name))
async function login(name) {
  await page.goto(base + '/login')
  await page.getByLabel('账号', { exact: true }).fill(name)
  await page.getByLabel('密码', { exact: true }).fill(password)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await page.locator('.stat-grid').waitFor()
}
async function logout() { await page.getByRole('button', { name: '退出登录' }).click(); await page.waitForURL('**/login') }
async function get(path) { return page.evaluate(async path => { const r = await fetch('/api' + path); return { status: r.status, data: await r.json() } }, path) }
async function choose(label, option) {
  await page.getByRole('combobox', { name: label, exact: true }).focus()
  await page.getByRole('combobox', { name: label, exact: true }).press('ArrowDown')
  await page.getByRole('option', { name: option, exact: true }).click()
  await page.keyboard.press('Escape')
}
async function shot(name) { await page.screenshot({ path: fileURLToPath(new URL(name, screenshots)), fullPage: true }) }
try {
  await login('boss')
  assert.equal(await page.evaluate(async () => (await (await fetch('/api/analysis-config')).json()).mode), 'demo', 'This demo test requires demo analysis mode; real paid calls are disabled for this script.')
  const title = '演示验收：接口与测试安排'
  const existing = await get('/meetings?q=' + encodeURIComponent(title))
  let meetingId = existing.data.items.find(row => row.title === title)?.id
  if (!meetingId) {
    await page.getByRole('link', { name: '会议', exact: true }).click()
    await page.getByRole('button', { name: '创建会议', exact: true }).click()
    await page.getByLabel('会议标题', { exact: true }).fill(title)
    await page.getByLabel('开始时间', { exact: true }).fill('2026-09-09T10:00')
    await choose('参会人', '张三 · 技术部')
    await choose('参会人', '李四 · 技术部')
    await page.getByLabel('地点', { exact: true }).fill('演示会议室')
    await page.getByRole('button', { name: '创建并打开' }).click()
    await page.waitForURL(/\/meetings\/\d+$/)
    meetingId = Number(new URL(page.url()).pathname.split('/').pop())
  } else await page.goto(`${base}/meetings/${meetingId}`)
  const meeting = await get(`/meetings/${meetingId}`)
  if (!meeting.data.current_input) {
    await page.getByRole('button', { name: '载入演示样例' }).click()
    await page.getByRole('button', { name: '提交并处理' }).click()
  }
  await page.getByText('处理完成', { exact: true }).waitFor({ timeout: 20000 })
  const original = page.locator('.candidate-row').filter({ hasText: '整理接口清单' })
  await original.getByText('已生成任务', { exact: true }).waitFor()
  const missing = page.locator('.candidate-row').filter({ hasText: '整理测试用例' })
  if (await missing.getByRole('button', { name: '补充并生成' }).count()) {
    await missing.getByRole('button', { name: '补充并生成' }).click()
    await choose('负责人', '李四 · 技术部')
    await page.getByRole('button', { name: '生成任务', exact: true }).click()
    await page.getByRole('dialog').waitFor({ state: 'hidden' })
  }
  await shot('meeting-detail.png')
  const published = await get(`/meetings/${meetingId}/tasks`)
  assert.equal(published.data.total, 2)
  const taskId = published.data.items.find(row => row.title === '整理接口清单').id
  await logout()

  await login('wangwu')
  await page.goto(`${base}/tasks/${taskId}`)
  await page.getByRole('heading', { name: '任务信息', exact: true }).waitFor()
  assert.equal(await page.getByRole('button', { name: '标记完成' }).count(), 0)
  assert.equal(await page.getByRole('link', { name: '查看会议', exact: true }).count(), 0)
  await page.getByLabel('进展内容').fill('演示反馈：字段已核对，等待负责人确认。')
  await page.getByRole('button', { name: '提交进展' }).click()
  await page.locator('.event-row').filter({ hasText: '演示反馈：字段已核对' }).first().waitFor()
  assert.equal((await get(`/meetings/${meetingId}`)).status, 404)
  await shot('collaborator-task.png')
  await logout()

  await login('zhangsan')
  await page.goto(`${base}/tasks/${taskId}`)
  await page.getByRole('heading', { name: '任务信息', exact: true }).waitFor()
  if (await page.getByRole('button', { name: '重新打开' }).count()) {
    await page.getByRole('button', { name: '重新打开' }).click()
    await page.getByRole('button', { name: '标记完成' }).waitFor()
  }
  if (await page.getByRole('button', { name: '开始任务' }).count()) {
    await page.getByRole('button', { name: '开始任务' }).click()
    await page.getByRole('button', { name: '设为待开始' }).waitFor()
  }
  await page.getByRole('button', { name: '标记完成' }).click()
  await page.getByRole('button', { name: '重新打开' }).waitFor()
  assert.equal((await get(`/tasks/${taskId}`)).data.status, 'DONE')
  await page.setViewportSize({ width: 390, height: 844 })
  await shot('mobile-task-detail.png')
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), 'Task mobile layout overflows')
  await page.setViewportSize({ width: 1440, height: 1050 })
  await logout()

  await login('zhaoliu')
  await page.goto(`${base}/tasks/${taskId}`)
  await page.getByRole('alert').waitFor()
  assert.equal(await page.getByRole('heading', { name: '任务信息', exact: true }).count(), 0)
  await logout()

  await login('boss')
  await page.goto(`${base}/tasks/${taskId}`)
  await page.getByRole('button', { name: '重新打开' }).waitFor()
  await page.getByRole('button', { name: '编辑任务' }).click()
  await page.getByLabel('任务说明', { exact: true }).fill('演示验收完成，保留此任务用于查看协作动态。')
  await page.getByRole('button', { name: '保存任务', exact: true }).click()
  await page.getByRole('dialog').waitFor({ state: 'hidden' })
  assert.equal((await get(`/tasks/${taskId}`)).data.status, 'DONE')
  assert.equal(runtimeErrors.length, 0, 'Browser runtime errors')
  await shot('completed-task.png')
  console.log(`PASS: meeting creation, demo processing, missing-owner correction, collaborator feedback, owner completion, Boss edit, access denial, mobile layout. Demonstration meeting id=${meetingId}, task id=${taskId}.`)
} finally {
  await context.request.post(`${base}/api/auth/logout`, { headers: { Origin: base } }).catch(() => {})
  await browser.close()
}

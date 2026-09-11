import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { randomUUID } from 'node:crypto'
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
async function query(question) {
  await page.getByLabel('查询内容').fill(question)
  await page.getByRole('button', { name: '查询', exact: true }).click()
  await page.getByRole('heading', { name: '查询结果', exact: true }).waitFor()
}
try {
  await login('boss')
  assert.equal(await page.evaluate(async () => (await (await fetch('/api/analysis-config')).json()).mode), 'demo', 'This demo test requires demo analysis mode; real paid calls are disabled for this script.')
  await page.getByRole('link', { name: '人员管理', exact: true }).click()
  await page.getByRole('heading', { name: '人员管理', exact: true }).waitFor()
  let testRow = page.getByRole('row').filter({ hasText: 'demo_validation' })
  await page.getByRole('row').filter({ hasText: '王总' }).waitFor()
  if (await testRow.count() === 0) {
    await page.getByRole('button', { name: '新建账号', exact: true }).click()
    await page.getByLabel('人员姓名').fill('演示校验账号')
    await page.getByLabel('登录账号').fill('demo_validation')
    await page.getByLabel('初始密码').fill(randomUUID())
    await page.getByRole('button', { name: '保存人员', exact: true }).click()
    await page.getByRole('dialog').waitFor({ state: 'hidden' })
    await testRow.waitFor()
  }
  await testRow.getByRole('button', { name: '编辑', exact: true }).click()
  const toggle = page.getByRole('switch', { name: '启用账号', exact: true })
  if (await toggle.getAttribute('aria-checked') === 'true') await page.getByRole('dialog').locator('.el-switch').click()
  await page.getByRole('button', { name: '保存人员', exact: true }).click()
  await page.getByRole('dialog').waitFor({ state: 'hidden' })
  await testRow.getByText('停用', { exact: true }).waitFor()
  await page.getByRole('row').filter({ hasText: '王总' }).getByRole('button', { name: '编辑', exact: true }).click()
  await page.getByRole('dialog').locator('.el-switch').click()
  await page.getByRole('button', { name: '保存人员', exact: true }).click()
  await page.getByRole('dialog').getByRole('alert').waitFor()
  await page.getByRole('dialog').getByRole('button', { name: /close/i }).click()
  await page.getByRole('dialog').waitFor({ state: 'hidden' })
  await page.screenshot({ path: fileURLToPath(new URL('../../work/screenshots/people.png', import.meta.url)), fullPage: true })
  await page.getByRole('link', { name: '查询助手', exact: true }).click()
  await query('查找会议：接口清单')
  const source = page.getByRole('link', { name: '演示验收：接口与测试安排', exact: true })
  await source.waitFor()
  await page.screenshot({ path: fileURLToPath(new URL('../../work/screenshots/assistant.png', import.meta.url)), fullPage: true })
  await query('把所有任务改为已完成')
  assert.equal(await source.count(), 0)
  await logout()
  await login('wangwu')
  assert.equal(await page.getByRole('link', { name: '人员管理', exact: true }).count(), 0)
  await page.goto(base + '/people')
  await page.waitForURL(base + '/')
  await page.goto(base + '/assistant')
  await query('查找会议：接口清单')
  assert.equal(await page.getByRole('link', { name: '演示验收：接口与测试安排', exact: true }).count(), 0)
  await query('查看我的任务')
  await page.getByRole('link', { name: '整理接口清单', exact: true }).first().waitFor()
  assert.equal(errors.length, 0)
  console.log('PASS: create/disable demo_validation account, last Boss protection, staff navigation guard, assistant sources and role filtering.')
} finally {
  await context.request.post(base + '/api/auth/logout', { headers: { Origin: base } }).catch(() => {})
  await browser.close()
}

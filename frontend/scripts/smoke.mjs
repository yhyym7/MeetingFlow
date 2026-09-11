import assert from 'node:assert/strict'
import { readFile, mkdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright-core'

// Local demo credentials stay in memory; never print credentials or persist browser storage.
const raw = await readFile(new URL('../../backend/.env.demo', import.meta.url), 'utf8')
const match = raw.match(/^DEMO_PASSWORD=(.*)$/m)
assert(match, 'Local demo credential is missing')
const password = match[1].trim().replace(/^['"]|['"]$/g, '')
const output = new URL('../../work/screenshots/', import.meta.url)
await mkdir(output, { recursive: true })
const browser = await chromium.launch({ channel: 'chrome', headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 1050 } })
const page = await context.newPage()
const errors = []
page.on('pageerror', error => errors.push(error.name))
const base = 'http://127.0.0.1:5173'
async function login(username) {
  await page.getByLabel('账号', { exact: true }).fill(username)
  await page.getByLabel('密码', { exact: true }).fill(password)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await page.locator('.stat-grid').waitFor()
}
async function shot(name) { await page.screenshot({ path: fileURLToPath(new URL(name, output)), fullPage: true }) }
try {
  await page.goto(base)
  await page.waitForURL('**/login')
  await shot('login.png')
  await page.getByLabel('账号', { exact: true }).fill('boss')
  await page.getByLabel('密码', { exact: true }).fill('incorrect-demo-password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await page.getByRole('alert').waitFor()
  assert.equal(new URL(page.url()).pathname, '/login')
  await login('boss')
  const actual = await page.evaluate(async () => (await fetch('/api/dashboard')).json())
  assert.equal(await page.locator('.stat-card strong').first().textContent(), String(actual.statistics.total))
  assert.equal(await page.locator('.attention-strip').count(), 1)
  await shot('boss-dashboard.png')
  await page.getByRole('link', { name: '会议', exact: true }).click()
  await page.waitForURL('**/meetings')
  await page.getByRole('link', { name: '工作概览', exact: true }).click()
  await page.waitForURL(base + '/')
  await page.reload()
  await page.locator('.stat-grid').waitFor()
  await page.route('**/api/dashboard', route => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: '数据服务暂时不可用，请稍后重试' }) }))
  await page.getByRole('button', { name: '刷新概览' }).click()
  await page.getByRole('alert').waitFor()
  assert.equal(await page.locator('.stat-grid').count(), 0)
  await page.unroute('**/api/dashboard')
  await page.getByRole('button', { name: '刷新概览' }).click()
  await page.locator('.stat-grid').waitFor()
  await page.getByRole('button', { name: '退出登录' }).click()
  await page.waitForURL('**/login')
  assert.equal(await page.evaluate(async () => (await fetch('/api/dashboard')).status), 401)
  await page.goBack()
  await page.waitForURL('**/login')
  assert.equal(await page.locator('.stat-grid').count(), 0)
  await login('zhaoliu')
  assert.equal(await page.locator('.attention-strip').count(), 0)
  const employee = await page.evaluate(async () => (await fetch('/api/dashboard')).json())
  assert.equal(await page.locator('.stat-card strong').first().textContent(), String(employee.statistics.total))
  await shot('employee-dashboard.png')
  await page.setViewportSize({ width: 390, height: 844 })
  await shot('mobile-dashboard.png')
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), 'Mobile page overflows')
  // Revoke the real server session, then verify protected requests clear the UI.
  assert.equal(await page.evaluate(async () => (await fetch('/api/auth/logout', { method: 'POST' })).status), 204)
  await page.getByRole('button', { name: '刷新概览' }).click()
  await page.waitForURL('**/login')
  assert.equal(await page.locator('.stat-grid').count(), 0)
  assert.equal(errors.length, 0, 'Browser runtime errors detected')
  console.log('PASS: login errors, Boss/employee data, navigation, reload, service failure, logout/back, session revocation, mobile layout; 4 screenshots saved.')
} finally {
  await context.request.post(`${base}/api/auth/logout`, { headers: { Origin: base } }).catch(() => {})
  await browser.close()
}

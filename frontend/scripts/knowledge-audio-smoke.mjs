import assert from 'node:assert/strict'
import { readFile, mkdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright-core'

// Keeps one named meeting and an explicitly labelled synthetic silent WAV.
const raw = await readFile(new URL('../../backend/.env.demo', import.meta.url), 'utf8')
const password = raw.match(/^DEMO_PASSWORD=(.*)$/m)[1].trim().replace(/^['"]|['"]$/g, '')
const screenshots = new URL('../../work/screenshots/', import.meta.url)
await mkdir(screenshots, { recursive: true })
const base = 'http://127.0.0.1:5173'
const browser = await chromium.launch({ channel: 'chrome', headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 1050 } })
const page = await context.newPage(), errors = []
page.on('pageerror', error => errors.push(error.name))
async function login(username) {
  await page.goto(base + '/login')
  await page.getByLabel('账号', { exact: true }).fill(username)
  await page.getByLabel('密码', { exact: true }).fill(password)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await page.locator('.stat-grid').waitFor()
}
async function logout() {
  await page.getByRole('button', { name: '退出登录' }).click()
  await page.waitForURL('**/login')
}
async function request(path, method = 'GET', body) {
  return page.evaluate(async ({ path, method, body }) => {
    const response = await fetch('/api' + path, { method, headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined })
    return { status: response.status, data: await response.json() }
  }, { path, method, body })
}
async function shot(name) { await page.screenshot({ path: fileURLToPath(new URL(name, screenshots)), fullPage: true }) }
const wav = Buffer.alloc(44 + 1600)
wav.write('RIFF', 0); wav.writeUInt32LE(wav.length - 8, 4); wav.write('WAVEfmt ', 8)
wav.writeUInt32LE(16, 16); wav.writeUInt16LE(1, 20); wav.writeUInt16LE(1, 22)
wav.writeUInt32LE(8000, 24); wav.writeUInt32LE(16000, 28); wav.writeUInt16LE(2, 32); wav.writeUInt16LE(16, 34)
wav.write('data', 36); wav.writeUInt32LE(1600, 40)
try {
  await login('boss')
  const safeConfig = (await request('/analysis-config')).data
  assert.equal(safeConfig.mode, 'demo', 'Use demo mode for this test to avoid paid model calls.')
  assert.equal(safeConfig.transcription_available, false, 'This script checks storage-only mode; disable ASR first.')
  const title = '演示验收：录音保存与分片检索'
  const existing = await request('/meetings?q=' + encodeURIComponent(title))
  let meetingId = existing.data.items.find(row => row.title === title)?.id
  if (!meetingId) {
    const people = (await request('/users')).data
    const owner = people.find(row => row.name === '张三')
    assert(owner, 'Demo participant is missing')
    const result = await request('/meetings', 'POST', { title, starts_at: '2026-09-10T10:00:00+08:00', participant_ids: [owner.id] })
    assert.equal(result.status, 201)
    meetingId = result.data.id
  }
  await page.goto(`${base}/meetings/${meetingId}`)
  await page.getByRole('heading', { name: '会议录音', exact: true }).waitFor()
  let detail = (await request(`/meetings/${meetingId}`)).data
  if (!detail.current_input) {
    await page.getByRole('button', { name: '载入演示样例' }).click()
    await page.getByRole('button', { name: '提交并处理' }).click()
  }
  await page.getByText('处理完成', { exact: true }).waitFor({ timeout: 20000 })
  detail = (await request(`/meetings/${meetingId}`)).data
  const inputId = detail.current_input.id
  await page.getByLabel('选择录音', { exact: true }).setInputFiles({ name: '无效录音.wav', mimeType: 'audio/wav', buffer: Buffer.from('not audio') })
  await page.getByRole('button', { name: '上传录音', exact: true }).click()
  await page.getByText('文件内容与录音格式不符，或文件已损坏', { exact: true }).waitFor()
  if (!detail.current_audio) {
    await page.getByLabel('选择录音', { exact: true }).setInputFiles({ name: '上传验证静音样本（非会议录音）.wav', mimeType: 'audio/wav', buffer: wav })
    await page.getByRole('button', { name: '上传录音', exact: true }).click()
    await page.getByText('录音已保存，等待接入转写服务。', { exact: true }).waitFor()
  }
  await page.reload()
  await page.getByRole('link', { name: '下载录音', exact: true }).waitFor()
  detail = (await request(`/meetings/${meetingId}`)).data
  assert.equal(detail.current_input.id, inputId)
  const downloadEvent = page.waitForEvent('download')
  await page.getByRole('link', { name: '下载录音', exact: true }).click()
  const download = await downloadEvent
  assert.equal(download.suggestedFilename(), '上传验证静音样本（非会议录音）.wav')
  assert.equal(await download.failure(), null)
  await shot('audio-meeting-desktop.png')
  await page.goto(base + '/assistant')
  await page.getByLabel('查询内容').fill('查找会议：接口清单')
  await page.getByRole('button', { name: '查询', exact: true }).click()
  await page.getByRole('link', { name: title, exact: true }).first().waitFor()
  await shot('chunk-search-desktop.png')
  await page.getByRole('link', { name: title, exact: true }).first().click()
  await page.locator('#source-excerpt blockquote').waitFor()
  assert((await page.locator('#source-excerpt').textContent()).includes('接口清单'))
  assert(new URL(page.url()).searchParams.has('chunk_id'))
  await page.setViewportSize({ width: 390, height: 844 })
  await shot('audio-source-mobile.png')
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), 'Mobile layout overflows')
  await page.setViewportSize({ width: 1440, height: 1050 })
  await logout()
  await login('zhangsan')
  await page.goto(`${base}/meetings/${meetingId}`)
  await page.getByRole('link', { name: '下载录音', exact: true }).waitFor()
  assert.equal(await page.getByLabel('选择录音', { exact: true }).count(), 0)
  await logout()
  await login('wangwu')
  const denied = await page.evaluate(async path => (await fetch(path)).status,
    `/api/meetings/${meetingId}/audio/${detail.current_audio.id}/download`)
  assert.equal(denied, 404)
  assert.equal(errors.length, 0, 'Browser runtime errors')
  await logout()
  console.log(`PASS: invalid upload, private audio save/download, retained text, source links, mobile layout and access control. Meeting id=${meetingId}, audio id=${detail.current_audio.id}. Synthetic silent WAV only; no ASR verification.`)
} finally { await context.close(); await browser.close() }

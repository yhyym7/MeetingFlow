// Explicit opt-in validation: up to one analysis and two assistant model calls.
import assert from 'node:assert/strict'
import { readFile, writeFile, mkdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright-core'
const base = 'http://127.0.0.1:5173'
const raw = await readFile(new URL('../../backend/.env.demo', import.meta.url), 'utf8')
const password = raw.match(/^DEMO_PASSWORD=(.*)$/m)[1].trim().replace(/^['"]|['"]$/g, '')
const reportPath = new URL('../../work/live-validation.json', import.meta.url)
const oldReport = await readFile(reportPath, 'utf8').then(JSON.parse).catch(() => null)
const output = new URL('../../work/screenshots/', import.meta.url)
await mkdir(output, { recursive: true })
const browser = await chromium.launch({ channel: 'chrome', headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
const page = await context.newPage(), errors = []
page.on('pageerror', error => errors.push(error.name))
async function login(username) {
  await page.goto(base + '/login')
  await page.getByLabel('账号', { exact: true }).fill(username)
  await page.getByLabel('密码', { exact: true }).fill(password)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await page.locator('.stat-grid').waitFor()
}
async function logout() { await page.getByRole('button', { name: '退出登录' }).click(); await page.waitForURL('**/login') }
async function request(path, body) {
  return page.evaluate(async ({path,body}) => {
    const r = await fetch('/api'+path, body ? {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)} : {})
    return {status:r.status, data:await r.json()}
  }, {path,body})
}
try {
  await login('boss')
  assert.equal((await request('/analysis-config')).data.mode, 'deepseek')
  const title = '真实模型验收：接口与测试安排（合成语音）'
  let meeting = (await request('/meetings?q='+encodeURIComponent(title))).data.items.find(x=>x.title===title)
  if (!meeting) {
    const people = (await request('/users?page_size=100')).data
    const created = await request('/meetings', {title,starts_at:new Date().toISOString(),participant_ids:people.filter(x=>['zhangsan','lisi'].includes(x.username)).map(x=>x.id)})
    assert.equal(created.status,201); meeting=created.data
  }
  await page.goto(`${base}/meetings/${meeting.id}`)
  await page.getByRole('heading',{name:'会议录音',exact:true}).waitFor()
  let detail = (await request(`/meetings/${meeting.id}`)).data
  if (!detail.current_audio) {
    await page.getByLabel('选择录音',{exact:true}).setInputFiles(fileURLToPath(new URL('../../work/asr-spoken-validation.wav',import.meta.url)))
    await page.getByRole('button',{name:'上传录音',exact:true}).click()
  }
  await page.getByText('处理完成',{exact:true}).waitFor({timeout:90000})
  detail=(await request(`/meetings/${meeting.id}`)).data
  assert.equal(detail.current_audio.status,'SUCCEEDED')
  const analysis=(await request(`/meetings/${meeting.id}/analysis`)).data
  assert.equal(analysis.mode,'deepseek')
  const tasks=(await request(`/meetings/${meeting.id}/tasks`)).data.items
  assert(tasks.length>=1, 'Expected at least one real extracted task')
  const task=tasks.find(x=>x.title.includes('接口'))
  assert(task,'Expected an interface-related task')
  await page.screenshot({path:fileURLToPath(new URL('live-meeting.png',output)),fullPage:true})
  await page.goto(base+'/assistant')
  await page.getByLabel('查询内容').fill('语义检索：接口资料由谁整理')
  await page.getByRole('button',{name:'查询',exact:true}).click()
  await page.getByRole('heading',{name:'查询结果',exact:true}).waitFor({timeout:60000})
  assert(await page.locator('.event-row').count()>0)
  let answer=oldReport?.meeting_id===meeting.id ? oldReport.answer : null
  if (!answer) {
    const response = await request('/assistant/query',{question:'会议里关于接口清单作了什么决定？'})
    assert.equal(response.status,200); answer=response.data
    assert.equal(answer.mode,'deepseek'); assert.equal(answer.tool_calls,1)
    assert(answer.trace.includes('CLASSIFY_MODEL')); assert(answer.sources.length)
    await writeFile(reportPath,JSON.stringify({meeting_id:meeting.id,task_id:task.id,transcript:detail.current_audio.transcript,analysis_summary:analysis.summary,answer},null,2))
  }
  await page.screenshot({path:fileURLToPath(new URL('live-semantic.png',output)),fullPage:true})
  await logout(); await login('zhangsan')
  await page.goto(`${base}/tasks/${task.id}`)
  await page.getByRole('heading',{name:'任务信息',exact:true}).waitFor()
  if (await page.getByRole('button',{name:'开始任务',exact:true}).count()) await page.getByRole('button',{name:'开始任务',exact:true}).click()
  if (await page.getByRole('button',{name:'标记完成',exact:true}).count()) await page.getByRole('button',{name:'标记完成',exact:true}).click()
  await page.getByRole('button',{name:'重新打开',exact:true}).waitFor()
  await page.setViewportSize({width:390,height:844})
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth))
  await page.screenshot({path:fileURLToPath(new URL('live-task-mobile.png',output)),fullPage:true})
  await logout()
  assert.equal(errors.length,0)
  console.log(`PASS real ASR -> DeepSeek analysis -> task completion; local semantic retrieval and model assistant. Meeting ${meeting.id}, task ${task.id}. Speech was synthesized locally, not a real meeting recording.`)
} finally { await context.close(); await browser.close() }

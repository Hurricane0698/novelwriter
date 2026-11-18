import { test, expect, type APIRequestContext } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import { createServer } from 'node:http'
import type { AddressInfo } from 'node:net'
import { authHeaders, blockExternalNoise, getSessionToken } from '../../fixtures/api-helpers'
import { waitForInitialNovelReady } from '../../fixtures/novel-ready'

const API = process.env.E2E_API_ORIGIN ?? 'http://localhost:8000'
const RUN = Math.random().toString(36).slice(2, 6)

const createdNovelIds: number[] = []
let sessionToken = ''

async function apiDelete(request: APIRequestContext, path: string) {
  return request.delete(`${API}${path}`, { headers: authHeaders(sessionToken) })
}

test.beforeAll(async ({ request }) => {
  sessionToken = await getSessionToken(request)
})

test.afterAll(async ({ request }) => {
  if (!sessionToken) return
  for (const id of createdNovelIds) {
    await apiDelete(request, `/api/novels/${id}`)
  }
})

test.beforeEach(async ({ page }) => {
  await blockExternalNoise(page)
  await page.goto('/library')
})

test('opens imported chapters in Studio', async ({ page }) => {
  test.slow()
  test.setTimeout(180_000)


  const [chooser] = await Promise.all([
    page.waitForEvent('filechooser'),
    page.getByTestId('library-import-novel').click(),
  ])

  const fileName = `首发验证_${Date.now()}_${RUN}.txt`
  const fileContent = Buffer.from('第一章\n这里是导入后进入正式工作台的内容。\n', 'utf-8')
  await chooser.setFiles({ name: fileName, mimeType: 'text/plain', buffer: fileContent })

  await expect(page).toHaveURL(/\/novel\/\d+$/, { timeout: 60_000 })
  const novelId = Number(page.url().split('/').pop())
  expect(Number.isFinite(novelId)).toBeTruthy()
  createdNovelIds.push(novelId)

  await waitForInitialNovelReady(page)

  const chapterList = page.getByTestId('studio-rail-chapters')
  await expect(chapterList.getByRole('button', { name: /第\s*1\s*章/ })).toBeVisible({ timeout: 30_000 })
  await expect(page.getByTestId('studio-preparation-gate')).toHaveCount(0)
})

test('write a first chapter, confirm an evidenced change, then continue and adopt it', async ({ page, request }) => {
  const quote = '沈梨把铜钥匙交给林秋。'
  const nextScene = '林秋用铜钥匙打开了西门。'
  const owner = '由林秋保管'
  await page.getByRole('button', { name: '新建作品' }).click()
  await expect(page).toHaveURL(/\/novel\/\d+$/)
  const novelId = Number(new URL(page.url()).pathname.split('/').pop())
  createdNovelIds.push(novelId)
  const editor = page.getByTestId('chapter-editor-textarea')
  await expect(editor).toBeEditable()
  await page.getByRole('button', { name: '未命名作品' }).click()
  await page.getByLabel('修改书名').fill('渡口来信')
  await page.getByLabel('修改书名').press('Enter')
  await expect(page.getByRole('button', { name: '渡口来信' })).toBeVisible()
  await editor.fill(quote)
  await page.getByRole('button', { name: '保存', exact: true }).click()
  await page.reload()
  await expect(page.getByText(quote, { exact: true })).toBeVisible()

  const world = `${API}/api/novels/${novelId}/world/entities`
  const headers = authHeaders(sessionToken)
  const created = await request.post(world, { headers, data: {
    name: '铜钥匙', entity_type: 'Item', description: '由沈梨保管',
  } })
  expect(created.ok()).toBeTruthy()
  const key = await created.json()
  expect((await request.post(`${world}/confirm`, { headers, data: { ids: [key.id] } })).ok()).toBeTruthy()

  const prompts: string[] = []
  const provider = createServer(async (req, res) => {
    const chunks = []
    for await (const chunk of req) chunks.push(chunk)
    const body = JSON.parse(Buffer.concat(chunks).toString())
    const envelope = { id: 'test', model: body.model, created: 0 }
    if (body.stream) {
      prompts.push(body.messages.map((m: { content: string }) => m.content).join('\n'))
      res.writeHead(200, { 'content-type': 'text/event-stream' })
      const chunk = { ...envelope, object: 'chat.completion.chunk',
        choices: [{ index: 0, delta: { content: nextScene }, finish_reason: 'stop' }] }
      res.end(`data: ${JSON.stringify(chunk)}\n\ndata: [DONE]\n\n`)
    } else {
      const content = JSON.stringify({ answer: '铜钥匙易手。', suggestions: [{
        kind: 'update_entity', target_id: key.id, title: '铜钥匙的持有人', summary: '记录交接后的持有人。',
        delta: { description: owner }, references: [{ id: 'e0', quote }],
      }] })
      res.writeHead(200, { 'content-type': 'application/json' })
      res.end(JSON.stringify({ ...envelope, object: 'chat.completion',
        choices: [{ index: 0, message: { role: 'assistant', content }, finish_reason: 'stop' }] }))
    }
  })
  await new Promise<void>(resolve => provider.listen(0, '127.0.0.1', resolve))
  try {
    await page.goto('/settings')
    await page.getByLabel('API Base URL').fill(`http://127.0.0.1:${(provider.address() as AddressInfo).port}/v1`)
    await page.getByLabel('API Key', { exact: true }).fill('novwr-local-test-key')
    await page.getByLabel('Model Name').fill('novwr-local-test')
    await page.getByRole('link', { name: '作品库' }).click()
    await page.getByRole('link', { name: /渡口来信/ }).click()

    await page.getByTestId('chapter-world-changes').click()
    const card = page.getByTestId(/^copilot-suggestion-/).filter({ hasText: '铜钥匙的持有人' })
    await expect(card).toContainText(quote, { timeout: 20_000 })
    await expect(card).toContainText(key.description)
    await expect(card).toContainText(owner)
    async function savedKey() { return (await request.get(`${world}/${key.id}`, { headers })).json() }
    expect((await savedKey()).description).toBe(key.description)
    await card.getByRole('button', { name: '采纳', exact: true }).click()
    await expect.poll(async () => (await savedKey()).description).toBe(owner)
    expect((await savedKey()).source_refs[0].quote).toBe(quote)

    await page.getByTestId('studio-rail-continuation').click()
    await page.getByTestId('studio-generate-button').click()
    const adopt = page.getByTestId('results-adopt-button')
    await expect(adopt).toBeEnabled({ timeout: 20_000 })
    expect(prompts.some(prompt => prompt.includes(owner))).toBe(true)
    await adopt.click()
    await expect(page).toHaveURL(new RegExp(`/novel/${novelId}\\?chapter=2$`))
    await page.reload()
    await expect(page.getByText(nextScene, { exact: true })).toBeVisible()
  } finally {
    provider.closeAllConnections()
    await new Promise<void>(resolve => provider.close(() => resolve()))
  }
})

test('Markdown import → source preview → save → native export', async ({ page }) => {
  test.slow()
  test.setTimeout(180_000)

  const [chooser] = await Promise.all([
    page.waitForEvent('filechooser'),
    page.getByTestId('library-import-novel').click(),
  ])
  const fileName = `Markdown_闭环_${Date.now()}_${RUN}.md`
  const fileContent = Buffer.from(
    '# 第一卷\n'
    + '## 第一章 开端\n'
    + '\n'
    + '这里有 **粗体**。\n'
    + '\n'
    + '### 章内小节\n'
    + '- 列表项\n'
    + '# 第二卷\n'
    + '## 第二章 继续\n'
    + '> 引用\n',
    'utf-8',
  )
  await chooser.setFiles({ name: fileName, mimeType: 'text/markdown', buffer: fileContent })

  await expect(page).toHaveURL(/\/novel\/\d+$/, { timeout: 60_000 })
  const novelId = Number(page.url().split('/').pop())
  expect(Number.isFinite(novelId)).toBeTruthy()
  createdNovelIds.push(novelId)
  await waitForInitialNovelReady(page)

  await expect(page.getByTestId('markdown-content').getByText('粗体')).toBeVisible()
  await expect(page.getByRole('heading', { level: 3, name: '章内小节' })).toBeVisible()

  await page.getByRole('button', { name: '编辑' }).click()
  const sourceEditor = page.getByTestId('chapter-editor-textarea')
  await sourceEditor.fill('**修改后正文**\n\n### 实时预览\n\n- 新列表项\n')
  await page.getByRole('button', { name: '预览' }).click()
  const editorPreview = page.getByTestId('markdown-editor-preview')
  await expect(editorPreview.getByText('修改后正文')).toBeVisible()
  await expect(editorPreview.getByRole('heading', { level: 3, name: '实时预览' })).toBeVisible()

  await page.getByRole('button', { name: '保存' }).click()
  await expect(page.getByTestId('markdown-editor-preview')).toHaveCount(0)
  await page.reload()
  await expect(page.getByTestId('markdown-content').getByText('修改后正文')).toBeVisible({ timeout: 30_000 })

  await page.getByRole('button', { name: '更多操作' }).click()
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: '导出全部章节' }).click(),
  ])
  expect(download.suggestedFilename()).toMatch(/\.md$/)
  const downloadPath = await download.path()
  expect(downloadPath).not.toBeNull()
  const exported = await readFile(downloadPath!, 'utf-8')
  expect(exported).toContain('# 第一卷\n## 第 1 章 · 开端\n**修改后正文**')
  expect(exported).toContain('# 第二卷\n## 第 2 章 · 继续\n> 引用\n')
})

test('import supports 30MB txt (boundary)', async ({ page }) => {
  test.slow()
  test.setTimeout(180_000)

  const maxBytes = 30 * 1024 * 1024
  const header = 'Chapter 1\nhello\n\nChapter 2\n'
  const headerBuf = Buffer.from(header, 'utf-8')
  const fillerSize = maxBytes - headerBuf.length
  expect(fillerSize).toBeGreaterThan(0)
  const buf = Buffer.concat([headerBuf, Buffer.alloc(fillerSize, 'a')])
  expect(buf.length).toBe(maxBytes)

  const [chooser] = await Promise.all([
    page.waitForEvent('filechooser'),
    page.getByTestId('library-import-novel').click(),
  ])
  await chooser.setFiles({
    name: `30MB_boundary_${Date.now()}_${RUN}.txt`,
    mimeType: 'text/plain',
    buffer: buf,
  })

  await expect(page).toHaveURL(/\/novel\/\d+$/, { timeout: 150_000 })
  const novelId = Number(page.url().split('/').pop())
  expect(Number.isFinite(novelId)).toBeTruthy()
  createdNovelIds.push(novelId)

  const chapterList = page.getByTestId('studio-rail-chapters')
  const chapterCount = chapterList.getByText(/共\s*2\s*章/)
  await waitForInitialNovelReady(page)

  // Parser should split into two chapters, but the page should remain responsive
  // (first chapter content is small).
  await expect(chapterCount).toBeVisible({ timeout: 30_000 })
  await expect(chapterList.getByRole('button', { name: /第\s*1\s*章/ })).toBeVisible()
})

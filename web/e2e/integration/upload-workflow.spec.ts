import { test, expect, type APIRequestContext } from '@playwright/test'
import { authHeaders, blockExternalNoise, createApiSession, ensureLoggedIn } from '../fixtures/api-helpers'

const API = 'http://localhost:8000'
const RUN = Math.random().toString(36).slice(2, 6)
const AUTH_SCOPE = 'upload-workflow'

const createdNovelIds: number[] = []
let sessionToken = ''

async function apiDelete(request: APIRequestContext, path: string) {
  return request.delete(`${API}${path}`, { headers: authHeaders(sessionToken) })
}

async function ensureUploadConsent(page: import('@playwright/test').Page) {
  const createButton = page.getByTestId('library-create-novel')
  if (await createButton.isEnabled()) return

  const checkbox = page.getByRole('checkbox').first()
  if (await checkbox.isVisible()) {
    await checkbox.click()
    await expect(createButton).toBeEnabled({ timeout: 15_000 })
  }
}

test.beforeAll(async ({ request }) => {
  sessionToken = (await createApiSession(request, { scope: AUTH_SCOPE })).accessToken
})

test.afterAll(async ({ request }) => {
  if (!sessionToken) return
  for (const id of createdNovelIds) {
    await apiDelete(request, `/api/novels/${id}`)
  }
})

test.beforeEach(async ({ page }) => {
  await blockExternalNoise(page)
  await ensureLoggedIn(page, { scope: AUTH_SCOPE })
})

test('import → enter writing desk → continue → adopt', async ({ page }) => {
  await page.goto('/library')
  await ensureUploadConsent(page)

  const [chooser] = await Promise.all([
    page.waitForEvent('filechooser'),
    page.getByTestId('library-create-novel').click(),
  ])

  const fileName = `导入测试_${Date.now()}_${RUN}.txt`
  const fileContent = Buffer.from('第一章\n这里是导入的内容。\n', 'utf-8')
  await chooser.setFiles({ name: fileName, mimeType: 'text/plain', buffer: fileContent })

  await expect(page).toHaveURL(/\/novel\/\d+$/, { timeout: 60_000 })
  const novelId = Number(page.url().split('/').pop())
  expect(Number.isFinite(novelId)).toBeTruthy()
  createdNovelIds.push(novelId)

  // New novels are empty-world by default; onboarding replaces the chapter UI until dismissed.
  const onboarding = page.getByTestId('world-onboarding')
  const chapterBtn = page.getByRole('button', { name: /第\s*1\s*章/ })
  await Promise.any([
    onboarding.waitFor({ state: 'visible', timeout: 15_000 }),
    chapterBtn.waitFor({ state: 'visible', timeout: 15_000 }),
  ])
  if (await onboarding.isVisible()) {
    await page.getByTestId('world-onboarding-dismiss').click()
    await expect(page).toHaveURL(new RegExp(`/world/${novelId}`), { timeout: 15_000 })
    await page.getByRole('link', { name: '返回作品' }).click()
    await expect(page).toHaveURL(new RegExp(`/novel/${novelId}$`), { timeout: 15_000 })
  }

  // Sidebar label should NOT duplicate the heading ("第 1 章 · 第一章 ...")
  await expect(chapterBtn).toBeVisible({ timeout: 15_000 })
  await expect(chapterBtn).not.toContainText('第一章')

  // Enter writing desk
  await page.getByTestId('novel-continue-button').click()
  await expect(page).toHaveURL(new RegExp(`/novel/${novelId}/chapter/1/write$`))
  await expect(page.getByText('续写设置')).toBeVisible()

  // Mock the LLM streaming endpoint: deterministic NDJSON, no real model calls.
  const ndjson = [
    JSON.stringify({ type: 'start', variant: 0, total_variants: 3 }),
    JSON.stringify({ type: 'token', variant: 0, content: '他抬头看见远处的灯火。' }),
    JSON.stringify({
      type: 'variant_done',
      variant: 0,
      continuation_id: 101,
      content: '他抬头看见远处的灯火。',
    }),
    JSON.stringify({
      type: 'variant_done',
      variant: 1,
      continuation_id: 102,
      content: '风从走廊尽头吹来，带着旧纸张的气味。',
    }),
    JSON.stringify({
      type: 'variant_done',
      variant: 2,
      continuation_id: 103,
      content: '门轴轻响，像某种迟到的回答。',
    }),
    JSON.stringify({ type: 'done', continuation_ids: [101, 102, 103] }),
  ].join('\n')
  await page.route('**/api/novels/*/continue/stream', route =>
    route.fulfill({ status: 200, body: ndjson, headers: { 'content-type': 'application/x-ndjson' } }),
  )

  // Generate continuation (navigates to results page).
  await page.getByTestId('workspace-generate-button').click()
  await expect(page).toHaveURL(new RegExp(`/novel/${novelId}/chapter/1/results`), { timeout: 15_000 })

  // Wait until streaming completes and adopting is enabled.
  const adoptBtn = page.getByTestId('results-adopt-button')
  await expect(adoptBtn).toBeEnabled({ timeout: 15_000 })
  await adoptBtn.click()

  // Should return to novel detail and a new chapter should appear.
  await expect(page).toHaveURL(new RegExp(`/novel/${novelId}$`), { timeout: 15_000 })
  await expect(page.getByRole('button', { name: /第\s*2\s*章/ })).toBeVisible({ timeout: 15_000 })
})

test('import supports 30MB txt (boundary)', async ({ page }) => {
  test.slow()
  test.setTimeout(180_000)

  await page.goto('/library')
  await ensureUploadConsent(page)

  const maxBytes = 30 * 1024 * 1024
  const header = 'Chapter 1\nhello\n\nChapter 2\n'
  const headerBuf = Buffer.from(header, 'utf-8')
  const fillerSize = maxBytes - headerBuf.length
  expect(fillerSize).toBeGreaterThan(0)
  const buf = Buffer.concat([headerBuf, Buffer.alloc(fillerSize, 'a')])
  expect(buf.length).toBe(maxBytes)

  const [chooser] = await Promise.all([
    page.waitForEvent('filechooser'),
    page.getByTestId('library-create-novel').click(),
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

  // Dismiss empty-world onboarding so the chapter sidebar is visible.
  const onboarding = page.getByTestId('world-onboarding')
  const chapterCount = page.getByText(/共\s*2\s*章/)
  await Promise.any([
    onboarding.waitFor({ state: 'visible', timeout: 30_000 }),
    chapterCount.waitFor({ state: 'visible', timeout: 30_000 }),
  ])
  if (await onboarding.isVisible()) {
    await page.getByTestId('world-onboarding-dismiss').click()
    await expect(page).toHaveURL(new RegExp(`/world/${novelId}`), { timeout: 15_000 })
    await page.getByRole('link', { name: '返回作品' }).click()
    await expect(page).toHaveURL(new RegExp(`/novel/${novelId}$`), { timeout: 15_000 })
  }

  // Parser should split into two chapters, but the page should remain responsive
  // (first chapter content is small).
  await expect(chapterCount).toBeVisible({ timeout: 30_000 })
  await expect(page.getByRole('button', { name: /第\s*1\s*章/ })).toBeVisible()
})

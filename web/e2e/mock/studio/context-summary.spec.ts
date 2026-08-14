import { expect, test } from '@playwright/test'
import { mockAllApiRoutes } from '../../fixtures/api-helpers'

test('reviews and confirms a distant chapter recap before continuation uses it', async ({ page }, testInfo) => {
  await mockAllApiRoutes(page)
  await page.addInitScript(() => {
    localStorage.setItem('novwr_world_onboarding_dismissed_1_2026-01-01T00:00:00Z', '1')
  })

  const summaries: Array<Record<string, unknown>> = []
  let continuationPayload: Record<string, unknown> | null = null

  await page.route('**/api/novels/1/context-summaries', async route => {
    const method = route.request().method()
    if (method === 'GET') return route.fulfill({ json: summaries })
    if (method !== 'POST') return route.abort('blockedbyclient')
    const range = route.request().postDataJSON() as { start_chapter: number; end_chapter: number }
    const created = {
      id: 41,
      novel_id: 1,
      start_chapter: range.start_chapter,
      end_chapter: range.end_chapter,
      title: `第${range.start_chapter}—${range.end_chapter}章远期剧情回顾`,
      content: 'AI 初稿：汪淼开始怀疑眼前发生的一切。',
      model: 'mock-model',
      review_status: 'draft',
      is_stale: false,
      created_at: '2026-08-14T00:00:00Z',
      updated_at: '2026-08-14T00:00:00Z',
    }
    summaries.splice(0, summaries.length, created)
    return route.fulfill({ status: 201, json: created })
  })

  await page.route('**/api/novels/1/context-summaries/41', async route => {
    if (route.request().method() !== 'PUT') return route.abort('blockedbyclient')
    const update = route.request().postDataJSON() as {
      content: string
      review_status: 'draft' | 'confirmed'
    }
    const updated = { ...summaries[0], ...update, is_stale: false }
    summaries.splice(0, summaries.length, updated)
    return route.fulfill({ json: updated })
  })

  const ndjson = [
    JSON.stringify({ type: 'start', variant: 0, total_variants: 1 }),
    JSON.stringify({ type: 'token', variant: 0, content: '倒计时仍在继续。' }),
    JSON.stringify({
      type: 'variant_done',
      variant: 0,
      continuation_id: 101,
      content: '倒计时仍在继续。',
    }),
    JSON.stringify({
      type: 'done',
      continuation_ids: [101],
      debug: {
        context_chapters: 5,
        injected_systems: [],
        injected_entities: [],
        injected_relationships: [],
        injected_context_summaries: ['第1—2章远期剧情回顾'],
        relevant_entity_ids: [],
        ambiguous_keywords_disabled: [],
        drift_warnings: [],
        prose_warnings: [],
      },
    }),
  ].join('\n')
  await page.route('**/api/novels/1/continue/stream', async route => {
    continuationPayload = route.request().postDataJSON() as Record<string, unknown>
    return route.fulfill({
      status: 200,
      body: ndjson,
      headers: { 'content-type': 'application/x-ndjson' },
    })
  })

  await page.goto('/novel/1')
  await page.getByTestId('studio-rail-continuation').click()
  await expect(page).toHaveURL(/\/novel\/1\?stage=write$/)
  await expect(page.getByText('续写设置')).toBeVisible()
  await page.getByRole('button', { name: '高级设置' }).click()
  await page.getByRole('textbox', { name: '回顾章节范围' }).fill('1-2')
  await page.getByRole('button', { name: '生成回顾' }).click()

  const dialog = page.getByTestId('context-summary-review-dialog')
  await expect(dialog).toBeVisible()
  await expect(dialog.getByText('待确认')).toBeVisible()
  const editor = dialog.getByTestId('context-summary-content')
  await editor.fill('作者核对：汪淼已经确认倒计时与自己的视野有关。')
  await dialog.getByRole('button', { name: '确认并用于本次续写' }).click()

  await expect(dialog).toHaveCount(0)
  await expect(page.getByRole('checkbox', { name: /本次续写使用/ })).toBeChecked()
  await page.screenshot({
    path: testInfo.outputPath('context-summary-confirmed.png'),
    fullPage: true,
  })

  await page.getByTestId('studio-generate-button').click()
  await expect(page).toHaveURL(/\/novel\/1\?stage=results&chapter=2$/)
  await expect.poll(() => continuationPayload).not.toBeNull()
  expect(continuationPayload).toMatchObject({ context_summary_ids: [41] })
  await expect(page.getByText('倒计时仍在继续。')).toBeVisible()
})

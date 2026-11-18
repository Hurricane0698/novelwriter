import { createHash } from 'node:crypto'
import { expect, test } from '@playwright/test'
import { mockAllApiRoutes } from '../../fixtures/api-helpers'

const hash = (text: string) => createHash('sha256').update(text).digest('hex')

for (const finish of ['return-and-save', 'desktop-exit']) {
  test(`retains a closed candidate editor: ${finish}`, async ({ page }, testInfo) => {
    const errors: string[] = []
    page.on('pageerror', (error) => errors.push(error.message))
    await mockAllApiRoutes(page)
    await page.addInitScript(() => {
      Object.assign(window, { __TAURI__: { core: { invoke: async () => false } } })
    })
    const rows = [101, 102].map((id) => ({
      id, novel_id: 1, chapter_number: 3, content: `候选原文 ${id}`, edited_content: null as string | null,
      content_hash: hash(`候选原文 ${id}`), rating: null, created_at: '2026-01-01T00:00:00Z',
    }))
    let saves = 0
    await page.route('**/api/novels/1/continuations?*', (route) => {
      const ids = new URL(route.request().url()).searchParams.get('ids')!.split(',').map(Number)
      return route.fulfill({ json: ids.map((id) => rows.find((row) => row.id === id)) })
    })
    await page.route(/\/api\/novels\/1\/continuations\/\d+$/, (route) => {
      const row = rows.find((item) => route.request().url().endsWith(`/${item.id}`))!
      const body = route.request().postDataJSON() as { content: string; expected_content_hash: string }
      expect(body.expected_content_hash).toBe(row.content_hash)
      row.edited_content = body.content
      row.content_hash = hash(body.content)
      saves += 1
      return route.fulfill({ json: row })
    })
    await page.goto('/novel/1?stage=results&chapter=2&continuations=0:101,1:102&total_variants=2')
    await page.getByRole('button', { name: '编辑修改稿', exact: true }).click()
    await page.getByTestId('candidate-draft-editor').fill('跨页面后必须保留的手稿。')
    await page.getByRole('button', { name: '版本 2', exact: true }).click()
    await page.getByRole('link', { name: '作品库', exact: true }).click()
    await expect(page).toHaveURL(/\/library$/)
    await expect(page.getByTestId('candidate-draft-editor')).toHaveCount(0)
    expect(saves).toBe(0)
    if (finish === 'desktop-exit') {
      await page.evaluate(() => window.dispatchEvent(new CustomEvent('novwr:prepare-exit', { detail: { requestId: 1 } })))
      await expect.poll(() => saves).toBe(1)
    } else {
      await page.goBack()
      await page.getByRole('button', { name: '版本 1', exact: true }).click()
      await page.getByRole('button', { name: '编辑修改稿', exact: true }).click()
      await expect(page.getByTestId('candidate-draft-editor')).toHaveValue('跨页面后必须保留的手稿。')
      await page.getByRole('button', { name: '保存修改稿', exact: true }).click()
      await expect.poll(() => saves).toBe(1)
    }
    expect(rows[0].edited_content).toBe('跨页面后必须保留的手稿。')
    expect(rows[0].content).toBe('候选原文 101')
    expect(errors).toEqual([])
    await page.screenshot({ path: testInfo.outputPath('candidate-draft.png'), fullPage: true })
  })
}

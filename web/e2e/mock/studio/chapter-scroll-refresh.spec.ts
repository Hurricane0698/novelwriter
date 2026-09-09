import { expect, test } from '@playwright/test'
import { mockAllApiRoutes } from '../../fixtures/api-helpers'
import { CHAPTERS, NOVELS } from '../../fixtures/data'

test('a long chapter list preserves the visible row through background metadata refreshes', async ({ page }) => {
  await mockAllApiRoutes(page)
  await page.addInitScript(() => {
    localStorage.setItem('novwr_world_onboarding_dismissed_1_2026-01-01T00:00:00Z', '1')
  })
  let chapters = Array.from({ length: 1000 }, (_, index) => ({ ...CHAPTERS[0], id: index + 1, chapter_number: index + 1, title: `Chapter ${index + 1}` }))
  let reads = 0
  await page.route('**/api/novels/1', route => route.fulfill({ json: { ...NOVELS[0], total_chapters: chapters.length } }))
  await page.route('**/api/novels/1/chapters/meta', route => {
    reads += 1
    return route.fulfill({ json: chapters })
  })
  await page.route(/\/api\/novels\/1\/chapters\/\d+$/, route => {
    const number = Number(route.request().url().split('/').pop())
    return route.fulfill({ json: chapters.find(chapter => chapter.chapter_number === number) })
  })
  await page.goto('/novel/1?chapter=100')
  const viewport = page.getByTestId('studio-chapter-viewport')
  await expect(viewport).toBeVisible()
  await viewport.evaluate(element => { element.scrollTop = 799 * 42 + 17 })
  await expect.poll(() => viewport.evaluate(element => element.scrollTop)).toBe(799 * 42 + 17)

  async function refresh() {
    const before = reads
    // TanStack Query's real window-focus listener refetches stale metadata.
    await page.evaluate(() => {
      window.dispatchEvent(new Event('visibilitychange'))
    })
    await expect.poll(() => reads).toBeGreaterThan(before)
  }

  chapters = chapters.map(chapter => chapter.chapter_number === 100 ? { ...chapter, title: 'Renamed' } : chapter)
  await refresh()
  await expect(viewport.getByRole('button', { name: /Renamed/ })).toHaveCount(1)
  await expect.poll(() => viewport.evaluate(element => element.scrollTop)).toBe(799 * 42 + 17)
  chapters = [...chapters, { ...CHAPTERS[0], id: 1001, chapter_number: 1001, title: 'Chapter 1001' }]
  await refresh()
  await expect(viewport.getByRole('listitem').first()).toHaveAttribute('aria-setsize', '1001')
  await expect.poll(() => viewport.evaluate(element => element.scrollTop)).toBe(799 * 42 + 17)
  chapters = chapters.filter(chapter => chapter.chapter_number !== 20)
  await refresh()
  await expect(viewport.getByRole('listitem').first()).toHaveAttribute('aria-setsize', '1000')
  await expect.poll(() => viewport.evaluate(element => element.scrollTop)).toBe(798 * 42 + 17)
  expect(await viewport.getByRole('button').count()).toBeLessThan(60)
  await page.getByPlaceholder('搜索章节...').fill('900')
  const target = page.getByTestId('studio-rail-chapters').getByRole('button', { name: '第 900 章', exact: true })
  await target.click()
  await expect(page).toHaveURL(/chapter=900/)
  await page.getByPlaceholder('搜索章节...').fill('')
  await expect.poll(() => viewport.evaluate(element => element.scrollTop)).toBeGreaterThan(37000)
})

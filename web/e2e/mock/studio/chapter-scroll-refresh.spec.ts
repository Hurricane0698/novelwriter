import { expect, test } from '@playwright/test'
import { mockAllApiRoutes } from '../../fixtures/api-helpers'
import { CHAPTERS, NOVELS } from '../../fixtures/data'

test('a long chapter list preserves the visible row through background metadata refreshes', async ({ page }) => {
  await mockAllApiRoutes(page)
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
  const firstVisible = () => viewport.evaluate(element => {
    const top = element.getBoundingClientRect().top
    return [...element.querySelectorAll('[role="listitem"]')].find(row => row.getBoundingClientRect().bottom > top)?.textContent
  })
  await viewport.evaluate(element => { element.scrollTop = element.scrollHeight * 0.8 })
  await expect.poll(firstVisible).toMatch(/第 (79\d|80\d) 章/)
  const anchor = await firstVisible()

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
  await expect.poll(firstVisible).toBe(anchor)
  chapters = [...chapters, { ...CHAPTERS[0], id: 1001, chapter_number: 1001, title: 'Chapter 1001' }]
  await refresh()
  await expect(viewport.getByRole('listitem').first()).toHaveAttribute('aria-setsize', '1001')
  await expect.poll(firstVisible).toBe(anchor)
  chapters = chapters.filter(chapter => chapter.chapter_number !== 20)
  await refresh()
  await expect(viewport.getByRole('listitem').first()).toHaveAttribute('aria-setsize', '1000')
  await expect.poll(firstVisible).toBe(anchor)
  await page.getByPlaceholder('搜索章节...').fill('900')
  const target = page.getByTestId('studio-rail-chapters').getByRole('button', { name: '第 900 章', exact: true })
  await target.click()
  await expect(page).toHaveURL(/chapter=900/)
  await page.getByPlaceholder('搜索章节...').fill('')
  await expect(viewport.getByRole('button', { name: /第 900 章/ })).toBeInViewport()
})

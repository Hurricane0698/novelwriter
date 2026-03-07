import { test, expect } from '@playwright/test'
import { ensureLoggedIn, mockAllApiRoutes, mockAuthRoutes, submitLoginForm } from '../fixtures/api-helpers'
import { NOVELS, CHAPTERS } from '../fixtures/data'


test.describe('Login', () => {
  test('login form renders and navigates to library on success', async ({ page }) => {
    await mockAllApiRoutes(page)
    await mockAuthRoutes(page, { authenticated: false })

    await ensureLoggedIn(page, {
      inviteCode: 'MOCK-INVITE',
      nickname: 'test',
      username: 'test',
      password: 'testpass123!',
    })

    await expect(page).toHaveURL('/library')
    await expect(page.getByText('我的作品库')).toBeVisible()
  })

  test('returns to the protected page after login', async ({ page }) => {
    await mockAllApiRoutes(page)
    await mockAuthRoutes(page, { authenticated: false })
    await page.addInitScript(() => {
      localStorage.setItem('novwr_world_onboarding_dismissed_1_2026-01-01T00:00:00Z', '1')
    })

    await page.goto('/novel/1')
    await expect(page).toHaveURL(/\/login$/)

    await submitLoginForm(page, {
      inviteCode: 'MOCK-INVITE',
      nickname: 'redirect-user',
      username: 'redirect-user',
      password: 'testpass123!',
    })

    await expect(page).toHaveURL('/novel/1')
    await expect(page.getByText(NOVELS[0].title)).toBeVisible()
  })
})

test.describe('Library', () => {
  test('shows novels list', async ({ page }) => {
    await mockAllApiRoutes(page)
    await page.goto('/library')

    await expect(page.getByText('我的作品库')).toBeVisible()
    await expect(page.getByText(NOVELS[0].title)).toBeVisible()
    await expect(page.getByText(NOVELS[1].title)).toBeVisible()
  })

  test('shows empty state when no novels', async ({ page }) => {
    await page.route('**/api/**', route => route.abort('blockedbyclient'))
    await mockAuthRoutes(page)
    await page.route('**/api/novels', route => route.fulfill({ json: [] }))
    await page.goto('/library')

    await expect(page.getByText('我的作品库')).toBeVisible()
    await expect(page.getByText('还没有作品，开始创作你的第一部小说吧')).toBeVisible()
  })

  test('shows error state on API failure', async ({ page }) => {
    await page.route('**/api/**', route => route.abort('blockedbyclient'))
    await mockAuthRoutes(page)
    await page.route('**/api/novels', route =>
      route.fulfill({ status: 500, body: 'Internal Server Error' })
    )
    await page.goto('/library')
    // React Query retries by default; allow time for the error state to surface.
    await expect(page.getByText(/加载失败/)).toBeVisible({ timeout: 15_000 })
  })

  test('delete novel removes it from the list (mocked)', async ({ page }) => {
    // Stateful mock: delete affects subsequent GET /api/novels.
    const novels = [...NOVELS]

    await page.route('**/api/**', route => route.abort('blockedbyclient'))
    await mockAuthRoutes(page)

    await page.route('**/api/novels', route => {
      if (route.request().method() !== 'GET') return route.abort('blockedbyclient')
      return route.fulfill({ json: novels })
    })

    await page.route('**/api/novels/1', route => {
      if (route.request().method() === 'GET') return route.fulfill({ json: NOVELS[0] })
      if (route.request().method() === 'DELETE') {
        const idx = novels.findIndex((n) => n.id === 1)
        if (idx >= 0) novels.splice(idx, 1)
        return route.fulfill({ status: 204 })
      }
      return route.abort('blockedbyclient')
    })

    await page.goto('/library')
    await expect(page.getByText(NOVELS[0].title)).toBeVisible()

    page.once('dialog', (d) => d.accept())
    await page.getByRole('link', { name: new RegExp(NOVELS[0].title) }).getByRole('button', { name: '删除' }).click()

    await expect(page.getByText(NOVELS[0].title)).not.toBeVisible()
  })
})

test.describe('Novel detail', () => {
  test('loads novel and chapters (after dismissing onboarding)', async ({ page }) => {
    await mockAllApiRoutes(page)
    await page.addInitScript(() => {
      localStorage.setItem('novwr_world_onboarding_dismissed_1_2026-01-01T00:00:00Z', '1')
    })
    await page.goto('/novel/1')

    await expect(page.getByText(NOVELS[0].title)).toBeVisible()
    await expect(page.getByRole('button', { name: /第\s*1\s*章/ })).toBeVisible()
    await expect(page.getByText(CHAPTERS[0].content)).toBeVisible()
  })
})

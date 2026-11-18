import { test, expect } from '@playwright/test'
import { blockExternalNoise } from '../fixtures/api-helpers'

test.beforeEach(async ({ page }) => {
  await blockExternalNoise(page)
})

test.describe('Smoke: health check', () => {
  test('home page loads', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('navigation').filter({ hasText: 'NovWr' }).first()).toBeVisible()
  })

  test('library page fetches from real backend', async ({ page }) => {
    await page.goto('/library')
    await expect(
      page.getByRole('heading', { name: '我的作品库' })
    ).toBeVisible()
  })
})

test.describe('Smoke: access flow', () => {
  test('selfhost login route returns to Landing and enters Library directly', async ({ page }) => {

    await page.goto('/login')
    await expect(page).toHaveURL('/')
    await expect(page.getByTestId('home-start-writing')).toBeVisible()
    await expect(page.getByTestId('login-form')).toHaveCount(0)

    await page.getByTestId('home-start-writing').click()
    await expect(page).toHaveURL('/library')
    await expect(page.getByRole('heading', { name: '我的作品库' })).toBeVisible()
  })
})

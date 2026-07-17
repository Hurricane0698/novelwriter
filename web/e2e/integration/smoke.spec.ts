import { test, expect } from '@playwright/test'
import { blockExternalNoise, ensureProductAccess, getDeployMode, readInviteCode, submitLoginForm } from '../fixtures/api-helpers'

/**
 * Integration / smoke tests — real backend required.
 * Run with: npm run test:e2e:integration
 *
 * These tests verify frontend ↔ backend contract:
 * auth, data flow, error codes, transactions.
 */

const deployMode = getDeployMode()
const inviteCode = readInviteCode()

test.beforeEach(async ({ page }) => {
  await blockExternalNoise(page)
})

test.describe('Smoke: health check', () => {
  test('home page loads', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('navigation').filter({ hasText: 'NovWr' }).first()).toBeVisible()
  })

  test('library page fetches from real backend', async ({ page }) => {
    await ensureProductAccess(page, { scope: 'smoke-library' })
    await expect(
      page.getByRole('heading', { name: '我的作品库' })
    ).toBeVisible()
  })
})

test.describe('Smoke: access flow', () => {
  test('selfhost login route returns to Landing and enters Library directly', async ({ page }) => {
    test.skip(deployMode !== 'selfhost', 'Local access contract applies only to selfhost E2E.')

    await page.goto('/login')
    await expect(page).toHaveURL('/')
    await expect(page.getByTestId('home-start-writing')).toBeVisible()
    await expect(page.getByTestId('login-form')).toHaveCount(0)

    await page.getByTestId('home-start-writing').click()
    await expect(page).toHaveURL('/library')
    await expect(page.getByRole('heading', { name: '我的作品库' })).toBeVisible()
  })

  test('hosted login form submits to real backend', async ({ page }) => {
    test.skip(deployMode !== 'hosted', 'Hosted login contract applies only to hosted E2E.')
    test.skip(!inviteCode, 'Hosted login requires HOSTED_INVITE_CODES or E2E_INVITE_CODE.')

    await page.goto('/login')
    await expect(page.getByTestId('login-form')).toBeVisible()

    await submitLoginForm(page, { scope: 'smoke-login' })

    await expect(page).toHaveURL('/library')
    await expect(page.getByRole('heading', { name: '我的作品库' })).toBeVisible()
  })
})

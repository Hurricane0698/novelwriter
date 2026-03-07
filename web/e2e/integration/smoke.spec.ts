import { test, expect } from '@playwright/test'
import { blockExternalNoise, ensureLoggedIn, getDeployMode, readInviteCode, submitLoginForm } from '../fixtures/api-helpers'

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
    await ensureLoggedIn(page, { scope: 'smoke-library' })
    await page.goto('/library')
    await expect(
      page.getByRole('heading', { name: '我的作品库' })
    ).toBeVisible()
  })
})

test.describe('Smoke: login flow', () => {
  test('login form submits to real backend', async ({ page }) => {
    await page.goto('/login')
    await expect(page.getByTestId('login-form')).toBeVisible()

    test.skip(deployMode === 'hosted' && !inviteCode, 'Hosted login requires INVITE_CODE (set env or repo-root .env).')

    await submitLoginForm(page, { scope: 'smoke-login' })

    await expect(page).toHaveURL('/library')
    await expect(page.getByRole('heading', { name: '我的作品库' })).toBeVisible()
  })
})

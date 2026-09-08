import { expect, test } from '@playwright/test'

for (const asset of ['index', 'Home']) {
  test(`a failed ${asset} module shows recovery and reload restores the page`, async ({ page }) => {
    await page.route('**/api/auth/me', (route) => route.fulfill({
      status: 401, contentType: 'application/json', body: '{"detail":"Not authenticated"}',
    }))
    let fail = true
    await page.route(new RegExp(`/assets/${asset}-[^/]+\\.js$`), (route) =>
      fail ? route.abort('failed') : route.continue(),
    )
    await page.goto('/')
    await expect(page.getByText('页面未能加载', { exact: true })).toBeVisible()
    await expect(page.getByRole('link', { name: '重新加载页面' })).toBeVisible()
    await page.screenshot({ path: `test-results/startup-${asset}-recovery.png` })
    fail = false
    await page.getByRole('link', { name: '重新加载页面' }).click()
    await expect(page.getByTestId('home-start-writing')).toBeVisible()
    await expect(page.getByText('页面未能加载', { exact: true })).toHaveCount(0)
  })
}

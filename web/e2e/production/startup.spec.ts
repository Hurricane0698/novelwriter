import { expect, test } from '@playwright/test'

for (const [asset, url] of [['index', '/'], ['Home', '/'], ['Home', '/#chapter-note']]) {
  test(`a failed ${asset} module at ${url} shows recovery and reload restores the page`, async ({ page }, testInfo) => {
    await page.route('**/api/auth/me', (route) => route.fulfill({
      status: 401, contentType: 'application/json', body: '{"detail":"Not authenticated"}',
    }))
    let fail = true
    await page.route(new RegExp(`/assets/${asset}-[^/]+\\.js$`), (route) =>
      fail ? route.abort('failed') : route.continue(),
    )
    await page.goto(url)
    await expect(page.getByText('页面未能加载', { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: '重新加载页面' })).toBeVisible()
    await page.screenshot({ path: testInfo.outputPath('startup-recovery.png') })
    fail = false
    await Promise.all([
      page.waitForEvent('load'),
      page.getByRole('button', { name: '重新加载页面' }).click(),
    ])
    expect(new URL(page.url()).hash).toBe(new URL(url, 'http://localhost').hash)
    await expect(page.getByTestId('home-start-writing')).toBeVisible()
    await expect(page.getByText('页面未能加载', { exact: true })).toHaveCount(0)
  })
}

import { test as base, expect } from '@playwright/test'

// Exercise the installed Tauri WebView itself. A separate Chromium page cannot
// reveal WebView-only navigation, rendering, or runtime compatibility failures.
export const test = base.extend({
  page: async ({ playwright, request }, runTest, testInfo) => {
    const endpoint = process.env.NOVWR_DESKTOP_CDP_URL
    if (!endpoint) throw new Error('NOVWR_DESKTOP_CDP_URL must identify the disposable installed WebView')
    await expect.poll(async () => {
      try {
        return (await request.get(`${endpoint}/json/version`, { timeout: 1000 })).ok()
      } catch {
        return false
      }
    }, { timeout: 30_000, message: 'Desktop WebView debugging endpoint did not become ready' }).toBe(true)
    const browser = await playwright.chromium.connectOverCDP(endpoint)
    try {
      const pages = browser.contexts().flatMap((context) => context.pages())
      const page = pages.find((candidate) => candidate.url().startsWith('http://127.0.0.1:8000')) ?? pages[0]
      if (!page) throw new Error('The installed desktop WebView has no page')
      try {
        await runTest(page)
      } finally {
        if (!page.isClosed()) await page.screenshot({ path: testInfo.outputPath('installed-webview.png') })
      }
    } finally {
      await browser.close()
    }
  },
})

export { expect }

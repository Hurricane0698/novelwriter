import { expect, test, type Page } from '@playwright/test'

test('installed desktop renders its local startup failure instead of a blank page', async ({
  playwright,
}) => {
  const cdpUrl = process.env.NOVWR_DESKTOP_E2E_CDP_URL
  if (!cdpUrl) {
    throw new Error('NOVWR_DESKTOP_E2E_CDP_URL is required')
  }

  // WebView2 rejects `/json/version/` with a trailing slash, while Playwright
  // appends one when given the HTTP origin. Resolve the exact endpoint first
  // and connect with the browser WebSocket URL it returns.
  const versionResponse = await fetch(`${cdpUrl}/json/version`)
  if (!versionResponse.ok) {
    throw new Error(`WebView2 CDP version request returned HTTP ${versionResponse.status}`)
  }
  const version = (await versionResponse.json()) as { webSocketDebuggerUrl?: unknown }
  if (typeof version.webSocketDebuggerUrl !== 'string' || !version.webSocketDebuggerUrl) {
    throw new Error('WebView2 CDP version response is missing webSocketDebuggerUrl')
  }

  const browser = await playwright.chromium.connectOverCDP(version.webSocketDebuggerUrl)
  try {
    let shellPage: Page | undefined

    await expect
      .poll(() => {
        shellPage = browser
          .contexts()
          .flatMap((context) => context.pages())
          .find((page) => /^https?:\/\/tauri\.localhost(?:\/|$)/.test(page.url()))
        return shellPage?.url() ?? ''
      })
      .toMatch(/^https?:\/\/tauri\.localhost(?:\/|$)/)

    if (!shellPage) {
      throw new Error('The installed desktop did not expose its bundled failure shell')
    }

    await expect(shellPage.getByRole('heading', { name: '启动失败' })).toBeVisible()
    await expect(shellPage.getByText('本地端口 8000 已被占用。')).toBeVisible()
    await expect(shellPage.getByRole('button', { name: '打开日志' })).toBeVisible()
    await expect(shellPage.getByRole('button', { name: '退出' })).toBeVisible()
  } finally {
    await browser.close()
  }
})

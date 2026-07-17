import { expect, test } from '@playwright/test'
import { waitForInitialNovelReady } from '../fixtures/novel-ready'
import {
  INSTALLED_NOVEL_TITLE,
  assertDesktopLanding,
  assertDesktopLoginRouteRemoved,
  assertSeededDemoVisible,
  assertUploadedNovelVisible,
  enterLibraryThroughDesktopLanding,
  installInstalledProductFailureGuard,
  saveDesktopLlmConfig,
  testDesktopLlmConnection,
  writeInstalledProductState,
} from './support'

test('first installed launch imports a novel and verifies encrypted LLM config', async ({ page }) => {
  const failureGuard = installInstalledProductFailureGuard(page)

  await assertDesktopLanding(page)
  await assertDesktopLoginRouteRemoved(page)
  await enterLibraryThroughDesktopLanding(page)
  await assertSeededDemoVisible(page)

  const fileChooserPromise = page.waitForEvent('filechooser')
  await page.getByTestId('library-create-novel').click()
  const fileChooser = await fileChooserPromise
  await fileChooser.setFiles({
    name: `${INSTALLED_NOVEL_TITLE}.txt`,
    mimeType: 'text/plain',
    buffer: Buffer.from('第一章\n这是 Windows 安装版持久化验证正文。\n', 'utf8'),
  })

  await expect(page).toHaveURL(/\/novel\/\d+$/, { timeout: 60_000 })
  const match = new URL(page.url()).pathname.match(/^\/novel\/(\d+)$/)
  expect(match).not.toBeNull()
  const novelId = Number(match?.[1])
  expect(Number.isInteger(novelId) && novelId > 0).toBe(true)

  await waitForInitialNovelReady(page, novelId)
  await expect(
    page.getByTestId('studio-rail-chapters').getByRole('button', { name: /第\s*1\s*章/ }),
  ).toBeVisible({ timeout: 30_000 })

  const state = { novelId, title: INSTALLED_NOVEL_TITLE }
  await page.goto('/library')
  await assertSeededDemoVisible(page)
  await assertUploadedNovelVisible(page, state)
  await saveDesktopLlmConfig(page)
  await testDesktopLlmConnection(page)
  await writeInstalledProductState(state)
  failureGuard.assertClean()
})

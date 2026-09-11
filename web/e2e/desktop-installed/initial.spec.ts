import { expect, test } from './fixtures'
import { waitForInitialNovelReady } from '../fixtures/novel-ready'
import {
  INSTALLED_NOVEL_TITLE,
  INSTALLED_EDITED_CHAPTER_CONTENT,
  INSTALLED_ORIGIN,
  INSTALLED_STORM_TIMEOUT_MS,
  assertDesktopProductEntry,
  assertDesktopLoginRouteRemoved,
  assertSeededDemoVisible,
  assertUploadedNovelVisible,
  installInstalledProductFailureGuard,
  saveDesktopLlmConfig,
  testDesktopLlmConnection,
  writeInstalledPageDiagnostics,
  writeInstalledProductState,
} from './support'

test.afterEach(async ({ page }, testInfo) => {
  if (testInfo.status === testInfo.expectedStatus) return
  await writeInstalledPageDiagnostics(page, `initial test ${testInfo.status}`)
})

test('first installed launch imports a novel and verifies encrypted LLM config', async ({ page }) => {
  const failureGuard = installInstalledProductFailureGuard(page)

  await assertDesktopProductEntry(page)
  await assertDesktopLoginRouteRemoved(page)
  await assertSeededDemoVisible(page)

  await page.getByTestId('library-file-input').setInputFiles({
    name: `${INSTALLED_NOVEL_TITLE}.txt`,
    mimeType: 'text/plain',
    buffer: Buffer.from('第一章\n这是 Windows 安装版持久化验证正文。\n', 'utf8'),
  })

  await expect(page).toHaveURL(/\/novel\/\d+$/, { timeout: INSTALLED_STORM_TIMEOUT_MS })
  const match = new URL(page.url()).pathname.match(/^\/novel\/(\d+)$/)
  expect(match).not.toBeNull()
  const novelId = Number(match?.[1])
  expect(Number.isInteger(novelId) && novelId > 0).toBe(true)

  await waitForInitialNovelReady(page, novelId, { readyTimeoutMs: INSTALLED_STORM_TIMEOUT_MS })
  await expect(
    page.getByTestId('studio-rail-chapters').getByRole('button', { name: /第\s*1\s*章/ }),
  ).toBeVisible({ timeout: INSTALLED_STORM_TIMEOUT_MS })

  await page.getByRole('button', { name: '编辑', exact: true }).click()
  await page.getByTestId('chapter-editor-textarea').fill(INSTALLED_EDITED_CHAPTER_CONTENT)
  const saved = page.waitForResponse(response => (
    response.request().method() === 'PUT'
    && new URL(response.url()).pathname === `/api/novels/${novelId}/chapters/1`
  ))
  await page.getByRole('button', { name: '保存', exact: true }).click()
  expect((await saved).ok()).toBe(true)
  await expect(page.getByTestId('chapter-editor-textarea')).toHaveCount(0)
  await expect(page.getByText(INSTALLED_EDITED_CHAPTER_CONTENT, { exact: true })).toBeVisible()

  const state = { novelId, title: INSTALLED_NOVEL_TITLE }
  await page.goto(`${INSTALLED_ORIGIN}/library`)
  await assertSeededDemoVisible(page)
  await assertUploadedNovelVisible(page, state)
  await saveDesktopLlmConfig(page)
  await testDesktopLlmConnection(page)
  await writeInstalledProductState(state)
  failureGuard.assertClean()
})

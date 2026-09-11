import { expect, test } from './fixtures'
import { waitForInitialNovelReady } from '../fixtures/novel-ready'
import {
  INSTALLED_EDITED_CHAPTER_CONTENT,
  INSTALLED_ORIGIN,
  assertDesktopProductEntry,
  assertDesktopLlmConfigRestored,
  assertSeededDemoVisible,
  assertUploadedNovelVisible,
  installInstalledProductFailureGuard,
  readInstalledProductState,
  testDesktopLlmConnection,
  writeInstalledPageDiagnostics,
} from './support'

test.afterEach(async ({ page }, testInfo) => {
  if (testInfo.status === testInfo.expectedStatus) return
  await writeInstalledPageDiagnostics(page, `restart test ${testInfo.status}`)
})

test('overwrite install preserves and reuses encrypted LLM config', async ({ page }) => {
  const failureGuard = installInstalledProductFailureGuard(page)
  const state = await readInstalledProductState()

  await assertDesktopProductEntry(page)
  await assertSeededDemoVisible(page)
  await assertUploadedNovelVisible(page, state)
  await assertDesktopLlmConfigRestored(page)
  await testDesktopLlmConnection(page)
  await page.goto(`${INSTALLED_ORIGIN}/novel/${state.novelId}`)
  await waitForInitialNovelReady(page, state.novelId, { dismissOnboarding: true })
  await expect(page.getByText(INSTALLED_EDITED_CHAPTER_CONTENT, { exact: true })).toBeVisible()
  failureGuard.assertClean()
})

import { test } from '@playwright/test'
import {
  assertDesktopLanding,
  assertDesktopLlmConfigRestored,
  assertSeededDemoVisible,
  assertUploadedNovelVisible,
  enterLibraryThroughDesktopLanding,
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

  await assertDesktopLanding(page)
  await enterLibraryThroughDesktopLanding(page)
  await assertSeededDemoVisible(page)
  await assertUploadedNovelVisible(page, state)
  await assertDesktopLlmConfigRestored(page)
  await testDesktopLlmConnection(page)
  failureGuard.assertClean()
})

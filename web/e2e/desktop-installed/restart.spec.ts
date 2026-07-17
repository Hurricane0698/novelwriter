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
} from './support'

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

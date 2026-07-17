import { test } from '@playwright/test'
import {
  assertSeededDemoVisible,
  assertUploadedNovelVisible,
  installInstalledProductFailureGuard,
  loginThroughInstalledUi,
  readInstalledProductState,
} from './support'

test('overwrite install preserves the uploaded novel and seeded demo', async ({ page }) => {
  const failureGuard = installInstalledProductFailureGuard(page)
  const state = await readInstalledProductState()

  await loginThroughInstalledUi(page)
  await assertSeededDemoVisible(page)
  await assertUploadedNovelVisible(page, state)
  failureGuard.assertClean()
})

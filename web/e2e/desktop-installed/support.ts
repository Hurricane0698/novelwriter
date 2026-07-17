import { expect, type Page } from '@playwright/test'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { dirname } from 'node:path'

export const INSTALLED_ORIGIN = 'http://127.0.0.1:8000'
export const INSTALLED_NOVEL_TITLE = 'NovWr Desktop Installed Smoke'

const INSTALLED_USERNAME = 'desktop-installed'
const INSTALLED_PASSWORD = 'desktop-installed'

export interface InstalledProductState {
  novelId: number
  title: string
}

function requiredStatePath(): string {
  const statePath = process.env.NOVWR_DESKTOP_E2E_STATE?.trim()
  if (!statePath) {
    throw new Error('NOVWR_DESKTOP_E2E_STATE must point to the shared installed-product JSON state file.')
  }
  return statePath
}

function isInstalledAsset(url: string): boolean {
  const parsed = new URL(url)
  return (
    parsed.origin === INSTALLED_ORIGIN
    && (parsed.pathname === '/assets' || parsed.pathname.startsWith('/assets/'))
  )
}

export function installInstalledProductFailureGuard(page: Page) {
  const failures: string[] = []
  const record = (message: string) => {
    failures.push(message)
    console.error(`[desktop-installed] ${message}`)
  }

  page.on('pageerror', (error) => {
    record(`pageerror: ${error.stack || error.message}`)
  })
  page.on('requestfailed', (request) => {
    if (!isInstalledAsset(request.url())) return
    record(`asset request failed: ${request.url()} (${request.failure()?.errorText ?? 'unknown error'})`)
  })
  page.on('response', (response) => {
    if (!isInstalledAsset(response.url()) || response.ok()) return
    record(`asset response was ${response.status()}: ${response.url()}`)
  })

  return {
    assertClean() {
      expect(failures, failures.join('\n')).toEqual([])
    },
  }
}

export async function loginThroughInstalledUi(page: Page) {
  await page.goto('/login')
  await expect(page.getByTestId('login-form')).toBeVisible()
  await page.getByLabel('用户名').fill(INSTALLED_USERNAME)
  await page.getByLabel('密码').fill(INSTALLED_PASSWORD)
  const loginResponsePromise = page.waitForResponse((response) => (
    response.url() === `${INSTALLED_ORIGIN}/api/auth/login`
    && response.request().method() === 'POST'
  ))
  await page.getByTestId('login-submit').click()
  const loginResponse = await loginResponsePromise
  expect(
    loginResponse.ok(),
    `Installed login returned HTTP ${loginResponse.status()}.`,
  ).toBe(true)
  await expect(page).toHaveURL(`${INSTALLED_ORIGIN}/library`, { timeout: 60_000 })
  await expect(page.getByRole('heading', { name: '我的作品库' })).toBeVisible()
}

export async function assertSeededDemoVisible(page: Page) {
  const demoEntry = page.getByTestId('library-demo-entry')
  await expect(demoEntry).toBeVisible({ timeout: 60_000 })
  await expect(demoEntry).toContainText('西游记')
}

export async function assertUploadedNovelVisible(
  page: Page,
  state: InstalledProductState,
) {
  const novelLink = page.locator(`a[href="/novel/${state.novelId}"]`)
  await expect(novelLink).toHaveCount(1)
  await expect(novelLink).toContainText(state.title)
}

export async function writeInstalledProductState(state: InstalledProductState) {
  const statePath = requiredStatePath()
  await mkdir(dirname(statePath), { recursive: true })
  await writeFile(statePath, `${JSON.stringify(state, null, 2)}\n`, 'utf8')
}

export async function readInstalledProductState(): Promise<InstalledProductState> {
  const statePath = requiredStatePath()
  const parsed: unknown = JSON.parse(await readFile(statePath, 'utf8'))
  if (typeof parsed !== 'object' || parsed === null) {
    throw new Error(`Invalid installed-product state in ${statePath}.`)
  }
  const state = parsed as Record<string, unknown>
  if (
    typeof state.novelId !== 'number'
    || !Number.isInteger(state.novelId)
    || state.novelId <= 0
    || typeof state.title !== 'string'
    || !state.title.trim()
  ) {
    throw new Error(`Invalid installed-product state in ${statePath}.`)
  }
  return {
    novelId: state.novelId,
    title: state.title,
  }
}

import { expect, type Page, type Response } from '@playwright/test'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { dirname } from 'node:path'

export const INSTALLED_ORIGIN = 'http://127.0.0.1:8000'
export const INSTALLED_NOVEL_TITLE = 'NovWr Desktop Installed Smoke'

function requiredEnvironmentValue(name: string): string {
  const value = process.env[name]?.trim()
  if (!value) {
    throw new Error(`${name} must be set for the installed desktop test.`)
  }
  return value
}

export const INSTALLED_LLM_BASE_URL = requiredEnvironmentValue('NOVWR_DESKTOP_E2E_LLM_BASE_URL')
export const INSTALLED_LLM_API_KEY = requiredEnvironmentValue('NOVWR_DESKTOP_E2E_LLM_API_KEY')
export const INSTALLED_LLM_MODEL = requiredEnvironmentValue('NOVWR_DESKTOP_E2E_LLM_MODEL')

export interface InstalledProductState {
  novelId: number
  title: string
}

const MAX_DIAGNOSTIC_HTML_LENGTH = 12_000
const MAX_DIAGNOSTIC_TEXT_LENGTH = 6_000

function truncateDiagnosticValue(value: string, maxLength: number): string {
  if (value.length <= maxLength) return value
  return `${value.slice(0, maxLength)}\n...[truncated ${value.length - maxLength} characters]`
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

  page.on('console', (message) => {
    if (message.type() !== 'error') return
    record(`console error: ${message.text()}`)
  })
  page.on('crash', () => {
    record('page crashed')
  })
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

export async function writeInstalledPageDiagnostics(page: Page, label: string) {
  const diagnostics: Record<string, unknown> = {
    label,
    url: page.url(),
    pageClosed: page.isClosed(),
  }

  if (!page.isClosed()) {
    try {
      const snapshot = await page.evaluate(() => {
        const summarizeElement = (element: Element) => ({
          tag: element.tagName.toLowerCase(),
          text: element.textContent?.replace(/\s+/g, ' ').trim() ?? '',
          href: element instanceof HTMLAnchorElement ? element.href : null,
          testId: element.getAttribute('data-testid'),
        })
        const actionableElements = Array.from(document.querySelectorAll('a, button'))
        const semanticCtas = actionableElements.filter((element) => {
          const text = element.textContent?.replace(/\s+/g, ' ').trim().toLowerCase() ?? ''
          return text.includes('开始写作') || text.includes('start writing')
        })
        const exactCtas = Array.from(
          document.querySelectorAll('[data-testid="home-start-writing"]'),
        )
        const testIds = Array.from(document.querySelectorAll('[data-testid]')).map((element) => {
          const style = window.getComputedStyle(element)
          return {
            ...summarizeElement(element),
            visible: (
              style.display !== 'none'
              && style.visibility !== 'hidden'
              && !element.hasAttribute('hidden')
              && element.getClientRects().length > 0
            ),
          }
        })

        return {
          readyState: document.readyState,
          rootHtml: document.querySelector('#root')?.innerHTML ?? null,
          bodyText: document.body?.innerText ?? '',
          links: Array.from(document.querySelectorAll('a')).map(summarizeElement),
          testIds,
          exactCtaCount: exactCtas.length,
          exactCtas: exactCtas.map(summarizeElement),
          semanticCtaCount: semanticCtas.length,
          semanticCtas: semanticCtas.map(summarizeElement),
        }
      })
      diagnostics.readyState = snapshot.readyState
      diagnostics.rootHtml = snapshot.rootHtml === null
        ? null
        : truncateDiagnosticValue(snapshot.rootHtml, MAX_DIAGNOSTIC_HTML_LENGTH)
      diagnostics.bodyText = truncateDiagnosticValue(
        snapshot.bodyText,
        MAX_DIAGNOSTIC_TEXT_LENGTH,
      )
      diagnostics.links = snapshot.links
      diagnostics.testIds = snapshot.testIds
      diagnostics.exactCtaCount = snapshot.exactCtaCount
      diagnostics.exactCtas = snapshot.exactCtas
      diagnostics.semanticCtaCount = snapshot.semanticCtaCount
      diagnostics.semanticCtas = snapshot.semanticCtas
    } catch (error) {
      diagnostics.snapshotError = error instanceof Error ? error.stack || error.message : String(error)
    }
  }

  console.error(`[desktop-installed] page diagnostics:\n${JSON.stringify(diagnostics, null, 2)}`)
}

async function expectDesktopLandingSurface(page: Page) {
  try {
    await expect(page).toHaveURL(`${INSTALLED_ORIGIN}/`)
    // First launch renders Landing while the runner absorbs WebView2 first-run,
    // Defender scanning of the fresh install, and first-user demo seeding; the
    // route chunk can take 30-70s to arrive, so this gate gets its own budget
    // below the 210s test and 300s outer process deadlines.
    await expect(page.getByTestId('home-start-writing')).toBeVisible({ timeout: 120_000 })
  } catch (error) {
    await writeInstalledPageDiagnostics(page, 'landing surface')
    throw error
  }
}

export async function assertDesktopLanding(page: Page) {
  await page.goto('/')
  await expectDesktopLandingSurface(page)
}

export async function assertDesktopLoginRouteRemoved(page: Page) {
  await page.goto('/login')
  await expectDesktopLandingSurface(page)
}

export async function enterLibraryThroughDesktopLanding(page: Page) {
  const startWritingLink = page.getByTestId('home-start-writing')
  await expect(startWritingLink).toHaveAttribute('href', '/library')
  await page.goto('/library', { waitUntil: 'domcontentloaded' })
  await expect(page).toHaveURL(`${INSTALLED_ORIGIN}/library`, { timeout: 60_000 })
  await expect(page.getByTestId('library-create-novel')).toBeVisible()
}

function isLlmConfigResponse(response: Response, method: string) {
  return response.url() === `${INSTALLED_ORIGIN}/api/llm/config`
    && response.request().method() === method
}

function isLlmTestResponse(response: Response) {
  return response.url() === `${INSTALLED_ORIGIN}/api/llm/test`
    && response.request().method() === 'POST'
}

export async function saveDesktopLlmConfig(page: Page) {
  const loadResponsePromise = page.waitForResponse((response) => isLlmConfigResponse(response, 'GET'))
  await page.goto('/settings')
  const loadResponse = await loadResponsePromise
  expect(loadResponse.ok(), `Desktop LLM config load returned HTTP ${loadResponse.status()}.`).toBe(true)

  const baseUrlInput = page.locator('#llm-base-url')
  const apiKeyInput = page.locator('#llm-api-key')
  const modelInput = page.locator('#llm-model')
  await expect(baseUrlInput).toHaveValue('')
  await expect(apiKeyInput).toHaveValue('')
  await expect(modelInput).toHaveValue('')

  await baseUrlInput.fill(INSTALLED_LLM_BASE_URL)
  await apiKeyInput.fill(INSTALLED_LLM_API_KEY)
  await modelInput.fill(INSTALLED_LLM_MODEL)

  const saveButton = page.getByTestId('llm-config-save')
  await expect(saveButton).toBeEnabled()
  const saveResponsePromise = page.waitForResponse((response) => isLlmConfigResponse(response, 'PUT'))
  await saveButton.click()
  const saveResponse = await saveResponsePromise
  expect(saveResponse.ok(), `Desktop LLM config save returned HTTP ${saveResponse.status()}.`).toBe(true)

  await expect(page.getByTestId('llm-config-result')).toBeVisible()
  await expect(baseUrlInput).toHaveValue(INSTALLED_LLM_BASE_URL)
  await expect(apiKeyInput).toHaveValue('')
  await expect(modelInput).toHaveValue(INSTALLED_LLM_MODEL)
  await expect(page.getByTestId('llm-api-key-configured')).toBeVisible()
}

export async function assertDesktopLlmConfigRestored(page: Page) {
  const loadResponsePromise = page.waitForResponse((response) => isLlmConfigResponse(response, 'GET'))
  await page.goto('/settings')
  const loadResponse = await loadResponsePromise
  expect(loadResponse.ok(), `Desktop LLM config reload returned HTTP ${loadResponse.status()}.`).toBe(true)

  await expect(page.locator('#llm-base-url')).toHaveValue(INSTALLED_LLM_BASE_URL)
  await expect(page.locator('#llm-api-key')).toHaveValue('')
  await expect(page.locator('#llm-model')).toHaveValue(INSTALLED_LLM_MODEL)
  await expect(page.getByTestId('llm-api-key-configured')).toBeVisible()
}

export async function testDesktopLlmConnection(page: Page) {
  const testButton = page.getByTestId('llm-config-test')
  await expect(testButton).toBeEnabled()
  const testResponsePromise = page.waitForResponse(isLlmTestResponse)
  await testButton.click()
  const testResponse = await testResponsePromise
  expect(testResponse.ok(), `Desktop LLM connection test returned HTTP ${testResponse.status()}.`).toBe(true)
  expect(await testResponse.json()).toMatchObject({
    code: 'llm_probe_compatible',
    model: INSTALLED_LLM_MODEL,
    capabilities: {
      basic: true,
      stream: true,
      json_mode: true,
    },
  })
  await expect(page.getByTestId('llm-config-result')).toContainText('连接与应用兼容性检测通过')
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

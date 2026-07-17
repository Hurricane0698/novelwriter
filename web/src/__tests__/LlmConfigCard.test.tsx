import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClientProvider } from '@tanstack/react-query'
import { UiLocaleProvider } from '@/contexts/UiLocaleContext'
import { createTestQueryClient } from '@/__tests__/support/queryClient'
import { LlmConfigCard } from '@/components/settings/LlmConfigCard'
import {
  clearSelfhostLlmConfig,
  getSelfhostLlmConfig,
} from '@/lib/selfhostLlmConfigStore'
import { api, ApiError, type LlmConfigResponse, type LlmProbeResponse } from '@/services/api'

function createDeferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

const EMPTY_CONFIG: LlmConfigResponse = {
  configured: false,
  base_url: '',
  model: '',
  api_key_configured: false,
}

const SAVED_CONFIG: LlmConfigResponse = {
  configured: true,
  base_url: 'https://example.com/v1',
  model: 'desktop-model',
  api_key_configured: true,
}

const COMPATIBLE_PROBE: LlmProbeResponse = {
  code: 'llm_probe_compatible',
  model: 'desktop-model',
  latency_ms: 12,
  capabilities: { basic: true, stream: true, json_mode: true },
}

function renderCard() {
  const queryClient = createTestQueryClient()
  return render(
    <QueryClientProvider client={queryClient}>
      <UiLocaleProvider>
        <LlmConfigCard />
      </UiLocaleProvider>
    </QueryClientProvider>,
  )
}

describe('LlmConfigCard desktop persistence', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllEnvs()
    vi.stubEnv('VITE_DEPLOY_MODE', 'desktop')
    localStorage.clear()
    document.documentElement.lang = 'zh-CN'
    document.documentElement.dataset.uiLocale = 'zh'
    vi.spyOn(api, 'getLlmConfig').mockResolvedValue(EMPTY_CONFIG)
    vi.spyOn(api, 'updateLlmConfig').mockResolvedValue(SAVED_CONFIG)
    vi.spyOn(api, 'clearLlmConfig').mockResolvedValue(undefined)
    vi.spyOn(api, 'testLlmConnection').mockResolvedValue(COMPATIBLE_PROBE)
  })

  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('hydrates redacted config without ever revealing the saved API key', async () => {
    vi.mocked(api.getLlmConfig).mockResolvedValue(SAVED_CONFIG)
    renderCard()

    expect(await screen.findByDisplayValue(SAVED_CONFIG.base_url)).toBeVisible()
    expect(screen.getByDisplayValue(SAVED_CONFIG.model)).toBeVisible()
    expect(screen.getByLabelText('API Key')).toHaveValue('')
    expect(screen.getByTestId('llm-api-key-configured')).toBeVisible()
    expect(screen.getByTestId('llm-config-save')).toBeDisabled()
    expect(screen.getByTestId('llm-config-test')).toBeEnabled()
  })

  it('persists a complete first-time config and clears the key edit buffer', async () => {
    const user = userEvent.setup()
    const canonicalSavedConfig = {
      ...SAVED_CONFIG,
      base_url: 'https://canonical.example/v1',
      model: 'desktop-model-normalized',
    }
    vi.mocked(api.updateLlmConfig).mockResolvedValue(canonicalSavedConfig)
    renderCard()

    await waitFor(() => expect(screen.getByLabelText('API Base URL')).toBeEnabled())
    await user.type(screen.getByLabelText('API Base URL'), SAVED_CONFIG.base_url)
    await user.type(screen.getByLabelText('API Key'), 'desktop-secret')
    await user.type(screen.getByLabelText('Model Name'), SAVED_CONFIG.model)
    await user.click(screen.getByTestId('llm-config-save'))

    await waitFor(() => {
      expect(vi.mocked(api.updateLlmConfig).mock.calls[0]?.[0]).toEqual({
        base_url: SAVED_CONFIG.base_url,
        model: SAVED_CONFIG.model,
        api_key: 'desktop-secret',
      })
    })
    expect(screen.getByLabelText('API Base URL')).toHaveValue(canonicalSavedConfig.base_url)
    expect(screen.getByLabelText('Model Name')).toHaveValue(canonicalSavedConfig.model)
    expect(screen.getByLabelText('API Key')).toHaveValue('')
    expect(screen.getByTestId('llm-api-key-configured')).toBeVisible()
    expect(screen.getByTestId('llm-config-result')).toHaveTextContent('AI 模型配置已保存')
    expect(screen.getByTestId('llm-config-test')).toBeEnabled()
    await user.click(screen.getByTestId('llm-config-test'))
    await waitFor(() => expect(api.testLlmConnection).toHaveBeenCalledTimes(1))
  })

  it('passes raw desktop input to the backend validation boundary', async () => {
    const user = userEvent.setup()
    vi.mocked(api.updateLlmConfig).mockRejectedValue(
      new ApiError(400, 'HTTP 400', { code: 'llm_api_key_invalid' }),
    )
    renderCard()

    await waitFor(() => expect(screen.getByLabelText('API Base URL')).toBeEnabled())
    await user.type(screen.getByLabelText('API Base URL'), ' https://example.com/v1 ')
    await user.type(screen.getByLabelText('API Key'), ' desktop-secret ')
    await user.type(screen.getByLabelText('Model Name'), ' desktop-model ')
    await user.click(screen.getByTestId('llm-config-save'))

    await waitFor(() => {
      expect(vi.mocked(api.updateLlmConfig).mock.calls[0]?.[0]).toEqual({
        base_url: ' https://example.com/v1 ',
        api_key: ' desktop-secret ',
        model: ' desktop-model ',
      })
    })
    expect(screen.getByTestId('llm-config-result')).toHaveTextContent('API Key 格式无效')
  })

  it('retains the saved key when updating other fields with an empty key input', async () => {
    const user = userEvent.setup()
    vi.mocked(api.getLlmConfig).mockResolvedValue(SAVED_CONFIG)
    vi.mocked(api.updateLlmConfig).mockResolvedValue({
      ...SAVED_CONFIG,
      base_url: 'https://new.example/v1',
    })
    renderCard()

    const baseUrlInput = await screen.findByDisplayValue(SAVED_CONFIG.base_url)
    await user.clear(baseUrlInput)
    await user.type(baseUrlInput, 'https://new.example/v1')
    expect(screen.getByTestId('llm-config-test')).toBeDisabled()
    await user.click(screen.getByTestId('llm-config-save'))

    await waitFor(() => {
      expect(vi.mocked(api.updateLlmConfig).mock.calls[0]?.[0]).toEqual({
        base_url: 'https://new.example/v1',
        model: SAVED_CONFIG.model,
      })
    })
  })

  it('tests only saved config and requires confirmation before deleting it', async () => {
    const user = userEvent.setup()
    vi.mocked(api.getLlmConfig).mockResolvedValue(SAVED_CONFIG)
    renderCard()

    await waitFor(() => expect(screen.getByTestId('llm-config-test')).toBeEnabled())
    await user.click(screen.getByTestId('llm-config-test'))
    await waitFor(() => expect(api.testLlmConnection).toHaveBeenCalledTimes(1))
    expect(await screen.findByTestId('llm-config-result')).toHaveTextContent('连接与应用兼容性检测通过')

    await user.click(screen.getByTestId('llm-config-clear'))
    expect(screen.getByTestId('confirm-dialog')).toBeVisible()
    expect(api.clearLlmConfig).not.toHaveBeenCalled()

    await user.click(screen.getByTestId('confirm-cancel'))
    expect(screen.queryByTestId('confirm-dialog')).toBeNull()
    expect(api.clearLlmConfig).not.toHaveBeenCalled()
    expect(screen.getByLabelText('API Base URL')).toHaveValue(SAVED_CONFIG.base_url)

    await user.click(screen.getByTestId('llm-config-clear'))
    await user.click(screen.getByTestId('confirm-ok'))
    await waitFor(() => expect(api.clearLlmConfig).toHaveBeenCalledTimes(1))
    expect(screen.getByLabelText('API Base URL')).toHaveValue('')
    expect(screen.getByLabelText('API Key')).toHaveValue('')
    expect(screen.getByLabelText('Model Name')).toHaveValue('')
    expect(screen.queryByTestId('llm-api-key-configured')).toBeNull()
    expect(screen.getByTestId('llm-config-result')).toHaveTextContent('AI 模型配置已清空')
  })

  it('localizes stable probe capability results instead of rendering backend text', async () => {
    const user = userEvent.setup()
    localStorage.setItem('novwr_ui_locale', 'en')
    vi.mocked(api.getLlmConfig).mockResolvedValue(SAVED_CONFIG)
    vi.mocked(api.testLlmConnection).mockResolvedValue({
      code: 'llm_probe_capability_mismatch',
      model: SAVED_CONFIG.model,
      latency_ms: 17,
      capabilities: { basic: true, stream: true, json_mode: false },
    })
    renderCard()

    await waitFor(() => expect(screen.getByTestId('llm-config-test')).toBeEnabled())
    await user.click(screen.getByTestId('llm-config-test'))

    expect(await screen.findByTestId('llm-config-result')).toHaveTextContent(
      'does not support JSON mode',
    )
    expect(screen.getByTestId('llm-config-result')).not.toHaveTextContent('JSON 模式')
  })

  it('locks every field and action while saving', async () => {
    const user = userEvent.setup()
    const deferred = createDeferred<LlmConfigResponse>()
    vi.mocked(api.updateLlmConfig).mockReturnValue(deferred.promise)
    renderCard()

    await waitFor(() => expect(screen.getByLabelText('API Base URL')).toBeEnabled())
    await user.type(screen.getByLabelText('API Base URL'), SAVED_CONFIG.base_url)
    await user.type(screen.getByLabelText('API Key'), 'desktop-secret')
    await user.type(screen.getByLabelText('Model Name'), SAVED_CONFIG.model)
    await user.click(screen.getByTestId('llm-config-save'))
    await waitFor(() => expect(api.updateLlmConfig).toHaveBeenCalledTimes(1))

    expect(screen.getByLabelText('API Base URL')).toBeDisabled()
    expect(screen.getByLabelText('API Key')).toBeDisabled()
    expect(screen.getByLabelText('Model Name')).toBeDisabled()
    expect(screen.getByTestId('llm-config-save')).toBeDisabled()
    expect(screen.getByTestId('llm-config-test')).toBeDisabled()
    expect(screen.getByTestId('llm-config-clear')).toBeDisabled()

    deferred.resolve(SAVED_CONFIG)
    await waitFor(() => expect(screen.getByTestId('llm-config-test')).toBeEnabled())
  })

  it('locks every field and action while testing the saved config', async () => {
    const user = userEvent.setup()
    const deferred = createDeferred<LlmProbeResponse>()
    vi.mocked(api.getLlmConfig).mockResolvedValue(SAVED_CONFIG)
    vi.mocked(api.testLlmConnection).mockReturnValue(deferred.promise)
    renderCard()

    await waitFor(() => expect(screen.getByTestId('llm-config-test')).toBeEnabled())
    await user.click(screen.getByTestId('llm-config-test'))
    await waitFor(() => expect(api.testLlmConnection).toHaveBeenCalledTimes(1))

    expect(screen.getByLabelText('API Base URL')).toBeDisabled()
    expect(screen.getByLabelText('API Key')).toBeDisabled()
    expect(screen.getByLabelText('Model Name')).toBeDisabled()
    expect(screen.getByTestId('llm-config-save')).toBeDisabled()
    expect(screen.getByTestId('llm-config-test')).toBeDisabled()
    expect(screen.getByTestId('llm-config-clear')).toBeDisabled()

    deferred.resolve(COMPATIBLE_PROBE)
    await waitFor(() => expect(screen.getByTestId('llm-config-test')).toBeEnabled())
  })

  it('locks every field and action while clearing the saved config', async () => {
    const user = userEvent.setup()
    const deferred = createDeferred<void>()
    vi.mocked(api.getLlmConfig).mockResolvedValue(SAVED_CONFIG)
    vi.mocked(api.clearLlmConfig).mockReturnValue(deferred.promise)
    renderCard()

    await waitFor(() => expect(screen.getByTestId('llm-config-clear')).toBeEnabled())
    await user.click(screen.getByTestId('llm-config-clear'))
    await user.click(screen.getByTestId('confirm-ok'))
    await waitFor(() => expect(api.clearLlmConfig).toHaveBeenCalledTimes(1))

    expect(screen.getByLabelText('API Base URL')).toBeDisabled()
    expect(screen.getByLabelText('API Key')).toBeDisabled()
    expect(screen.getByLabelText('Model Name')).toBeDisabled()
    expect(screen.getByTestId('llm-config-save')).toBeDisabled()
    expect(screen.getByTestId('llm-config-test')).toBeDisabled()
    expect(screen.getByTestId('llm-config-clear')).toBeDisabled()

    deferred.resolve()
    await waitFor(() => expect(screen.getByLabelText('API Base URL')).toHaveValue(''))
  })

  it('keeps the form disabled after a load failure and recovers through retry', async () => {
    const user = userEvent.setup()
    const retry = createDeferred<LlmConfigResponse>()
    vi.mocked(api.getLlmConfig)
      .mockRejectedValueOnce(new Error('desktop config unreadable'))
      .mockReturnValueOnce(retry.promise)
    renderCard()

    expect(await screen.findByText('无法读取本机 AI 模型配置')).toBeVisible()
    expect(screen.getByTestId('llm-config-retry')).toBeEnabled()
    expect(screen.getByLabelText('API Base URL')).toBeDisabled()
    expect(screen.getByLabelText('API Key')).toBeDisabled()
    expect(screen.getByLabelText('Model Name')).toBeDisabled()

    await user.click(screen.getByTestId('llm-config-retry'))
    await waitFor(() => expect(api.getLlmConfig).toHaveBeenCalledTimes(2))
    expect(screen.getByTestId('llm-config-retry')).toBeDisabled()
    expect(screen.getByLabelText('API Base URL')).toBeDisabled()

    retry.resolve(SAVED_CONFIG)
    expect(await screen.findByDisplayValue(SAVED_CONFIG.base_url)).toBeEnabled()
    expect(screen.queryByTestId('llm-config-retry')).toBeNull()
  })

  it('does not call the desktop config API in hosted mode', () => {
    vi.stubEnv('VITE_DEPLOY_MODE', 'hosted')
    renderCard()

    expect(screen.getByText('当前 hosted beta 只使用平台托管的 AI 凭证', { exact: false })).toBeVisible()
    expect(api.getLlmConfig).not.toHaveBeenCalled()
    expect(api.updateLlmConfig).not.toHaveBeenCalled()
    expect(api.clearLlmConfig).not.toHaveBeenCalled()
  })
})

describe('LlmConfigCard selfhost transport validation', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllEnvs()
    vi.stubEnv('VITE_DEPLOY_MODE', 'selfhost')
    clearSelfhostLlmConfig()
    localStorage.clear()
    document.documentElement.lang = 'zh-CN'
    document.documentElement.dataset.uiLocale = 'zh'
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    clearSelfhostLlmConfig()
  })

  it.each([
    {
      field: 'base URL',
      baseUrl: ' https://example.com/v1 ',
      apiKey: 'sk-sensitive-value',
      expectedMessage: '完整的 HTTP(S) 地址',
    },
    {
      field: 'API key',
      baseUrl: 'https://example.com/v1',
      apiKey: ' sk-sensitive-value ',
      expectedMessage: 'API Key 格式无效',
    },
  ])('rejects selfhost $field boundary whitespace without sending or rewriting it', async ({
    baseUrl,
    apiKey,
    expectedMessage,
  }) => {
    const user = userEvent.setup()
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    renderCard()

    await user.type(screen.getByLabelText('API Base URL'), baseUrl)
    await user.type(screen.getByLabelText('API Key'), apiKey)
    await user.type(screen.getByLabelText('Model Name'), 'selfhost-model')
    await user.click(screen.getByTestId('llm-config-test'))

    expect(await screen.findByTestId('llm-config-result')).toHaveTextContent(expectedMessage)
    expect(fetchSpy).not.toHaveBeenCalled()
    expect(getSelfhostLlmConfig()).toEqual({
      baseUrl,
      apiKey,
      model: 'selfhost-model',
    })
  })
})

import { afterEach, describe, expect, it, vi } from 'vitest'
import { getLlmApiErrorMessage, getLlmConfigWarning } from '@/lib/llmErrorMessages'
import { ApiError } from '@/services/api'

describe('llmErrorMessages', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('maps missing desktop config to the settings action', () => {
    vi.stubEnv('VITE_DEPLOY_MODE', 'desktop')
    const err = new ApiError(409, 'HTTP 409', {
      code: 'llm_config_missing',
      detail: { code: 'llm_config_missing' },
    })

    expect(getLlmApiErrorMessage(err)).toBe('请先在设置中配置 AI 模型。')
    expect(getLlmApiErrorMessage(err, 'en')).toBe('Configure an AI model in Settings before trying again.')
  })

  it('does not send hosted users to local model settings', () => {
    vi.stubEnv('VITE_DEPLOY_MODE', 'hosted')
    const err = new ApiError(400, 'HTTP 400', {
      code: 'llm_config_missing',
      detail: { code: 'llm_config_missing' },
    })

    expect(getLlmApiErrorMessage(err)).toContain('平台 AI 服务尚未配置')
    expect(getLlmApiErrorMessage(err)).not.toContain('设置中配置')
  })

  it('maps incomplete BYOK config to actionable copy', () => {
    vi.stubEnv('VITE_DEPLOY_MODE', 'selfhost')
    const err = new ApiError(400, 'HTTP 400', {
      code: 'llm_config_incomplete',
      detail: { code: 'llm_config_incomplete' },
    })

    expect(getLlmApiErrorMessage(err)).toContain('BYOK 配置不完整')
  })

  it('maps invalid base URLs without echoing backend diagnostics', () => {
    const err = new ApiError(400, 'HTTP 400', {
      code: 'llm_base_url_invalid',
      detail: {
        code: 'llm_base_url_invalid',
        message: 'do not render this backend diagnostic',
      },
    })

    expect(getLlmApiErrorMessage(err)).toContain('完整的 HTTP(S) 地址')
    expect(getLlmApiErrorMessage(err)).not.toContain('backend diagnostic')
    expect(getLlmApiErrorMessage(err, 'en')).toContain('absolute HTTP(S) address')
  })

  it('maps invalid API keys without echoing backend diagnostics', () => {
    const err = new ApiError(422, 'HTTP 422', {
      code: 'llm_api_key_invalid',
      detail: {
        code: 'llm_api_key_invalid',
        message: 'rejected secret key: sk-sensitive-value',
      },
    })

    expect(getLlmApiErrorMessage(err)).toBe(
      'API Key 格式无效。请重新填写不含空白或控制字符的有效 Key。',
    )
    expect(getLlmApiErrorMessage(err)).not.toContain('sk-sensitive-value')
    expect(getLlmApiErrorMessage(err, 'en')).toBe(
      'API key format is invalid. Enter a valid key without whitespace or control characters.',
    )
  })

  it('maps operator disable to explicit copy', () => {
    const err = new ApiError(503, 'HTTP 503', {
      code: 'ai_manually_disabled',
      detail: { code: 'ai_manually_disabled' },
    })

    expect(getLlmApiErrorMessage(err)).toContain('已关闭 AI 功能')
  })

  it('maps duplicate-click admission errors to actionable copy', () => {
    const continuationErr = new ApiError(409, 'HTTP 409', {
      code: 'continuation_duplicate_request',
      detail: { code: 'continuation_duplicate_request' },
    })
    const bootstrapErr = new ApiError(409, 'HTTP 409', {
      code: 'bootstrap_index_already_fresh',
      detail: { code: 'bootstrap_index_already_fresh' },
    })

    expect(getLlmApiErrorMessage(continuationErr)).toContain('已经在处理中')
    expect(getLlmApiErrorMessage(bootstrapErr)).toContain('已经是最新状态')
  })

  it('warns when the current BYOK config is partial', () => {
    expect(
      getLlmConfigWarning({ baseUrl: 'https://example.com/v1', apiKey: '', model: '' }),
    ).toContain('只填写了部分 BYOK 配置')
    expect(
      getLlmConfigWarning({ baseUrl: 'https://example.com/v1', apiKey: 'k', model: 'm' }),
    ).toBeNull()
  })
})

import { describe, expect, it } from 'vitest'
import { getLlmApiErrorMessage, getLlmConfigWarning } from '@/lib/llmErrorMessages'
import { ApiError } from '@/services/api'

describe('llmErrorMessages', () => {
  it('maps incomplete BYOK config to actionable copy', () => {
    const err = new ApiError(400, 'HTTP 400', {
      code: 'llm_config_incomplete',
      detail: { code: 'llm_config_incomplete' },
    })

    expect(getLlmApiErrorMessage(err)).toContain('BYOK 配置不完整')
  })

  it('maps operator disable to explicit copy', () => {
    const err = new ApiError(503, 'HTTP 503', {
      code: 'ai_manually_disabled',
      detail: { code: 'ai_manually_disabled' },
    })

    expect(getLlmApiErrorMessage(err)).toContain('已关闭 AI 功能')
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

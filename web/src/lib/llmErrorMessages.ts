import type { LlmConfig } from '@/lib/llmConfigStore'
import { ApiError } from '@/services/api'

export function getLlmConfigWarning(config: LlmConfig): string | null {
  const filled = [config.baseUrl, config.apiKey, config.model].filter(Boolean).length
  if (filled === 0 || filled === 3) return null
  return '当前只填写了部分 BYOK 配置。请同时填写 Base URL、API Key 和 Model；否则续写、世界生成和提取都会被拒绝。'
}

export function getLlmApiErrorMessage(err: ApiError): string | null {
  switch (err.code) {
    case 'llm_config_incomplete':
      return '当前 BYOK 配置不完整，请同时填写 Base URL、API Key 和 Model，或清空当前配置。'
    case 'ai_manually_disabled':
      return '当前实例已关闭 AI 功能，暂时无法发起模型请求。'
    case 'ai_budget_hard_stop':
      return '当前实例的托管 AI 额度已达上限，请稍后再试，或改用你自己的 API Key。'
    case 'ai_budget_meter_disabled':
    case 'ai_budget_meter_unavailable':
      return '当前实例暂时关闭了托管 AI 请求，请稍后再试，或改用你自己的 API Key。'
    case 'world_generate_llm_unavailable':
      return '当前模型不可用。请检查 Base URL、API Key、Model 是否匹配，并确认接口支持 JSON 模式。'
    default:
      return null
  }
}

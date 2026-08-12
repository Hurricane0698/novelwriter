import '@/lib/uiMessagePacks/novel'
import { resolveCurrentUiLocale } from '@/lib/uiLocale'
import { getRuntimeMode } from '@/lib/runtimeMode'
import { translateUiMessage, type UiLocale } from '@/lib/uiMessages'
import { ApiError } from '@/services/api'

export interface LlmConfigDraft {
  baseUrl: string
  apiKey: string
  model: string
}

export function getLlmConfigWarning(config: LlmConfigDraft, locale?: UiLocale): string | null {
  const filled = [config.baseUrl, config.apiKey, config.model].filter(Boolean).length
  if (filled === 0 || filled === 3) return null
  return translateUiMessage(locale ?? resolveCurrentUiLocale(), 'llm.warning.partialConfig')
}

export function getLlmApiErrorMessage(err: ApiError, locale?: UiLocale): string | null {
  const effectiveLocale = locale ?? resolveCurrentUiLocale()
  switch (err.code) {
    case 'llm_config_missing':
      return translateUiMessage(
        effectiveLocale,
        getRuntimeMode() === 'hosted'
          ? 'llm.error.missingHostedConfig'
          : 'llm.error.missingLocalConfig',
      )
    case 'llm_config_incomplete':
      return translateUiMessage(
        effectiveLocale,
        getRuntimeMode() === 'hosted'
          ? 'llm.error.incompleteHostedConfig'
          : 'llm.error.incompleteConfig',
      )
    case 'llm_base_url_invalid':
      return translateUiMessage(effectiveLocale, 'llm.error.invalidBaseUrl')
    case 'llm_api_key_invalid':
      return translateUiMessage(effectiveLocale, 'llm.error.invalidApiKey')
    case 'ai_manually_disabled':
      return translateUiMessage(effectiveLocale, 'llm.error.aiDisabled')
    case 'ai_budget_hard_stop':
      return translateUiMessage(effectiveLocale, 'llm.error.budgetHardStop')
    case 'ai_budget_meter_disabled':
    case 'ai_budget_meter_unavailable':
      return translateUiMessage(effectiveLocale, 'llm.error.budgetUnavailable')
    case 'world_generate_llm_unavailable':
    case 'outline_generation_llm_unavailable':
      return translateUiMessage(effectiveLocale, 'llm.error.modelUnavailable')
    case 'continuation_duplicate_request':
    case 'continuation_request_still_running':
      return translateUiMessage(effectiveLocale, 'continuation.results.alreadyRunning')
    case 'outline_not_found':
      return translateUiMessage(effectiveLocale, 'continuation.setup.outline.error.notFound')
    case 'outline_context_too_large':
      return translateUiMessage(effectiveLocale, 'continuation.setup.outline.error.selectedTooLarge')
    case 'world_generate_duplicate_request':
      return translateUiMessage(effectiveLocale, 'worldModel.generate.conflict')
    case 'bootstrap_index_already_fresh':
      return translateUiMessage(effectiveLocale, 'worldModel.bootstrap.alreadyFresh')
    default:
      return null
  }
}

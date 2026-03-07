export interface LlmConfig {
  baseUrl: string
  apiKey: string
  model: string
}

const EMPTY_CONFIG: LlmConfig = {
  baseUrl: '',
  apiKey: '',
  model: '',
}

let currentConfig: LlmConfig = { ...EMPTY_CONFIG }

function normalize(value: Partial<LlmConfig>): LlmConfig {
  return {
    baseUrl: (value.baseUrl ?? '').trim(),
    apiKey: (value.apiKey ?? '').trim(),
    model: (value.model ?? '').trim(),
  }
}

export function getLlmConfig(): LlmConfig {
  return { ...currentConfig }
}

export function setLlmConfig(value: Partial<LlmConfig>): LlmConfig {
  currentConfig = normalize({ ...currentConfig, ...value })
  return getLlmConfig()
}

export function clearLlmConfig(): void {
  currentConfig = { ...EMPTY_CONFIG }
}

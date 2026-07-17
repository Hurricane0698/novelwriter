export interface SelfhostLlmConfig {
  baseUrl: string
  apiKey: string
  model: string
}

const EMPTY_CONFIG: SelfhostLlmConfig = {
  baseUrl: '',
  apiKey: '',
  model: '',
}

let currentConfig: SelfhostLlmConfig = { ...EMPTY_CONFIG }

function copyConfig(value: Partial<SelfhostLlmConfig>): SelfhostLlmConfig {
  return {
    baseUrl: value.baseUrl ?? '',
    apiKey: value.apiKey ?? '',
    model: value.model ?? '',
  }
}

export function getSelfhostLlmConfig(): SelfhostLlmConfig {
  return { ...currentConfig }
}

export function setSelfhostLlmConfig(value: Partial<SelfhostLlmConfig>): SelfhostLlmConfig {
  currentConfig = copyConfig({ ...currentConfig, ...value })
  return getSelfhostLlmConfig()
}

export function clearSelfhostLlmConfig(): void {
  currentConfig = { ...EMPTY_CONFIG }
}

import { beforeEach, describe, expect, it } from 'vitest'
import {
  clearSelfhostLlmConfig,
  getSelfhostLlmConfig,
  setSelfhostLlmConfig,
} from '@/lib/selfhostLlmConfigStore'

describe('selfhostLlmConfigStore', () => {
  beforeEach(() => {
    clearSelfhostLlmConfig()
    localStorage.clear()
  })

  it('preserves raw Docker selfhost BYOK config in memory only', () => {
    setSelfhostLlmConfig({ baseUrl: ' http://example.com/v1 ', apiKey: ' sk-test ', model: ' m ' })

    expect(getSelfhostLlmConfig()).toEqual({
      baseUrl: ' http://example.com/v1 ',
      apiKey: ' sk-test ',
      model: ' m ',
    })
    expect(localStorage.length).toBe(0)
  })

  it('clears config completely', () => {
    setSelfhostLlmConfig({ baseUrl: 'http://example.com/v1', apiKey: 'sk-test', model: 'm' })
    clearSelfhostLlmConfig()

    expect(getSelfhostLlmConfig()).toEqual({ baseUrl: '', apiKey: '', model: '' })
  })
})

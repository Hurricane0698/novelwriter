import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  getRuntimeMode,
  isHostedRuntime,
  isSelfhostRuntime,
} from '@/lib/runtimeMode'

describe('runtimeMode', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('defaults to selfhost', () => {
    vi.stubEnv('VITE_DEPLOY_MODE', '')
    expect(getRuntimeMode()).toBe('selfhost')
    expect(isSelfhostRuntime()).toBe(true)
  })

  it('distinguishes hosted and desktop contracts', () => {
    vi.stubEnv('VITE_DEPLOY_MODE', 'hosted')
    expect(isHostedRuntime()).toBe(true)

    vi.stubEnv('VITE_DEPLOY_MODE', 'desktop')
    expect(getRuntimeMode()).toBe('desktop')
    expect(isHostedRuntime()).toBe(false)
    expect(isSelfhostRuntime()).toBe(false)
  })

  it('fails fast on unsupported modes', () => {
    vi.stubEnv('VITE_DEPLOY_MODE', 'unknown')
    expect(() => getRuntimeMode()).toThrow('Unsupported VITE_DEPLOY_MODE: unknown')
  })
})

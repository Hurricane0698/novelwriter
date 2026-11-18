import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  getRuntimeMode,
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

  it('selects the desktop runtime', () => {

    vi.stubEnv('VITE_DEPLOY_MODE', 'desktop')
    expect(getRuntimeMode()).toBe('desktop')
    expect(isSelfhostRuntime()).toBe(false)
  })

  it('fails fast on unsupported modes', () => {
    vi.stubEnv('VITE_DEPLOY_MODE', 'unknown')
    expect(() => getRuntimeMode()).toThrow('Unsupported VITE_DEPLOY_MODE: unknown')
  })
})

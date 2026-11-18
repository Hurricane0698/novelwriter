import { describe, expect, it, vi } from 'vitest'

describe('route-scoped ui message packs', () => {
  it('does not eagerly register home copy through the root locale provider module', async () => {
    vi.resetModules()

    await import('@/contexts/UiLocaleContext')
    const { translateUiMessage } = await import('@/lib/uiMessages')

    const homeTitleKey = 'home.hero.title' as Parameters<typeof translateUiMessage>[1]

    expect(translateUiMessage('en', homeTitleKey)).toBe('[missing:home.hero.title]')

    await import('@/lib/uiMessagePacks/home')

    expect(translateUiMessage('en', homeTitleKey)).toBe('Understand the world first.\nWrite better stories.')
  })

})

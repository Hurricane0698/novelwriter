import { describe, it, expect } from 'vitest'
import { cn } from '@/lib/utils'

describe('cn', () => {
  it('composes conditional classes with Tailwind conflict resolution', () => {
    expect(cn('px-2', { 'py-1': true, hidden: false }, null, undefined, 'px-4'))
      .toBe('py-1 px-4')
  })
})

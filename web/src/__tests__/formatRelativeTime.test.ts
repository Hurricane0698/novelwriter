// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { formatRelativeTime } from '@/lib/formatRelativeTime'

const NOW = '2026-09-08T02:00:02.123Z'

describe('formatRelativeTime', () => {
  beforeEach(() => {
    vi.stubEnv('TZ', 'Asia/Shanghai')
    vi.spyOn(Date, 'now').mockReturnValue(Date.parse(NOW))
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllEnvs()
  })

  it('shows a fresh UTC-naive API timestamp as just updated in UTC+8', () => {
    // Verify the actual Date parser uses +8 so a UTC-only test host cannot mask the bug.
    expect(new Date(NOW).getTimezoneOffset()).toBe(-480)
    expect(formatRelativeTime('2026-09-08T02:00:00')).toBe('刚刚')
    expect(formatRelativeTime('2026-09-08T02:00:00', 'en')).toBe('just now')
  })

  it.each([
    '2026-09-08T01:55:02.123456',
    '2026-09-08 01:55:02.123456',
  ])('retains elapsed minutes for a fractional naive timestamp: %s', (timestamp) => {
    expect(formatRelativeTime(timestamp)).toBe('5 分钟前')
  })

  it.each([
    '2026-09-08T01:00:02.123Z',
    '2026-09-08T09:00:02.123+08:00',
    '2026-09-07T21:00:02.123-04:00',
  ])('preserves an explicit timezone: %s', (timestamp) => {
    expect(formatRelativeTime(timestamp, 'en')).toBe('1 hour ago')
  })

  it('keeps naive timestamps consistent when the client timezone changes', () => {
    const timestamp = '2026-09-08T00:00:02.123'
    expect(formatRelativeTime(timestamp)).toBe('2 小时前')
    vi.stubEnv('TZ', 'America/New_York')
    expect(new Date(NOW).getTimezoneOffset()).toBe(240)
    expect(formatRelativeTime(timestamp)).toBe('2 小时前')
  })

  it('preserves invalid and future timestamp fallbacks and date-only semantics', () => {
    expect(formatRelativeTime('not-a-date')).toBe('刚刚')
    expect(formatRelativeTime('2026-09-08T03:00:00Z')).toBe('刚刚')
    expect(formatRelativeTime('2026-09-07')).toBe('昨天')
  })
})

import type { Novel } from '@/types/api'

export function isSeededDemoNovel(
  novel: Pick<Novel, 'is_seeded_demo'> | null | undefined,
): boolean {
  return Boolean(novel?.is_seeded_demo)
}

export function findSeededDemoNovel<T extends Pick<Novel, 'is_seeded_demo'>>(
  novels: readonly T[] | null | undefined,
): T | null {
  if (!novels) return null
  return novels.find((novel) => isSeededDemoNovel(novel)) ?? null
}

export function buildDemoStudioPath(
  novelId: number,
  opts?: { forceGuideOpen?: boolean },
): string {
  const searchParams = new URLSearchParams()
  if (opts?.forceGuideOpen) {
    searchParams.set('demoGuide', 'open')
  }
  const search = searchParams.toString()
  return `/novel/${novelId}${search ? `?${search}` : ''}`
}

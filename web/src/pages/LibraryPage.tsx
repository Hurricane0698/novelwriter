// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { EmptyState } from '@/components/library/EmptyState'
import { WorkCard } from '@/components/library/WorkCard'
import { PageShell } from '@/components/layout/PageShell'
import { NwButton } from '@/components/ui/nw-button'
import { GlassCard } from '@/components/GlassCard'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { ApiError, api } from '@/services/api'
import { novelKeys } from '@/hooks/novel/keys'
import { buildDemoStudioPath, findSeededDemoNovel } from '@/lib/demoProject'
import { trackHostedAnalyticsEvent } from '@/lib/hostedAnalytics'
import { buildNovelListQueryOptions } from '@/lib/novelListQuery'
import {
  DEMO_FIRST_ONBOARDING_STEPS,
  clearDemoFirstWritingOnboardingDismissed,
  countVisitedDemoFirstWritingOnboardingSteps,
  getDemoFirstWritingOnboardingState,
} from '@/lib/demoFirstOnboardingStorage'
import { clearWorldOnboardingDismissed } from '@/lib/worldOnboardingStorage'

export function LibraryPage() {
  const { t } = useUiLocale()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const pendingUploadSourceRef = useRef<string | null>(null)
  const [uploadingFileName, setUploadingFileName] = useState<string | null>(null)

  const { data: novels = [], isLoading: loading, error } = useQuery({
    ...buildNovelListQueryOptions(),
  })
  const demoNovel = findSeededDemoNovel(novels)
  const demoGuideState = demoNovel
    ? getDemoFirstWritingOnboardingState(demoNovel.id, demoNovel.created_at)
    : null
  const demoGuideProgressCount = demoGuideState
    ? countVisitedDemoFirstWritingOnboardingSteps(demoGuideState)
    : 0

  const deleteNovel = useMutation({
    mutationFn: (vars: { id: number, created_at?: string | null }) => api.deleteNovel(vars.id),
    onSuccess: (_data, vars) => {
      clearDemoFirstWritingOnboardingDismissed(vars.id, vars.created_at)
      clearWorldOnboardingDismissed(vars.id, vars.created_at)
      queryClient.invalidateQueries({ queryKey: novelKeys.all })
    },
  })

  function handleDelete(id: number) {
    if (!window.confirm(t('library.confirm.delete'))) return
    const novel = novels.find((n) => n.id === id)
    deleteNovel.mutate({ id, created_at: novel?.created_at })
  }

  function handleCreate(sourceSurface: string) {
    if (uploadingFileName) return
    pendingUploadSourceRef.current = sourceSurface
    void trackHostedAnalyticsEvent('upload_cta_click', {
      meta: {
        source_surface: sourceSurface,
      },
    })
    fileInputRef.current?.click()
  }

  async function handleFileSelected(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    const title = file.name.replace(/\.txt$/i, '')
    const sourceSurface = pendingUploadSourceRef.current ?? 'unknown'
    setUploadingFileName(file.name)
    try {
      const result = await api.uploadNovel(file, title, '', { sourceSurface })
      queryClient.invalidateQueries({ queryKey: novelKeys.all })
      navigate(`/novel/${result.novel_id}`, { state: { novwrEntry: 'upload' } })
    } catch (err) {
      if (err instanceof ApiError) {
        const detail = err.detail as { max_megabytes?: number } | undefined
        if (err.code === 'upload_file_too_large') {
          alert(t('library.error.uploadTooLarge', { maxMb: detail?.max_megabytes ?? 30 }))
        } else if (err.code === 'upload_type_not_supported') {
          alert(t('library.error.uploadTypeNotSupported'))
        } else if (err.code === 'upload_parse_failed') {
          alert(t('library.error.uploadParseFailed'))
        } else {
          alert(t('library.error.uploadFailed'))
        }
      } else {
        alert(err instanceof Error ? err.message : t('library.error.uploadFailed'))
      }
      setUploadingFileName(null)
    }
    pendingUploadSourceRef.current = null
    e.target.value = ''
  }

  const createButton = (
    <NwButton
      data-testid="library-create-novel"
      onClick={() => handleCreate('library_header')}
      variant="accent"
      disabled={uploadingFileName !== null}
      className="rounded-full px-6 py-2.5 text-sm font-semibold shadow-[0_0_24px_hsl(var(--accent)/0.35)]"
    >
      <Plus size={18} />
      {t('library.create')}
    </NwButton>
  )

  const openDemoGuide = () => {
    if (!demoNovel) return
    const shouldForceGuideOpen = demoGuideState?.status === 'completed' || demoGuideState?.status === 'skipped'
    navigate(buildDemoStudioPath(demoNovel.id, { forceGuideOpen: shouldForceGuideOpen }))
  }

  const demoDescription = !demoNovel || !demoGuideState
    ? ''
    : demoGuideState.status === 'in_progress'
      ? t('library.demo.description.inProgress', {
        title: demoNovel.title,
        current: demoGuideProgressCount,
        total: DEMO_FIRST_ONBOARDING_STEPS.length,
      })
      : demoGuideState.status === 'completed'
        ? t('library.demo.description.completed', { title: demoNovel.title })
        : demoGuideState.status === 'skipped'
          ? t('library.demo.description.skipped', { title: demoNovel.title })
          : t('library.demo.description', { title: demoNovel.title })
  const demoOpenLabel = !demoGuideState
    ? t('library.demo.open')
    : demoGuideState.status === 'in_progress'
      ? t('library.demo.resume')
      : demoGuideState.status === 'completed'
        ? t('library.demo.reopen')
        : demoGuideState.status === 'skipped'
          ? t('library.demo.reopen')
          : t('library.demo.start')

  return (
    <PageShell className="h-screen" navbarProps={{ position: 'static' }} mainClassName="overflow-hidden">
      <input
        ref={fileInputRef}
        data-testid="library-file-input"
        type="file"
        accept=".txt"
        className="hidden"
        disabled={uploadingFileName !== null}
        onChange={handleFileSelected}
      />
      {uploadingFileName ? (
        <div
          data-testid="library-upload-overlay"
          className="fixed inset-0 z-50 flex items-center justify-center bg-[hsl(var(--background)/0.72)] backdrop-blur-sm"
        >
          <div className="w-full max-w-md rounded-3xl border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] px-6 py-7 text-center shadow-[var(--nw-copilot-panel-shadow)]">
            <div className="mx-auto mb-4 h-10 w-10 animate-spin rounded-full border-2 border-[hsl(var(--accent)/0.18)] border-t-[hsl(var(--accent))]" />
            <div className="space-y-2">
              <h2 className="m-0 text-lg font-semibold text-foreground">
                {t('library.uploadOverlay.title')}
              </h2>
              <p className="m-0 text-sm leading-6 text-muted-foreground">
                {t('library.uploadOverlay.description')}
              </p>
              <p className="m-0 break-all text-xs text-muted-foreground/80">
                {uploadingFileName}
              </p>
            </div>
          </div>
        </div>
      ) : null}
      <div className="flex flex-col flex-1 px-12 py-10 gap-8 overflow-auto">
        {/* Header */}
        <div className="flex items-center justify-between gap-6">
          <div className="flex flex-col gap-1">
            <h1 className="m-0 font-mono text-2xl font-bold text-foreground">
              {t('library.title')}
            </h1>
            <p className="m-0 text-sm text-muted-foreground">
              {t('library.description')}
            </p>
          </div>
          {createButton}
        </div>

        {/* Loading */}
        {loading && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
            {[0, 1, 2, 3].map((i) => (
              <GlassCard
                key={i}
                className="h-40 animate-pulse"
              />
            ))}
          </div>
        )}

        {/* Error */}
        {error && (
          <p className="text-sm text-[hsl(var(--color-warning))]">
            {t('library.error.load')}: {error instanceof Error ? error.message : t('library.error.unknown')}
          </p>
        )}

        {/* Empty */}
        {!loading && !error && novels.length === 0 && (
          <EmptyState onCreate={() => handleCreate('library_empty_state')} />
        )}

        {!loading && !error && demoNovel && (
          <GlassCard
            className="flex flex-col gap-4 rounded-[28px] border border-[hsl(var(--accent)/0.22)] bg-[linear-gradient(135deg,hsl(var(--accent)/0.12),transparent_55%)] p-6"
            data-testid="library-demo-entry"
          >
            <div className="space-y-2">
              <span className="inline-flex items-center rounded-full border border-[hsl(var(--accent)/0.24)] bg-[hsl(var(--accent)/0.12)] px-3 py-1 text-[11px] font-semibold tracking-[0.18em] text-[hsl(var(--accent))] uppercase">
                {t('library.demo.badge')}
              </span>
              <div className="space-y-1">
                <h2 className="m-0 text-xl font-semibold text-foreground">
                  {t('library.demo.title')}
                </h2>
                <p className="m-0 max-w-3xl text-sm leading-6 text-muted-foreground">
                  {demoDescription}
                </p>
              </div>
            </div>

            <div className="flex flex-wrap gap-3">
              <NwButton
                variant="accent"
                className="rounded-full px-5 py-2.5 text-sm font-semibold"
                onClick={openDemoGuide}
              >
                {demoOpenLabel}
              </NwButton>
              <NwButton
                variant="glass"
                className="rounded-full px-5 py-2.5 text-sm font-semibold"
                onClick={() => handleCreate('library_demo_card')}
              >
                {t('library.demo.upload')}
              </NwButton>
            </div>
          </GlassCard>
        )}

        {/* Card Grid */}
        {!loading && !error && novels.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
            {novels.map((novel) => (
              <WorkCard key={novel.id} novel={novel} onDelete={handleDelete} />
            ))}
          </div>
        )}
      </div>
    </PageShell>
  )
}

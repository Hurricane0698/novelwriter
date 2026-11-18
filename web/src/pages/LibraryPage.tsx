// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: MIT

import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Upload } from 'lucide-react'
import { EmptyState } from '@/components/library/EmptyState'
import { WorkCard } from '@/components/library/WorkCard'
import { PageShell } from '@/components/layout/PageShell'
import { NwButton } from '@/components/ui/nw-button'
import { GlassCard } from '@/components/GlassCard'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { useConfirmDialog } from '@/hooks/useConfirmDialog'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { ApiError, api } from '@/services/api'
import { novelKeys } from '@/hooks/novel/keys'
import { buildNovelListQueryOptions } from '@/lib/novelListQuery'

const libraryActionClass = 'h-10 rounded-full px-6 text-sm font-semibold'

export function LibraryPage() {
  const { locale, t } = useUiLocale()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [uploadingFileName, setUploadingFileName] = useState<string | null>(null)
  const { confirm, alert: showAlert, dialogProps } = useConfirmDialog()

  const { data: novels = [], isLoading: loading, error } = useQuery({
    ...buildNovelListQueryOptions(),
  })

  const deleteNovel = useMutation({
    mutationFn: api.deleteNovel,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: novelKeys.all }),
  })
  const createNovel = useMutation({
    mutationFn: () => api.createNovel(t('library.untitled'), locale),
    onSuccess: (novel) => {
      void queryClient.invalidateQueries({ queryKey: novelKeys.all })
      navigate(`/novel/${novel.id}`)
    },
    onError: () => { void showAlert({ title: t('library.error.create') }) },
  })
  const busy = uploadingFileName !== null || createNovel.isPending

  async function handleDelete(id: number) {
    const confirmed = await confirm({
      title: t('library.confirm.delete.title'),
      description: t('library.confirm.delete'),
      confirmText: t('library.workCard.delete'),
      tone: 'destructive',
    })
    if (!confirmed) return
    deleteNovel.mutate(id)
  }

  async function handleFileSelected(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    const title = file.name.replace(/\.(?:txt|md)$/i, '')
    setUploadingFileName(file.name)
    try {
      const result = await api.uploadNovel(file, title)
      queryClient.invalidateQueries({ queryKey: novelKeys.all })
      navigate(`/novel/${result.novel_id}`)
    } catch (err) {
      let description: string | undefined
      if (err instanceof ApiError) {
        const detail = err.detail as { max_megabytes?: number } | undefined
        if (err.code === 'upload_file_too_large') {
          description = t('library.error.uploadTooLarge', { maxMb: detail?.max_megabytes ?? 30 })
        } else if (err.code === 'upload_type_not_supported') {
          description = t('library.error.uploadTypeNotSupported')
        } else if (err.code === 'upload_parse_failed') {
          description = t('library.error.uploadParseFailed')
        }
      } else if (err instanceof Error && err.message) {
        description = err.message
      }
      void showAlert({ title: t('library.error.uploadFailed'), description })
      setUploadingFileName(null)
    }
    e.target.value = ''
  }

  return (
    <PageShell className="h-screen" navbarProps={{ position: 'static' }} mainClassName="overflow-hidden">
      <input
        ref={fileInputRef}
        data-testid="library-file-input"
        type="file"
        accept=".txt,.md"
        className="hidden"
        disabled={busy}
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
      <div className="flex flex-col flex-1 px-4 sm:px-12 py-10 gap-8 overflow-auto">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex flex-col gap-1">
            <h1 className="m-0 font-mono text-2xl font-bold text-foreground">
              {t('library.title')}
            </h1>
            <p className="m-0 text-sm text-muted-foreground">
              {t('library.description')}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <NwButton
              variant="glass"
              className={libraryActionClass}
              data-testid="library-import-novel"
              disabled={busy}
              onClick={() => fileInputRef.current?.click()}
            >
              <Upload size={18} />
              {t('library.import')}
            </NwButton>
            <NwButton
              variant="accent"
              className={`${libraryActionClass} shadow-[0_0_24px_hsl(var(--accent)/0.35)]`}
              data-testid="library-create-novel"
              disabled={busy}
              onClick={() => createNovel.mutate()}
            >
              <Plus size={18} />
              {t('library.create')}
            </NwButton>
          </div>
        </div>

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

        {error && (
          <p className="text-sm text-[hsl(var(--color-warning))]">
            {t('library.error.load')}: {error instanceof Error ? error.message : t('library.error.unknown')}
          </p>
        )}

        {!loading && !error && novels.length === 0 && (
          <EmptyState />
        )}

        {!loading && !error && novels.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
            {novels.map((novel) => (
              <WorkCard key={novel.id} novel={novel} onDelete={handleDelete} />
            ))}
          </div>
        )}
      </div>
      <ConfirmDialog {...dialogProps} />
    </PageShell>
  )
}

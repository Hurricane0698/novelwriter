import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ChangeEvent } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import '@/lib/uiMessagePacks/novel'
import { getLlmApiErrorMessage } from '@/lib/llmErrorMessages'
import { trackHostedAnalyticsEvent } from '@/lib/hostedAnalytics'
import { ApiError } from '@/services/api'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { useGenerateWorld } from '@/hooks/world/useWorldGeneration'
import { useImportWorldpack } from '@/hooks/world/useWorldpack'
import type { WorldGenerateResponse, WorldpackImportResponse, WorldpackV1 } from '@/types/api'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isWorldpackV1(value: unknown): value is WorldpackV1 {
  return isRecord(value) && value.schema_version === 'worldpack.v1'
}

const MIN_LEN = 10
const MAX_LEN = 50_000

type FastApiValidationErrorItem = {
  loc?: unknown
  type?: unknown
  ctx?: unknown
}

function isTextFieldValidationError(item: FastApiValidationErrorItem): boolean {
  const loc = item.loc
  return Array.isArray(loc) && loc.length > 0 && loc[loc.length - 1] === 'text'
}

function getWorldGenerate422Message(
  detail: unknown,
  t: ReturnType<typeof useUiLocale>['t'],
): string | null {
  if (!Array.isArray(detail)) return null
  const items = detail.filter(isRecord).filter(isTextFieldValidationError)
  for (const item of items) {
    const type = typeof item.type === 'string' ? item.type : ''
    if (type === 'string_too_long') return t('worldModel.generate.validation.maxChars', { count: MAX_LEN.toLocaleString() })
    if (type === 'string_too_short') return t('worldModel.generate.validation.minChars', { count: MIN_LEN })
    if (type === 'world_generate_text_too_short_non_whitespace') return t('worldModel.generate.validation.minChars', { count: MIN_LEN })
  }
  return null
}

export function WorldGenerationDialog({
  novelId,
  open,
  onOpenChange,
  analyticsSource = 'unknown',
  onGenerateSuccess,
  navigateOnGenerateSuccess = true,
  onImportSuccess,
  navigateOnImportSuccess = true,
}: {
  novelId: number
  open: boolean
  onOpenChange: (open: boolean) => void
  analyticsSource?: string
  onGenerateSuccess?: (response: WorldGenerateResponse) => void
  navigateOnGenerateSuccess?: boolean
  onImportSuccess?: (response: WorldpackImportResponse) => void
  navigateOnImportSuccess?: boolean
}) {
  const { locale, t } = useUiLocale()
  const navigate = useNavigate()
  const location = useLocation()
  const sessionRef = useRef(0)
  const modalRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const trackedOpenRef = useRef(false)

  const [text, setText] = useState('')
  const [genError, setGenError] = useState<string | null>(null)
  const [importError, setImportError] = useState<string | null>(null)

  const generate = useGenerateWorld(novelId)
  const importWorldpack = useImportWorldpack(novelId)

  // Mutation ownership survives dismissal; permission to change this view does not.
  useLayoutEffect(() => {
    sessionRef.current += 1
    return () => { sessionRef.current += 1 }
  }, [open, novelId, location.key])

  const closeDialog = useCallback(() => {
    sessionRef.current += 1
    onOpenChange(false)
  }, [onOpenChange])

  useLayoutEffect(() => {
    if (!open) return
    const trigger = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const modal = modalRef.current
    const frame = requestAnimationFrame(() => textareaRef.current?.focus())
    return () => {
      cancelAnimationFrame(frame)
      if (trigger?.isConnected && (document.activeElement === document.body || modal?.contains(document.activeElement))) {
        trigger.focus()
      }
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    setGenError(null)
    setImportError(null)
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') closeDialog() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, closeDialog])

  useEffect(() => {
    if (!open) {
      trackedOpenRef.current = false
      return
    }
    if (trackedOpenRef.current) return
    trackedOpenRef.current = true
    void trackHostedAnalyticsEvent('world_generate_open', {
      novelId,
      meta: {
        source_surface: analyticsSource,
      },
    })
  }, [analyticsSource, novelId, open])

  const trimmed = text.trim()
  const nonWhitespaceLen = trimmed.replace(/\s/g, '').length
  const tooShort = nonWhitespaceLen > 0 && nonWhitespaceLen < MIN_LEN
  const tooLong = trimmed.length > MAX_LEN
  const canSubmit = nonWhitespaceLen >= MIN_LEN && trimmed.length <= MAX_LEN && !generate.isPending

  const handleSubmit = () => {
    if (!canSubmit) return
    const session = sessionRef.current
    setGenError(null)
    void trackHostedAnalyticsEvent('world_generate_submit', {
      novelId,
      meta: {
        source_surface: analyticsSource,
        text_length: trimmed.length,
      },
    })
    generate.mutate(
      { text: trimmed },
      {
        onSuccess: (response) => {
          if (session !== sessionRef.current) return
          onGenerateSuccess?.(response)
          closeDialog()
          if (navigateOnGenerateSuccess) {
            navigate(`/world/${novelId}?tab=review&kind=entities`)
          }
        },
        onError: (err) => {
          void trackHostedAnalyticsEvent('world_generate_failed', {
            novelId,
            meta: {
              source_surface: analyticsSource,
              status: err instanceof ApiError ? err.status : null,
              error_code: err instanceof ApiError ? err.code ?? null : 'client_error',
            },
          })
          if (session !== sessionRef.current) return
          if (err instanceof ApiError) {
            const llmMessage = getLlmApiErrorMessage(err, locale)
            if (llmMessage) {
              setGenError(llmMessage)
              return
            }
            if (err.status === 422) {
              setGenError(getWorldGenerate422Message(err.detail, t) ?? t('worldModel.generate.inputInvalid'))
              return
            }
            if (err.code === 'world_generate_llm_schema_invalid') {
              setGenError(t('worldModel.generate.schemaInvalid'))
              return
            }
            if (err.code === 'world_generate_conflict') {
              setGenError(t('worldModel.generate.conflict'))
              return
            }
          }
          setGenError(t('worldModel.generate.failed'))
        },
      },
    )
  }

  const handleImportSelect = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const session = sessionRef.current
    setImportError(null)
    try {
      const parsed = JSON.parse(await file.text()) as unknown
      if (session !== sessionRef.current) return
      if (!isWorldpackV1(parsed)) {
        void trackHostedAnalyticsEvent('worldpack_import_failed', {
          novelId,
          meta: {
            source_surface: analyticsSource,
            error_code: 'worldpack_file_unsupported',
          },
        })
        setImportError(t('worldModel.worldpack.fileUnsupported'))
        return
      }
      void trackHostedAnalyticsEvent('worldpack_import_submit', {
        novelId,
        meta: {
          source_surface: analyticsSource,
        },
      })
      importWorldpack.mutate(parsed, {
        onSuccess: (response) => {
          if (session !== sessionRef.current) return
          onImportSuccess?.(response)
          closeDialog()
          if (navigateOnImportSuccess) {
            navigate(`/world/${novelId}`)
          }
        },
        onError: (err) => {
          void trackHostedAnalyticsEvent('worldpack_import_failed', {
            novelId,
            meta: {
              source_surface: analyticsSource,
              error_code: err instanceof ApiError ? err.code ?? null : 'worldpack_import_failed',
            },
          })
          if (session === sessionRef.current) setImportError(t('worldModel.worldpack.failed'))
        },
      })
    } catch (err) {
      console.error(err)
      void trackHostedAnalyticsEvent('worldpack_import_failed', {
        novelId,
        meta: {
          source_surface: analyticsSource,
          error_code: 'worldpack_file_unreadable',
        },
      })
      if (session === sessionRef.current) setImportError(t('worldModel.worldpack.fileUnreadable'))
    } finally {
      e.target.value = ''
    }
  }

  if (!open) return null

  return (
    <>
      {/* Overlay */}
      <div
        className="fixed inset-0 z-40 bg-[var(--nw-backdrop)] backdrop-blur-sm"
        onClick={closeDialog}
      />
      {/* Centered modal */}
      <div
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-label={t('worldModel.generate.title')}
        className="fixed inset-0 z-50 flex items-center justify-center p-4"
        data-testid="bottom-sheet"
        data-open="true"
      >
        <div
          className="w-full max-w-2xl rounded-2xl border border-[var(--nw-glass-border-hover)] bg-[hsl(var(--nw-modal-bg))] backdrop-blur-[24px] shadow-[0_24px_80px_var(--nw-backdrop)]"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="p-5 space-y-4 max-h-[80vh] overflow-y-auto" data-testid="world-gen-dialog">
            <div className="space-y-0.5">
              <div className="text-sm font-semibold text-foreground">{t('worldModel.generate.title')}</div>
              <div className="text-xs text-muted-foreground">
                {t('worldModel.generate.description')}
              </div>
            </div>

            <div className="space-y-2">
              <Textarea
                ref={textareaRef}
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder={t('worldModel.generate.placeholder')}
                className="min-h-[180px] bg-transparent border-[var(--nw-glass-border)] text-foreground placeholder:text-muted-foreground/70 focus-visible:ring-accent focus-visible:ring-offset-0"
                data-testid="world-gen-text"
              />
              <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
                <span className={tooShort || tooLong ? 'text-[hsl(var(--color-warning))]' : undefined}>
                  {trimmed.length.toLocaleString()} / {MAX_LEN.toLocaleString()}
                </span>
                {tooShort ? <span>{t('worldModel.generate.minLength', { count: MIN_LEN })}</span> : null}
                {tooLong ? <span>{t('worldModel.generate.tooLong')}</span> : null}
                <span className="ml-auto" />
              </div>
            </div>

            {genError ? (
              <div
                className="rounded-lg border border-[hsl(var(--color-warning)/0.35)] bg-[hsl(var(--color-warning)/0.10)] px-3 py-2 text-xs text-[hsl(var(--color-warning))] whitespace-pre-wrap"
                data-testid="world-gen-error"
              >
                {genError}
              </div>
            ) : null}

            <div className="flex justify-end gap-2">
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="h-8 border-[var(--nw-glass-border)] bg-transparent hover:bg-[var(--nw-glass-bg-hover)]"
                onClick={closeDialog}
              >
                {t('dialog.cancel')}
              </Button>
              <Button
                type="button"
                size="sm"
                className="h-8"
                onClick={handleSubmit}
                disabled={!canSubmit}
                data-testid="world-gen-submit"
              >
                {generate.isPending ? t('worldModel.generate.submitting') : t('worldModel.generate.submit')}
              </Button>
            </div>

            <div className="pt-1 space-y-2">
              <div className="flex items-center gap-2">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="application/json,.json"
                  onChange={handleImportSelect}
                  className="hidden"
                />
                <button
                  type="button"
                  className="text-xs text-muted-foreground hover:text-foreground underline underline-offset-4"
                  onClick={() => fileInputRef.current?.click()}
                  data-testid="world-gen-import-link"
                >
                  {t('worldModel.generate.importLink')}
                </button>
                {importWorldpack.isPending ? (
                  <span className="text-[11px] text-muted-foreground">{t('worldModel.generate.importing')}</span>
                ) : null}
              </div>
              {importError ? (
                <div className="rounded-lg border border-[hsl(var(--color-warning)/0.35)] bg-[hsl(var(--color-warning)/0.10)] px-3 py-2 text-xs text-[hsl(var(--color-warning))] whitespace-pre-wrap">
                  {importError}
                </div>
              ) : null}
            </div>
          </div>
        </div>
      </div>
    </>
  )
}

import { useEffect, useRef, useState, type ChangeEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { getLlmApiErrorMessage } from '@/lib/llmErrorMessages'
import { ApiError } from '@/services/api'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { LABELS } from '@/constants/labels'
import { useGenerateWorld } from '@/hooks/world/useWorldGeneration'
import { useImportWorldpack } from '@/hooks/world/useWorldpack'
import type { WorldpackV1 } from '@/types/api'

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

function isFastApiValidationErrorItem(value: unknown): value is FastApiValidationErrorItem {
  return isRecord(value)
}

function isTextFieldValidationError(item: FastApiValidationErrorItem): boolean {
  const loc = item.loc
  return Array.isArray(loc) && loc.length > 0 && loc[loc.length - 1] === 'text'
}

function getWorldGenerate422Message(detail: unknown): string | null {
  if (!Array.isArray(detail)) return null
  const items = detail.filter(isFastApiValidationErrorItem).filter(isTextFieldValidationError)
  for (const item of items) {
    const type = typeof item.type === 'string' ? item.type : ''
    if (type === 'string_too_long') return `最多输入 ${MAX_LEN.toLocaleString()} 个字符`
    if (type === 'string_too_short') return `请至少输入 ${MIN_LEN} 个非空白字符`
    if (type === 'world_generate_text_too_short_non_whitespace') return `请至少输入 ${MIN_LEN} 个非空白字符`
  }
  return null
}

export function WorldGenerationDialog({
  novelId,
  open,
  onOpenChange,
}: {
  novelId: number
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const navigate = useNavigate()
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [text, setText] = useState('')
  const [genError, setGenError] = useState<string | null>(null)
  const [importError, setImportError] = useState<string | null>(null)

  const generate = useGenerateWorld(novelId)
  const importWorldpack = useImportWorldpack(novelId)

  useEffect(() => {
    if (!open) return
    setGenError(null)
    setImportError(null)
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onOpenChange(false) }
    document.addEventListener('keydown', handler)
    requestAnimationFrame(() => textareaRef.current?.focus())
    return () => document.removeEventListener('keydown', handler)
  }, [open, onOpenChange])

  const trimmed = text.trim()
  const nonWhitespaceLen = trimmed.replace(/\s/g, '').length
  const tooShort = nonWhitespaceLen > 0 && nonWhitespaceLen < MIN_LEN
  const tooLong = trimmed.length > MAX_LEN
  const canSubmit = nonWhitespaceLen >= MIN_LEN && trimmed.length <= MAX_LEN && !generate.isPending

  const handleSubmit = () => {
    if (!canSubmit) return
    setGenError(null)
    generate.mutate(
      { text: trimmed },
      {
        onSuccess: () => {
          onOpenChange(false)
          navigate(`/world/${novelId}?tab=review&kind=entities`)
        },
        onError: (err) => {
          if (err instanceof ApiError) {
            const llmMessage = getLlmApiErrorMessage(err)
            if (llmMessage) {
              setGenError(llmMessage)
              return
            }
            if (err.status === 422) {
              setGenError(getWorldGenerate422Message(err.detail) ?? '输入不符合要求，请检查长度')
              return
            }
            if (err.code === 'world_generate_llm_unavailable') {
              setGenError('AI 服务不可用，请检查模型配置或稍后重试')
              return
            }
            if (err.code === 'world_generate_llm_schema_invalid') {
              setGenError('AI 输出解析失败，请重试')
              return
            }
            if (err.code === 'world_generate_conflict') {
              setGenError('生成冲突，请稍后重试')
              return
            }
          }
          setGenError('生成失败，请重试')
        },
      },
    )
  }

  const handleImportSelect = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setImportError(null)
    try {
      const parsed = JSON.parse(await file.text()) as unknown
      if (!isWorldpackV1(parsed)) {
        setImportError('文件格式不支持，请使用正确的世界观文件')
        return
      }
      importWorldpack.mutate(parsed, {
        onSuccess: () => {
          onOpenChange(false)
          navigate(`/world/${novelId}`)
        },
        onError: () => setImportError(LABELS.WORLDPACK_IMPORT_FAILED),
      })
    } catch (err) {
      console.error(err)
      setImportError('文件内容无法识别，请检查文件格式')
    } finally {
      e.target.value = ''
    }
  }

  return (
    <>
      {/* Overlay */}
      <div
        className={cn(
          'fixed inset-0 z-40 bg-[var(--nw-backdrop)] backdrop-blur-sm transition-opacity',
          open ? 'opacity-100' : 'opacity-0 pointer-events-none'
        )}
        onClick={() => onOpenChange(false)}
      />
      {/* Centered modal */}
      <div
        className={cn(
          'fixed inset-0 z-50 flex items-center justify-center p-4 transition-all duration-200',
          open ? 'opacity-100' : 'opacity-0 pointer-events-none'
        )}
        data-testid="bottom-sheet"
        data-open={open ? 'true' : 'false'}
      >
        <div
          className="w-full max-w-2xl rounded-2xl border border-[var(--nw-glass-border-hover)] bg-[hsl(var(--nw-modal-bg))] backdrop-blur-[24px] shadow-[0_24px_80px_var(--nw-backdrop)]"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="p-5 space-y-4 max-h-[80vh] overflow-y-auto" data-testid="world-gen-dialog">
            <div className="space-y-0.5">
              <div className="text-sm font-semibold text-foreground">从设定生成</div>
              <div className="text-xs text-muted-foreground">
                粘贴世界观设定文本，生成草稿后进入「草稿审核」确认。
              </div>
            </div>

            <div className="space-y-2">
              <Textarea
                ref={textareaRef}
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="在这里粘贴世界观设定（例如：世界规则、阵营、人物关系、力量体系…）"
                className="min-h-[180px] bg-transparent border-[var(--nw-glass-border)] text-foreground placeholder:text-muted-foreground/70 focus-visible:ring-accent focus-visible:ring-offset-0"
                data-testid="world-gen-text"
              />
              <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
                <span className={tooShort || tooLong ? 'text-[hsl(var(--color-warning))]' : undefined}>
                  {trimmed.length.toLocaleString()} / {MAX_LEN.toLocaleString()}
                </span>
                {tooShort ? <span>至少 {MIN_LEN} 个非空白字符</span> : null}
                {tooLong ? <span>已超过上限</span> : null}
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
                onClick={() => onOpenChange(false)}
              >
                {LABELS.CANCEL}
              </Button>
              <Button
                type="button"
                size="sm"
                className="h-8"
                onClick={handleSubmit}
                disabled={!canSubmit}
                data-testid="world-gen-submit"
              >
                {generate.isPending ? '生成中...' : '生成'}
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
                  已有世界观文件？直接导入
                </button>
                {importWorldpack.isPending ? (
                  <span className="text-[11px] text-muted-foreground">导入中...</span>
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

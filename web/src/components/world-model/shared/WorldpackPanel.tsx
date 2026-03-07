import { useMemo, useRef, useState } from 'react'
import { Upload } from 'lucide-react'
import { useImportWorldpack } from '@/hooks/world/useWorldpack'
import { useToast } from '@/components/world-model/shared/useToast'
import { LABELS } from '@/constants/labels'
import { Button } from '@/components/ui/button'
import type { WorldpackImportCounts, WorldpackImportResponse, WorldpackImportWarning, WorldpackV1 } from '@/types/api'

type WorldpackPanelVariant = 'page' | 'sidebar'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isWorldpackV1(value: unknown): value is WorldpackV1 {
  return isRecord(value) && value.schema_version === 'worldpack.v1'
}

function summarizeBucket(
  counts: WorldpackImportCounts,
  bucket: 'created' | 'updated' | 'deleted',
): { total: number; detail?: string } {
  const byType =
    bucket === 'created'
      ? {
          entities: counts.entities_created,
          attributes: counts.attributes_created,
          relationships: counts.relationships_created,
          systems: counts.systems_created,
        }
      : bucket === 'updated'
        ? {
            entities: counts.entities_updated,
            attributes: counts.attributes_updated,
            relationships: counts.relationships_updated,
            systems: counts.systems_updated,
          }
        : {
            entities: counts.entities_deleted,
            attributes: counts.attributes_deleted,
            relationships: counts.relationships_deleted,
            systems: counts.systems_deleted,
          }
  const total = Object.values(byType).reduce((sum, v) => sum + v, 0)
  const parts = Object.entries(byType)
    .filter(([, v]) => v > 0)
    .map(([k, v]) => `${k}:${v}`)
  const detail = parts.length ? parts.join(' · ') : undefined
  return { total, detail }
}

function formatWarning(w: WorldpackImportWarning): string {
  const base = w.code ? `[${w.code}] ${w.message}` : w.message
  return w.path ? `${base} (${w.path})` : base
}

export function WorldpackPanel({ novelId, variant = 'page' }: { novelId: number; variant?: WorldpackPanelVariant }) {
  const { toast } = useToast()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [selectedFile, setSelectedFile] = useState<{ name: string; payload: WorldpackV1 } | null>(null)
  const [parseError, setParseError] = useState<string | null>(null)
  const [result, setResult] = useState<WorldpackImportResponse | null>(null)

  const importMutation = useImportWorldpack(novelId)

  const handleSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    setParseError(null)
    setResult(null)
    setSelectedFile(null)

    try {
      const text = await file.text()
      const parsed = JSON.parse(text) as unknown
      if (!isWorldpackV1(parsed)) {
        setParseError('文件格式不支持，请使用正确的世界观文件')
        return
      }
      setSelectedFile({ name: file.name, payload: parsed })
      importMutation.mutate(parsed, {
        onSuccess: (data) => {
          setResult(data)
          toast(LABELS.WORLDPACK_IMPORT_COMPLETED)
        },
        onError: () => {
          toast(LABELS.WORLDPACK_IMPORT_FAILED)
        },
      })
    } catch (err) {
      console.error(err)
      setParseError('文件内容无法识别，请检查文件格式')
    } finally {
      // Reset input so same file can be selected again
      e.target.value = ''
    }
  }

  const counts = useMemo(() => {
    if (!result) return null
    return {
      created: summarizeBucket(result.counts, 'created'),
      updated: summarizeBucket(result.counts, 'updated'),
      deleted: summarizeBucket(result.counts, 'deleted'),
      warnings: Array.isArray(result.warnings) ? result.warnings : [],
    }
  }, [result])

  const renderControls = (buttonText: string) => (
    <div className="flex items-center gap-2">
      <input
        ref={fileInputRef}
        type="file"
        accept="application/json,.json"
        onChange={handleSelect}
        className="hidden"
      />
      <Button
        variant="outline"
        size="sm"
        className="h-8 text-xs border-[var(--nw-glass-border)] bg-transparent hover:bg-[var(--nw-glass-bg-hover)]"
        disabled={importMutation.isPending}
        onClick={() => fileInputRef.current?.click()}
        data-testid="worldpack-import-btn"
      >
        <Upload className="mr-2 h-3.5 w-3.5" />
        {buttonText}
      </Button>
    </div>
  )

  const renderSummary = (dense: boolean) => {
    if (!counts) return null
    const cardClass = dense
      ? 'rounded-lg bg-[var(--nw-glass-bg)] px-3 py-2'
      : 'rounded-lg bg-[var(--nw-glass-bg)] px-4 py-3'
    const numberClass = dense ? 'mt-0.5 text-lg font-semibold tabular-nums' : 'mt-1 text-2xl font-semibold tabular-nums'

    return (
      <div className={dense ? 'mt-3 space-y-3' : 'mt-4 space-y-4'}>
        <div className={dense ? 'grid grid-cols-3 gap-2' : 'grid grid-cols-1 sm:grid-cols-3 gap-3'}>
          <div className={cardClass}>
            <div className="text-[11px] text-muted-foreground">新增</div>
            <div className={numberClass}>{counts.created.total}</div>
          </div>
          <div className={cardClass}>
            <div className="text-[11px] text-muted-foreground">更新</div>
            <div className={numberClass}>{counts.updated.total}</div>
          </div>
          <div className={cardClass}>
            <div className="text-[11px] text-muted-foreground">删除</div>
            <div className={numberClass}>{counts.deleted.total}</div>
          </div>
        </div>

        {dense ? null : (
          <div className="space-y-1">
            <div className="text-xs font-medium text-foreground">注意事项</div>
            {counts.warnings.length === 0 ? (
              <div className="text-xs text-muted-foreground">无</div>
            ) : (
              <ul className="text-xs text-muted-foreground list-disc pl-5 space-y-0.5">
                {counts.warnings.map((w, idx) => (
                  <li key={`${idx}-${w.code}-${w.path ?? ''}`}>{formatWarning(w)}</li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    )
  }

  const baseCard = (variant: WorldpackPanelVariant) => (
    <div className={variant === 'page' ? 'rounded-xl border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] backdrop-blur-2xl p-4 sm:p-6' : 'rounded-xl border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] backdrop-blur-2xl p-3'}>
      <div className={variant === 'page' ? 'flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between' : 'flex items-start justify-between gap-3'}>
        <div className="space-y-1">
          <div className="text-sm font-semibold tracking-tight">导入世界观</div>
          <div className="text-xs text-muted-foreground">上传世界观文件</div>
        </div>
        {renderControls(variant === 'page' ? '选择文件并导入' : '导入')}
      </div>

      {selectedFile && (
        <div className={variant === 'page' ? 'mt-4 flex flex-wrap items-center gap-x-6 gap-y-1 text-xs text-muted-foreground' : 'mt-3 text-[11px] text-muted-foreground'}>
          <span>
            文件：<span className="text-foreground">{selectedFile.name}</span>
          </span>
          {variant === 'page' && selectedFile.payload.pack_name ? (
            <span>
              包：<span className="text-foreground">{selectedFile.payload.pack_name}</span>
            </span>
          ) : null}
        </div>
      )}

      {parseError && (
        <div className={variant === 'page' ? 'mt-4 rounded-lg bg-amber-50 text-amber-950 ring-1 ring-amber-200 px-3 py-2 text-sm' : 'mt-3 rounded-lg bg-amber-500/10 text-amber-200 ring-1 ring-amber-500/30 px-3 py-2 text-xs'}>
          {parseError}
        </div>
      )}

      {importMutation.isPending && (
        <div className={variant === 'page' ? 'mt-4 flex items-center gap-2 text-xs text-muted-foreground' : 'mt-3 flex items-center gap-2 text-[11px] text-muted-foreground'}>
          <div className="h-2 w-2 rounded-full bg-primary animate-pulse" />
          正在导入...
        </div>
      )}

      {renderSummary(variant === 'sidebar')}
    </div>
  )

  return baseCard(variant)
}

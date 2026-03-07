import { Check, Redo2, Undo2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { NwButton } from '@/components/ui/nw-button'
import { GlassCard } from '@/components/GlassCard'

export type AutoSaveStatus = 'saved' | 'unsaved' | 'idle'

export function ChapterEditor({
  textareaRef,
  value,
  onChange,
  onSelectionChange,
  cursorInfo,
  autoSaveStatus,
  onUndo,
  onRedo,
  onCancel,
  onSave,
}: {
  textareaRef: React.RefObject<HTMLTextAreaElement | null>
  value: string
  onChange: (next: string) => void
  onSelectionChange: () => void
  cursorInfo: { para: number; col: number }
  autoSaveStatus: AutoSaveStatus
  onUndo: () => void
  onRedo: () => void
  onCancel: () => void
  onSave: () => void
}) {
  const wordCount = value.replace(/\s/g, '').length

  return (
    <GlassCard className="flex-1 flex flex-col overflow-hidden rounded-xl">
      <div className="flex items-center gap-2 px-4 py-2 border-b border-[var(--nw-glass-border)]">
        <NwButton
          onClick={onUndo}
          variant="ghost"
          className="w-8 h-8 rounded-md"
          title="撤销"
        >
          <Undo2 size={16} />
        </NwButton>
        <NwButton
          onClick={onRedo}
          variant="ghost"
          className="w-8 h-8 rounded-md"
          title="重做"
        >
          <Redo2 size={16} />
        </NwButton>
      </div>

      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onSelect={onSelectionChange}
        onClick={onSelectionChange}
        onKeyUp={onSelectionChange}
        className="flex-1 resize-none bg-transparent px-8 py-6 outline-none text-[15px] leading-[2] text-foreground caret-accent nw-scrollbar-thin"
      />

      <div className="flex items-center justify-between px-4 py-2 border-t border-[var(--nw-glass-border)]">
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          <span>{wordCount.toLocaleString()} 字</span>
          <span>第 {cursorInfo.para} 段 · 第 {cursorInfo.col} 列</span>
          <span className="inline-flex items-center gap-1.5">
            {autoSaveStatus !== 'idle' ? (
              <>
                <span
                  className={cn(
                    'w-1.5 h-1.5 rounded-full',
                    autoSaveStatus === 'saved'
                      ? 'bg-[hsl(var(--color-status-confirmed))]'
                      : 'bg-muted-foreground'
                  )}
                />
                <span>
                  {autoSaveStatus === 'saved' ? '已自动保存' : '未保存更改'}
                </span>
              </>
            ) : null}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <NwButton
            onClick={onCancel}
            variant="glass"
            className="rounded-lg px-3 py-1.5 text-sm"
          >
            取消
          </NwButton>
          <NwButton
            onClick={onSave}
            variant="accent"
            className="rounded-lg px-3 py-1.5 text-sm font-semibold shadow-[0_0_18px_hsl(var(--accent)/0.25)]"
          >
            <Check size={14} />
            保存
          </NwButton>
        </div>
      </div>
    </GlassCard>
  )
}

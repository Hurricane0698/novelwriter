// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { useState, useEffect, useMemo, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Globe, Pencil, PenTool, Trash2, Upload } from 'lucide-react'
import { ChapterContent } from '@/components/detail/ChapterContent'
import { ChapterEditor } from '@/components/detail/ChapterEditor'
import { ChapterSidebar } from '@/components/detail/ChapterSidebar'
import { EmptyWorldOnboarding } from '@/components/detail/EmptyWorldOnboarding'
import { PageShell } from '@/components/layout/PageShell'
import { NwButton } from '@/components/ui/nw-button'
import { api, ApiError } from '@/services/api'
import { novelKeys } from '@/hooks/novel/keys'
import { useUpdateChapter } from '@/hooks/novel/useUpdateChapter'
import { useCreateChapter } from '@/hooks/novel/useCreateChapter'
import { useDeleteChapter } from '@/hooks/novel/useDeleteChapter'
import { useWorldEntities } from '@/hooks/world/useEntities'
import { useWorldSystems } from '@/hooks/world/useSystems'
import { useBootstrapStatus, useTriggerBootstrap } from '@/hooks/world/useBootstrap'
import { WorldGenerationDialog } from '@/components/world-model/shared/WorldGenerationDialog'
import { LABELS } from '@/constants/labels'
import { formatRelativeTime } from '@/lib/formatRelativeTime'
import { downloadTextFile } from '@/lib/downloadTextFile'
import { formatChapterLabel, serializeChaptersToPlainText, stripLeadingChapterHeading } from '@/lib/chaptersPlainText'
import { useDebouncedAutoSave } from '@/hooks/useDebouncedAutoSave'
import { dismissWorldOnboarding, isWorldOnboardingDismissed } from '@/lib/worldOnboardingStorage'
import type { BootstrapStatus } from '@/types/api'

function countWords(text: string): number {
  return text.replace(/\s/g, '').length
}

const AUTO_SAVE_DELAY = 3000
const BOOTSTRAP_RUNNING_STATUSES: BootstrapStatus[] = [
  'pending',
  'tokenizing',
  'extracting',
  'windowing',
  'refining',
]

export function NovelDetailPage() {
  const { novelId: novelIdParam } = useParams<{ novelId: string }>()
  const navigate = useNavigate()
  const novelId = Number(novelIdParam)

  const [selectedChapterNum, setSelectedChapterNum] = useState<number | null>(null)
  const [editMode, setEditMode] = useState(false)
  const [editingTitle, setEditingTitle] = useState(false)
  const [titleDraft, setTitleDraft] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [editorContent, setEditorContent] = useState('')

  const [worldGenOpen, setWorldGenOpen] = useState(false)
  const [bootstrapError, setBootstrapError] = useState<string | null>(null)

  const { data: worldEntities = [], isLoading: worldEntitiesLoading } = useWorldEntities(novelId)
  const { data: worldSystems = [], isLoading: worldSystemsLoading } = useWorldSystems(novelId)
  const { data: bootstrapJob, isLoading: bootstrapLoading } = useBootstrapStatus(novelId)
  const triggerBootstrap = useTriggerBootstrap(novelId)

  const { data: novel, isLoading: novelLoading } = useQuery({
    queryKey: novelKeys.detail(novelId), queryFn: () => api.getNovel(novelId), enabled: !!novelIdParam,
  })
  // Empty-world onboarding (per novel instance, persisted).
  //
  // We include novel.created_at in the key to avoid collisions when SQLite reuses ids after deletes.
  const worldOnboardingDismissed = useMemo(() => (
    isWorldOnboardingDismissed(novelId, novel?.created_at)
  ), [novelId, novel?.created_at])
  const { data: chaptersMeta = [] } = useQuery({
    queryKey: novelKeys.chaptersMeta(novelId), queryFn: () => api.listChaptersMeta(novelId), enabled: !!novelIdParam,
  })
  const activeChapterNum = selectedChapterNum ?? (chaptersMeta[0]?.chapter_number ?? null)
  const latestChapterNum = chaptersMeta.length > 0 ? chaptersMeta[chaptersMeta.length - 1].chapter_number : null

  const updateChapter = useUpdateChapter(novelId, activeChapterNum ?? 0)
  const createChapter = useCreateChapter(novelId)
  const deleteChapter = useDeleteChapter(novelId)
  const {
    status: autoSaveStatus,
    schedule: scheduleAutoSave,
    saveNow: saveNowAutoSave,
    cancel: cancelAutoSave,
  } = useDebouncedAutoSave<string>({
    delayMs: AUTO_SAVE_DELAY,
    save: async (content) => {
      if (activeChapterNum === null) return
      await updateChapter.mutateAsync({ content })
    },
  })

  const { data: chapter, isLoading: chapterLoading } = useQuery({
    queryKey: novelKeys.chapter(novelId, activeChapterNum ?? 0),
    queryFn: () => {
      if (activeChapterNum === null) {
        // Guard for type safety; `enabled` prevents this from running in practice.
        throw new Error('Missing active chapter number')
      }
      return api.getChapter(novelId, activeChapterNum)
    },
    enabled: !!novelIdParam && activeChapterNum !== null,
  })

  const currentMeta = chaptersMeta.find(c => c.chapter_number === activeChapterNum)

  const filteredChapters = (() => {
    if (!searchQuery.trim()) return chaptersMeta
    const q = searchQuery.toLowerCase()
    return chaptersMeta.filter(c => (c.title ?? '').toLowerCase().includes(q))
  })()

  useEffect(() => {
    // Prevent autosave timers from leaking across chapter switches.
    cancelAutoSave()
  }, [activeChapterNum, cancelAutoSave])

  const handleEditorChange = (val: string) => {
    setEditorContent(val)
    scheduleAutoSave(val)
  }
  const handleSave = () => {
    if (activeChapterNum === null) return
    void saveNowAutoSave(editorContent)
      .then(() => setEditMode(false))
      .catch(() => {
        // Keep the editor open; user can retry.
      })
  }
  const handleCancelEdit = () => {
    cancelAutoSave()
    setEditorContent(chapter?.content ?? '')
    setEditMode(false)
  }
  const handleExportAll = async () => {
    try {
      const allChapters = await api.listChapters(novelId)
      const content = serializeChaptersToPlainText(allChapters)
      downloadTextFile(
        `${novel?.title ?? 'novel'}_全部章节_${new Date().toISOString().slice(0, 10)}.txt`,
        content
      )
    } catch { /* ignore */ }
  }
  const handleCreateChapter = () => {
    createChapter.mutate({ title: '', content: '' }, {
      onSuccess: (nc) => {
        cancelAutoSave()
        setSelectedChapterNum(nc.chapter_number)
        setEditorContent('')
        setEditMode(true)
      },
    })
  }
  const handleTitleSave = () => {
    setEditingTitle(false)
    if (activeChapterNum === null || !currentMeta) return
    const newTitle = titleDraft.trim()
    if (newTitle === (currentMeta.title || '')) return
    updateChapter.mutate({ title: newTitle })
  }

  const handleDeleteChapter = () => {
    if (activeChapterNum === null) return
    if (!window.confirm(`确定要删除第 ${activeChapterNum} 章吗？此操作无法撤销。`)) return
    deleteChapter.mutate(activeChapterNum, {
      onSuccess: () => {
        cancelAutoSave()
        const idx = chaptersMeta.findIndex(c => c.chapter_number === activeChapterNum)
        const next = chaptersMeta[idx + 1] ?? chaptersMeta[idx - 1]
        setSelectedChapterNum(next?.chapter_number ?? null)
        setEditorContent('')
        setEditMode(false)
      },
    })
  }

  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const [cursorInfo, setCursorInfo] = useState({ para: 1, col: 1 })
  const handleSelectionChange = () => {
    const ta = textareaRef.current; if (!ta) return
    const before = ta.value.slice(0, ta.selectionStart); const lines = before.split('\n')
    setCursorInfo({ para: lines.length, col: lines[lines.length - 1].length + 1 })
  }
  const handleUndo = () => { textareaRef.current?.focus(); document.execCommand('undo') }
  const handleRedo = () => { textareaRef.current?.focus(); document.execCommand('redo') }

  const worldLoading = worldEntitiesLoading || worldSystemsLoading || bootstrapLoading
  const worldEmpty = worldEntities.length === 0 && worldSystems.length === 0
  const bootstrapRunning = bootstrapJob
    ? BOOTSTRAP_RUNNING_STATUSES.includes(bootstrapJob.status)
    : false
  const showWorldOnboarding = !worldLoading && !worldOnboardingDismissed && worldEmpty && !bootstrapRunning

  const handleDismissWorldOnboarding = () => {
    dismissWorldOnboarding(novelId, novel?.created_at)
    navigate(`/world/${novelId}`)
  }

  const handleTriggerBootstrap = () => {
    setBootstrapError(null)
    triggerBootstrap.mutate(
      { mode: 'initial' },
      {
        onError: (err) => {
          if (err instanceof ApiError) {
            if (err.code === 'bootstrap_already_running') {
              setBootstrapError(LABELS.BOOTSTRAP_SCANNING)
              return
            }
            if (err.code === 'bootstrap_no_text') {
              setBootstrapError(LABELS.BOOTSTRAP_NO_TEXT)
              return
            }
          }
          setBootstrapError(LABELS.ERROR_BOOTSTRAP_TRIGGER_FAILED)
        },
      },
    )
  }

  if (novelLoading) {
    return (
      <PageShell showNavbar={false} className="h-screen" mainClassName="items-center justify-center">
        <span className="text-sm text-muted-foreground">加载中...</span>
      </PageShell>
    )
  }
  if (!novel) {
    return (
      <PageShell showNavbar={false} className="h-screen" mainClassName="items-center justify-center">
        <span className="text-sm text-[hsl(var(--color-warning))]">作品不存在</span>
      </PageShell>
    )
  }

  const wordCount = countWords(editMode ? editorContent : (chapter?.content ?? ''))
  const displayTitle = currentMeta?.title ? stripLeadingChapterHeading(currentMeta.title) : ''

  return (
    <PageShell className="h-screen" navbarProps={{ position: 'static' }} mainClassName="overflow-hidden">
      {showWorldOnboarding ? (
        <>
          <EmptyWorldOnboarding
            onGenerate={() => setWorldGenOpen(true)}
            onBootstrap={handleTriggerBootstrap}
            onDismiss={handleDismissWorldOnboarding}
            bootstrapPending={triggerBootstrap.isPending}
            bootstrapError={bootstrapError}
          />
          <WorldGenerationDialog novelId={novelId} open={worldGenOpen} onOpenChange={setWorldGenOpen} />
        </>
      ) : (
        <div className="flex flex-1 overflow-hidden">
          <ChapterSidebar
            novelTitle={novel.title}
            searchQuery={searchQuery}
            onSearchQueryChange={setSearchQuery}
            chapters={filteredChapters.map(c => ({
              chapterNumber: c.chapter_number,
              label: formatChapterLabel(c.chapter_number, c.title),
            }))}
            selectedChapterNumber={activeChapterNum}
            onSelectChapter={(chapterNumber) => {
              cancelAutoSave()
              setSelectedChapterNum(chapterNumber)
              setEditingTitle(false)
              setEditorContent('')
              setEditMode(false)
            }}
            chapterCount={chaptersMeta.length}
            onCreateChapter={handleCreateChapter}
            isCreating={createChapter.isPending}
          />

          {/* ── Content Area ── */}
          <div className="flex-1 min-w-0 flex flex-col gap-8 px-8 py-8 lg:px-16 overflow-hidden">
            {/* Action Bar */}
            <div className="flex items-start justify-between gap-6 shrink-0">
              <div className="min-w-0 flex flex-col gap-1">
                <div className="font-mono text-[22px] font-semibold text-foreground truncate flex items-center gap-2">
                  {currentMeta ? (
                    <>
                      <span className="text-foreground/90 font-semibold shrink-0">
                        第 {currentMeta.chapter_number} 章
                      </span>
                      {editingTitle ? (
                        <input
                          autoFocus
                          value={titleDraft}
                          onChange={e => setTitleDraft(e.target.value)}
                          onBlur={() => { handleTitleSave() }}
                          onKeyDown={e => { if (e.key === 'Enter') handleTitleSave(); if (e.key === 'Escape') setEditingTitle(false) }}
                          className="font-mono text-[22px] font-semibold text-foreground bg-[var(--nw-glass-bg)] border border-[hsl(var(--accent)/0.35)] rounded-md px-2 py-0.5 outline-none min-w-[120px] focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-0"
                          placeholder="输入章节标题"
                        />
                      ) : (
                        <span
                          onDoubleClick={() => { setTitleDraft(displayTitle); setEditingTitle(true) }}
                          title="双击编辑标题"
                          className="cursor-text"
                        >
                          {displayTitle ? (
                            `· ${displayTitle}`
                          ) : (
                            <span className="text-muted-foreground italic">双击添加标题</span>
                          )}
                        </span>
                      )}
                    </>
                  ) : '选择章节'}
                </div>
                {currentMeta ? (
                  <div className="text-sm text-muted-foreground">
                    {editMode ? '编辑中' : '阅读中'} · {wordCount.toLocaleString()} 字{currentMeta.created_at ? ` · ${formatRelativeTime(currentMeta.created_at)}更新` : ''}
                  </div>
                ) : null}
              </div>

              <div className="flex items-center gap-2.5 shrink-0 flex-wrap justify-end">
                <NwButton
                  onClick={() => {
                    if (activeChapterNum === null) return
                    if (!editMode) {
                      // Avoid setState-in-effect by initializing the editor draft from the current chapter on-demand.
                      setEditorContent(chapter?.content ?? '')
                      cancelAutoSave()
                    } else {
                      cancelAutoSave()
                    }
                    setEditMode(!editMode)
                  }}
                  disabled={activeChapterNum === null}
                  variant="accentOutline"
                  className="rounded-[10px] px-4 py-2 text-sm font-medium disabled:cursor-not-allowed"
                >
                  <Pencil size={14} />
                  编辑
                </NwButton>

                <NwButton
                  data-testid="novel-continue-button"
                  onClick={() => { if (latestChapterNum !== null) navigate(`/novel/${novelId}/chapter/${latestChapterNum}/write`) }}
                  disabled={latestChapterNum === null}
                  variant="accent"
                  className="rounded-[10px] px-4 py-2 text-sm font-semibold shadow-[0_0_18px_hsl(var(--accent)/0.25)]"
                >
                  <PenTool size={14} />
                  续写
                </NwButton>

                <NwButton
                  onClick={() => navigate(`/world/${novelId}`)}
                  variant="glass"
                  className="rounded-[10px] px-4 py-2 text-sm font-medium"
                >
                  <Globe size={14} />
                  世界模型
                </NwButton>

                <NwButton
                  onClick={handleExportAll}
                  variant="glass"
                  className="rounded-[10px] px-4 py-2 text-sm font-medium"
                >
                  <Upload size={14} />
                  导出全部章节
                </NwButton>

                {activeChapterNum !== null && chaptersMeta.length > 1 ? (
                  <NwButton
                    onClick={handleDeleteChapter}
                    variant="dangerOutline"
                    className="rounded-[10px] px-4 py-2 text-sm font-medium"
                  >
                    <Trash2 size={14} />
                    删除章节
                  </NwButton>
                ) : null}
              </div>
            </div>

            {/* ── Editor / Reader Area ── */}
            {editMode && activeChapterNum !== null ? (
                <ChapterEditor
                  textareaRef={textareaRef}
                  value={editorContent}
                  onChange={handleEditorChange}
                  onSelectionChange={handleSelectionChange}
                  cursorInfo={cursorInfo}
                  autoSaveStatus={autoSaveStatus}
                  onUndo={handleUndo}
                  onRedo={handleRedo}
                  onCancel={handleCancelEdit}
                  onSave={handleSave}
              />
            ) : (
              <ChapterContent
                isLoading={chapterLoading}
                content={chapter?.content ?? null}
              />
            )}
          </div>
        </div>
      )}
    </PageShell>
  )
}

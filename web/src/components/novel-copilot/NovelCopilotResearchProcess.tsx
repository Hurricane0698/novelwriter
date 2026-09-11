import { useMemo, useState } from 'react'
import { BookOpen, ChevronDown, ChevronUp, Database, Search, Sparkles, Wrench } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { translateUiMessage, type UiLocale } from '@/lib/uiMessages'
import type { CopilotEvidence, CopilotTraceStep } from '@/types/copilot'
import { getCopilotEvidenceSourceMeta } from './novelCopilotView'
import {
  copilotPanelMutedClassName,
  copilotPillClassName,
  copilotPillInteractiveClassName,
  copilotQuoteClassName,
} from './novelCopilotChrome'

type ResearchDetailSelection =
  | { type: 'evidence'; id: string }
  | { type: 'tool'; id: string }

function chapterLabel(evidence: CopilotEvidence, locale: UiLocale) {
  const chapterNumber = typeof evidence.source_ref?.chapter_number === 'number'
    ? evidence.source_ref.chapter_number
    : null
  return chapterNumber ? translateUiMessage(locale, 'copilot.research.chapterLabel', { chapter: chapterNumber }) : null
}

function getEvidencePreviewText(evidence: CopilotEvidence) {
  return evidence.preview_excerpt?.trim() ? evidence.preview_excerpt : evidence.excerpt
}

function getEvidenceDetailHeading(evidence: CopilotEvidence, locale: UiLocale) {
  if (evidence.pack_id) {
    return evidence.expanded
      ? translateUiMessage(locale, 'copilot.research.detail.moreContext')
      : translateUiMessage(locale, 'copilot.research.detail.relatedEvidence')
  }
  return translateUiMessage(locale, 'copilot.research.detail.fullEvidence')
}

function getEvidenceStateLabel(evidence: CopilotEvidence, locale: UiLocale) {
  if (!evidence.pack_id) return null
  return evidence.expanded
    ? translateUiMessage(locale, 'copilot.research.state.expandedContext')
    : translateUiMessage(locale, 'copilot.research.state.clueSummary')
}

function getEvidenceReasonText(evidence: CopilotEvidence, locale: UiLocale) {
  const raw = evidence.why_relevant?.trim() ?? ''
  if (!raw) {
    return evidence.pack_id ? translateUiMessage(locale, 'copilot.research.reason.fromRelatedClues') : ''
  }

  if (/tool-discovered/i.test(raw)) {
    return evidence.expanded
      ? translateUiMessage(locale, 'copilot.research.reason.fromExpandedContext')
      : translateUiMessage(locale, 'copilot.research.reason.fromRelatedClues')
  }

  if (locale === 'zh') {
    const normalized = raw
      .replace(/Tool-discovered/gi, translateUiMessage(locale, 'copilot.research.reason.fromToolResults'))
      .replace(/\(support:\s*\d+\)/gi, '')
      .replace(/support[:：]?\s*\d+/gi, '')
      .replace(/证据包/g, '相关线索')
      .replace(/\s{2,}/g, ' ')
      .trim()
    return normalized || (evidence.pack_id ? translateUiMessage(locale, 'copilot.research.reason.fromRelatedClues') : '')
  }

  const normalized = raw
    .replace(/Tool-discovered/gi, translateUiMessage(locale, 'copilot.research.reason.fromToolResults'))
    .replace(/\(support:\s*\d+\)/gi, '')
    .replace(/support[:：]?\s*\d+/gi, '')
    .replace(/evidence pack/gi, 'related clues')
    .replace(/\s{2,}/g, ' ')
    .trim()

  return normalized || (evidence.pack_id ? translateUiMessage(locale, 'copilot.research.reason.fromRelatedClues') : '')
}

function getToolSummaryText(step: CopilotTraceStep, locale: UiLocale) {
  if (locale === 'zh') {
    return step.summary
      .replace(/^本轮启用工具研究模式，调用 (\d+) 次工具$/, '本轮通过分步检索整理信息，共执行 $1 步')
      .replace(/^本轮未触发工具调用，模型直接完成分析$/, '本轮未追加检索步骤，模型直接完成分析')
      .replace(/^当前模型不支持工具调用，已降级为单轮分析$/, '当前模型不支持分步检索，已切换为直接分析')
      .replace(/^工具链路异常（(.+)），已降级为单轮分析$/, '分步检索异常（$1），已切换为直接分析')
      .replace(/^正在整理工具结果并生成回答\.\.\.$/, '正在整理检索结果并生成回答...')
      .replace(/^工具检索：搜索/, '搜索')
      .replace(/^工具展开：打开证据包 .+?(，来源 \d+ 条)?$/, (_match, suffix?: string) =>
        `展开更多上下文${suffix ? suffix.replace('，来源', '，补充了').replace('条', '条来源') : ''}`,
      )
      .replace(/^展开更多上下文（.+?）/, '展开更多上下文')
      .replace(/^工具读取：读取 /, '读取 ')
      .replace(/^工具快照：/, '刷新当前设定：')
      .replace(/^工具模式：/, '研究过程：')
      .replace(/证据包/g, '相关线索')
      .replace(/命中 (\d+) 个证据包/g, '找到 $1 组相关线索')
  }

  return step.summary
    .replace(/^Tool-mode: used (\d+) tool calls? this round$/i, 'This round used $1 retrieval steps')
    .replace(/^No tool calls were needed; the model completed the analysis directly$/i, 'No extra retrieval steps were needed; the model completed the analysis directly')
    .replace(/^The active model does not support tool calling; downgraded to one-shot analysis$/i, 'The active model does not support multi-step retrieval, so the run switched to direct analysis')
    .replace(/^Tool-chain failure \((.+)\), downgraded to one-shot analysis$/i, 'Multi-step retrieval failed ($1), so the run switched to direct analysis')
    .replace(/^Compiling tool results and drafting the answer\.\.\.$/i, 'Compiling retrieval results and drafting the answer...')
    .replace(/^Search for /i, 'Search ')
    .replace(/^Open evidence pack .+?(, sourced from \d+ refs?)?$/i, (_match, suffix?: string) =>
      `Expand related context${suffix ? suffix.replace(', sourced from', ', added').replace(' refs', ' sources').replace(' ref', ' source') : ''}`,
    )
    .replace(/^Load scope snapshot:/i, 'Refresh current world state:')
    .replace(/^Tool mode:/i, 'Research process:')
    .replace(/evidence pack/gi, 'related clues')
    .replace(/found (\d+) evidence packs?/gi, 'found $1 groups of related clues')
}

function getToolMeta(step: CopilotTraceStep, locale: UiLocale) {
  switch (step.kind) {
    case 'tool_find':
      return { label: translateUiMessage(locale, 'copilot.research.tool.find'), icon: Search }
    case 'tool_open':
      return { label: translateUiMessage(locale, 'copilot.research.tool.open'), icon: BookOpen }
    case 'tool_read':
    case 'tool_load_scope_snapshot':
      return { label: translateUiMessage(locale, 'copilot.research.tool.read'), icon: Database }
    case 'tool_mode':
      return { label: translateUiMessage(locale, 'copilot.research.tool.mode'), icon: Wrench }
    default:
      return { label: translateUiMessage(locale, 'copilot.research.tool.step'), icon: Sparkles }
  }
}

function buildProcessSummary(toolCount: number, evidenceCount: number, hasRunningStep: boolean, locale: UiLocale) {
  const parts: string[] = []
  if (toolCount > 0) parts.push(translateUiMessage(locale, 'copilot.research.summary.toolSteps', { count: toolCount }))
  if (evidenceCount > 0) parts.push(translateUiMessage(locale, 'copilot.research.summary.evidenceCount', { count: evidenceCount }))
  if (parts.length === 0) {
    return hasRunningStep
      ? translateUiMessage(locale, 'copilot.research.summary.processing')
      : translateUiMessage(locale, 'copilot.research.summary.none')
  }
  return parts.join(' · ')
}

export function NovelCopilotResearchProcess({
  trace,
  evidence,
}: {
  trace: CopilotTraceStep[]
  evidence: CopilotEvidence[]
}) {
  const { locale, t } = useUiLocale()
  const toolModeStep = trace.find((step) => step.kind === 'tool_mode') ?? null
  const toolSteps = useMemo(
    () => trace.filter((step) => step.kind.startsWith('tool_') && step.kind !== 'tool_mode'),
    [trace],
  )
  const hasRunningStep = trace.some((step) => step.status === 'running')
  const hasProcessContent = trace.length > 0 || evidence.length > 0
  const [isExpanded, setIsExpanded] = useState(false)
  const [selection, setSelection] = useState<ResearchDetailSelection | null>(null)

  const selectedEvidence =
    selection?.type === 'evidence'
      ? evidence.find((item) => item.evidence_id === selection.id) ?? null
      : null
  const selectedTool =
    selection?.type === 'tool'
      ? toolSteps.find((item) => item.step_id === selection.id) ?? null
      : null

  if (!hasProcessContent) return null

  const processSummary = buildProcessSummary(toolSteps.length, evidence.length, hasRunningStep, locale)

  return (
    <section className="border-y border-[var(--nw-copilot-border)] py-3" data-testid="copilot-research-process">
      <button
        type="button"
        onClick={() => setIsExpanded((value) => !value)}
        className="flex w-full items-center justify-between gap-3 text-left"
        aria-expanded={isExpanded}
        aria-label={isExpanded ? t('copilot.research.collapse') : t('copilot.research.expand')}
      >
        <div className="min-w-0">
          <div className="text-xs font-medium text-foreground/82">
            {t('copilot.research.panelLabel')}
          </div>
          <div className="mt-1 text-[12px] text-muted-foreground/78">
            {processSummary}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {toolModeStep ? (
            <span className={cn('inline-flex items-center rounded-full px-2 py-0.5 text-[10px] text-muted-foreground/78', copilotPillClassName)}>
              {toolModeStep.status === 'running' ? t('copilot.research.summary.processing') : t('copilot.research.viewable')}
            </span>
          ) : null}
          <span className={cn('inline-flex h-8 w-8 items-center justify-center rounded-full', copilotPillInteractiveClassName)}>
            {isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </span>
        </div>
      </button>

      {isExpanded ? (
        <div className="mt-3 space-y-3 border-t border-[var(--nw-copilot-border)] pt-3">
          {toolModeStep ? (
            <div className="text-xs leading-5 text-muted-foreground/80">
              {getToolSummaryText(toolModeStep, locale)}
            </div>
          ) : null}

          {toolSteps.length > 0 ? (
            <div className="space-y-2">
              <div className="text-xs font-medium text-foreground/72">
                {t('copilot.research.searchProcess')}
              </div>
              <div className="space-y-2">
                {toolSteps.map((step) => {
                  const meta = getToolMeta(step, locale)
                  const Icon = meta.icon
                  const active = selection?.type === 'tool' && selection.id === step.step_id
                  return (
                    <button
                      key={step.step_id}
                      type="button"
                      onClick={() => setSelection({ type: 'tool', id: step.step_id })}
                      className={cn(
                        'flex w-full items-start gap-3 rounded-xl px-2 py-2.5 text-left transition-colors',
                        active ? 'bg-foreground/8' : 'hover:bg-foreground/4',
                      )}
                    >
                      <span className={cn('mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full', copilotPillClassName)}>
                        <Icon className="h-3.5 w-3.5 text-foreground/78" />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block text-[11px] text-muted-foreground/72">{meta.label}</span>
                        <span className="mt-1 block text-[12px] leading-5 text-foreground/90">{getToolSummaryText(step, locale)}</span>
                      </span>
                    </button>
                  )
                })}
              </div>
            </div>
          ) : null}

          {evidence.length > 0 ? (
            <div className="space-y-2">
              <div className="text-xs font-medium text-foreground/72">
                {t('copilot.research.relatedEvidenceSection')}
              </div>
              <div className="space-y-2">
                {evidence.map((item) => {
                  const meta = getCopilotEvidenceSourceMeta(item.source_type, locale)
                  const active = selection?.type === 'evidence' && selection.id === item.evidence_id
                  const previewText = getEvidencePreviewText(item)
                  const preview = previewText.length > 84 ? `${previewText.slice(0, 84)}…` : previewText
                  const evidenceChapterLabel = chapterLabel(item, locale)
                  const evidenceStateLabel = getEvidenceStateLabel(item, locale)
                  const evidenceReason = getEvidenceReasonText(item, locale)
                  return (
                    <button
                      key={item.evidence_id}
                      type="button"
                      onClick={() => setSelection({ type: 'evidence', id: item.evidence_id })}
                      className={cn(
                        'flex w-full flex-col gap-2 rounded-xl px-2 py-3 text-left transition-colors',
                        active ? 'bg-foreground/8' : 'hover:bg-foreground/4',
                      )}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex min-w-0 flex-wrap items-center gap-1.5">
                          <span className={cn('inline-flex items-center rounded-full border px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.16em]', meta.chipClassName)}>
                            {meta.label}
                          </span>
                          {evidenceStateLabel ? (
                            <span className={cn('rounded-full px-2 py-0.5 text-[10px] text-muted-foreground/78', copilotPillClassName)}>
                              {evidenceStateLabel}
                            </span>
                          ) : null}
                          {evidenceChapterLabel ? (
                            <span className={cn('rounded-full px-2 py-0.5 text-[10px] text-muted-foreground/78', copilotPillClassName)}>
                              {evidenceChapterLabel}
                            </span>
                          ) : null}
                        </div>
                        {evidenceReason ? (
                          <span className={cn('truncate rounded-full px-2 py-0.5 text-[10px] text-muted-foreground/80', copilotPillClassName)} title={evidenceReason}>
                            {evidenceReason}
                          </span>
                        ) : null}
                      </div>
                      <div className="text-[12px] font-medium text-foreground/92">{item.title}</div>
                      <div className="text-[12px] leading-5 text-muted-foreground/78">{preview}</div>
                      {item.anchor_terms && item.anchor_terms.length > 0 ? (
                        <div className="flex flex-wrap gap-1.5">
                          {item.anchor_terms.slice(0, 4).map((term) => (
                            <span
                              key={`${item.evidence_id}-${term}`}
                              className={cn('rounded-full px-2 py-0.5 text-[10px] text-muted-foreground/76', copilotPillClassName)}
                            >
                              {term}
                            </span>
                          ))}
                        </div>
                      ) : null}
                    </button>
                  )
                })}
              </div>
            </div>
          ) : null}

          {(selectedEvidence || selectedTool) ? (
            <div className="space-y-2 border-t border-[var(--nw-copilot-border)] pt-3" data-testid="copilot-research-detail">
              {selectedEvidence ? (
                <>
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-xs font-medium text-foreground/72">
                      {getEvidenceDetailHeading(selectedEvidence, locale)}
                    </div>
                    <div className="flex flex-wrap justify-end gap-1.5">
                      {getEvidenceStateLabel(selectedEvidence, locale) ? (
                        <span className={cn('rounded-full px-2 py-0.5 text-[10px] text-muted-foreground/80', copilotPillClassName)}>
                          {getEvidenceStateLabel(selectedEvidence, locale)}
                        </span>
                      ) : null}
                      {chapterLabel(selectedEvidence, locale) ? (
                        <span className={cn('rounded-full px-2 py-0.5 text-[10px] text-muted-foreground/80', copilotPillClassName)}>
                          {chapterLabel(selectedEvidence, locale)}
                        </span>
                      ) : null}
                      <span className={cn('rounded-full px-2 py-0.5 text-[10px] text-muted-foreground/80', copilotPillClassName)}>
                        {selectedEvidence.title}
                      </span>
                    </div>
                  </div>
                  {getEvidenceReasonText(selectedEvidence, locale) ? (
                    <div className="text-[12px] text-muted-foreground/76">{getEvidenceReasonText(selectedEvidence, locale)}</div>
                  ) : null}
                  <div className={cn('rounded-[18px] px-3 py-3', copilotQuoteClassName)}>
                    <div className="whitespace-pre-wrap text-[13px] leading-6 text-foreground/88">
                      {selectedEvidence.excerpt}
                    </div>
                  </div>
                </>
              ) : null}

              {selectedTool ? (
                <>
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-xs font-medium text-foreground/72">
                      {t('copilot.research.processDescription')}
                    </div>
                    <span className={cn('rounded-full px-2 py-0.5 text-[10px] text-muted-foreground/80', copilotPillClassName)}>
                      {getToolMeta(selectedTool, locale).label}
                    </span>
                  </div>
                  <div className="text-[13px] leading-6 text-foreground/90">{getToolSummaryText(selectedTool, locale)}</div>
                  <div className={cn('rounded-[18px] px-3 py-3 text-[12px] leading-5 text-muted-foreground/78', copilotPanelMutedClassName)}>
                    {t('copilot.research.processNote')}
                  </div>
                </>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}

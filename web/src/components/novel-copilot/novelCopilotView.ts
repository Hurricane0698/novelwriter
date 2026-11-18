import { resolveCurrentUiLocale } from '@/lib/uiLocale'
import { translateUiMessage, type UiLocale } from '@/lib/uiMessages'
import type { CopilotRunStatus } from '@/types/copilot'

function readLocale(locale?: UiLocale): UiLocale {
  return locale ?? resolveCurrentUiLocale()
}

export function getCopilotRunStatusMeta(status: CopilotRunStatus | null, locale?: UiLocale) {
  const effectiveLocale = readLocale(locale)
  switch (status) {
    case 'queued':
      return {
        label: translateUiMessage(effectiveLocale, 'copilot.runStatus.queued'),
        dotClassName: 'bg-[hsl(var(--foreground)/0.38)]',
        toneClassName: 'text-muted-foreground',
      }
    case 'running':
      return {
        label: translateUiMessage(effectiveLocale, 'copilot.runStatus.running'),
        dotClassName: 'bg-[hsl(var(--foreground)/0.80)] animate-pulse shadow-[0_0_12px_hsl(var(--foreground)/0.14)]',
        toneClassName: 'text-foreground/80',
      }
    case 'error':
    case 'interrupted':
      return {
        label: translateUiMessage(effectiveLocale, status === 'interrupted' ? 'copilot.runStatus.interrupted' : 'copilot.runStatus.error'),
        dotClassName: 'bg-[hsl(var(--color-danger))] shadow-[0_0_10px_hsl(var(--color-danger)/0.40)]',
        toneClassName: 'text-[hsl(var(--color-danger))]',
      }
    case 'completed':
      return {
        label: translateUiMessage(effectiveLocale, 'copilot.runStatus.completed'),
        dotClassName: 'bg-[hsl(var(--foreground)/0.62)]',
        toneClassName: 'text-foreground/70',
      }
    default:
      return {
        label: translateUiMessage(effectiveLocale, 'copilot.runStatus.idle'),
        dotClassName: 'bg-muted-foreground/70',
        toneClassName: 'text-muted-foreground',
      }
  }
}

export function getCopilotSuggestionKindMeta(kind: string, locale?: UiLocale) {
  const effectiveLocale = readLocale(locale)
  switch (kind) {
    case 'replace_text':
      return {
        label: translateUiMessage(effectiveLocale, 'review.rewrite'),
        chipClassName: 'border-border bg-muted/40 text-foreground/80',
        accentClassName: 'bg-foreground/40',
      }
    case 'create_entity':
    case 'update_entity':
    case 'entity_update':
      return {
        label: translateUiMessage(effectiveLocale, 'copilot.suggestion.kind.entity'),
        chipClassName: 'border-[hsl(var(--foreground)/0.12)] bg-[hsl(var(--foreground)/0.06)] text-foreground/82',
        accentClassName: 'bg-[hsl(var(--foreground)/0.52)]',
      }
    case 'create_relationship':
    case 'update_relationship':
    case 'relationship_update':
      return {
        label: translateUiMessage(effectiveLocale, 'copilot.suggestion.kind.relationship'),
        chipClassName: 'border-[hsl(var(--foreground)/0.12)] bg-[hsl(var(--foreground)/0.05)] text-foreground/74',
        accentClassName: 'bg-[hsl(var(--foreground)/0.38)]',
      }
    case 'create_system':
    case 'update_system':
    case 'system_update':
      return {
        label: translateUiMessage(effectiveLocale, 'copilot.suggestion.kind.system'),
        chipClassName: 'border-[hsl(var(--foreground)/0.12)] bg-[hsl(var(--foreground)/0.04)] text-foreground/68',
        accentClassName: 'bg-[hsl(var(--foreground)/0.28)]',
      }
    default:
      return {
        label: kind,
        chipClassName: 'border-[hsl(var(--foreground)/0.10)] bg-[hsl(var(--foreground)/0.04)] text-muted-foreground',
        accentClassName: 'bg-[hsl(var(--foreground)/0.18)]',
      }
  }
}

export function getCopilotEvidenceSourceMeta(sourceType: string, locale?: UiLocale) {
  const effectiveLocale = readLocale(locale)
  switch (sourceType) {
    case 'chapter_excerpt':
      return {
        label: translateUiMessage(effectiveLocale, 'copilot.suggestion.source.chapterExcerpt'),
        chipClassName: 'border-[hsl(var(--foreground)/0.12)] bg-[hsl(var(--foreground)/0.06)] text-foreground/80',
      }
    case 'world_entity':
      return {
        label: translateUiMessage(effectiveLocale, 'copilot.suggestion.source.worldEntity'),
        chipClassName: 'border-[hsl(var(--foreground)/0.12)] bg-[hsl(var(--foreground)/0.06)] text-foreground/80',
      }
    case 'world_relationship':
      return {
        label: translateUiMessage(effectiveLocale, 'copilot.suggestion.source.worldRelationship'),
        chipClassName: 'border-[hsl(var(--foreground)/0.12)] bg-[hsl(var(--foreground)/0.05)] text-foreground/74',
      }
    case 'world_system':
      return {
        label: translateUiMessage(effectiveLocale, 'copilot.suggestion.source.worldSystem'),
        chipClassName: 'border-[hsl(var(--foreground)/0.12)] bg-[hsl(var(--foreground)/0.04)] text-foreground/68',
      }
    case 'evidence_pack':
      return {
        label: translateUiMessage(effectiveLocale, 'copilot.suggestion.source.evidencePack'),
        chipClassName: 'border-[hsl(var(--foreground)/0.12)] bg-[hsl(var(--foreground)/0.05)] text-foreground/74',
      }
    case 'draft_review':
      return {
        label: translateUiMessage(effectiveLocale, 'copilot.suggestion.source.draftReview'),
        chipClassName: 'border-[hsl(var(--foreground)/0.12)] bg-[hsl(var(--foreground)/0.04)] text-foreground/68',
      }
    default:
      return {
        label: sourceType,
        chipClassName: 'border-[hsl(var(--foreground)/0.10)] bg-[hsl(var(--foreground)/0.04)] text-muted-foreground',
      }
    }
}

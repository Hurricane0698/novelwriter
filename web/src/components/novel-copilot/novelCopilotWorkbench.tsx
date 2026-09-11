import {
  FileSearch,
  FileText,
  Link2,
  type LucideIcon,
  Search,
  Sparkles,
} from 'lucide-react'
import { resolveCurrentUiLocale } from '@/lib/uiLocale'
import { translateUiMessage, type UiLocale } from '@/lib/uiMessages'
import type { CopilotPrefill } from '@/types/copilot'
import { getCopilotScenario } from './novelCopilotHelpers'

export interface CopilotQuickActionSpec {
  id: string
  label: string
  description: string
  prompt: string
  icon: LucideIcon
}

export interface CopilotWorkbenchMeta {
  introTitle: string
  composerLabel: string
  composerPlaceholder: string
  quickActions: CopilotQuickActionSpec[]
}

function t(locale: UiLocale, key: Parameters<typeof translateUiMessage>[1], params?: Parameters<typeof translateUiMessage>[2]) {
  return translateUiMessage(locale, key, params)
}

function wholeBookActions(locale: UiLocale): CopilotQuickActionSpec[] {
  return [
    {
      id: 'scan_world_gaps',
      label: t(locale, 'copilot.workbench.wholeBook.scanGaps.label'),
      description: t(locale, 'copilot.workbench.wholeBook.scanGaps.description'),
      prompt: t(locale, 'copilot.workbench.wholeBook.scanGaps.prompt'),
      icon: Search,
    },
    {
      id: 'trace_recurring_signals',
      label: t(locale, 'copilot.workbench.wholeBook.traceSignals.label'),
      description: t(locale, 'copilot.workbench.wholeBook.traceSignals.description'),
      prompt: t(locale, 'copilot.workbench.wholeBook.traceSignals.prompt'),
      icon: Sparkles,
    },
    {
      id: 'find_world_conflicts',
      label: t(locale, 'copilot.workbench.wholeBook.findConflicts.label'),
      description: t(locale, 'copilot.workbench.wholeBook.findConflicts.description'),
      prompt: t(locale, 'copilot.workbench.wholeBook.findConflicts.prompt'),
      icon: FileSearch,
    },
  ]
}

function currentEntityActions(locale: UiLocale, subject: string): CopilotQuickActionSpec[] {
  return [
    {
      id: 'complete_entity',
      label: t(locale, 'copilot.workbench.entity.complete.label'),
      description: t(locale, 'copilot.workbench.entity.complete.description'),
      prompt: t(locale, 'copilot.workbench.entity.complete.prompt', { subject }),
      icon: Sparkles,
    },
    {
      id: 'find_relations',
      label: t(locale, 'copilot.workbench.entity.findRelations.label'),
      description: t(locale, 'copilot.workbench.entity.findRelations.description'),
      prompt: t(locale, 'copilot.workbench.entity.findRelations.prompt', { subject }),
      icon: Link2,
    },
    {
      id: 'collect_entity_evidence',
      label: t(locale, 'copilot.workbench.entity.collectEvidence.label'),
      description: t(locale, 'copilot.workbench.entity.collectEvidence.description'),
      prompt: t(locale, 'copilot.workbench.entity.collectEvidence.prompt', { subject }),
      icon: FileSearch,
    },
  ]
}

function relationshipActions(locale: UiLocale, subject: string): CopilotQuickActionSpec[] {
  return [
    {
      id: 'find_relations',
      label: t(locale, 'copilot.workbench.relationships.find.label'),
      description: t(locale, 'copilot.workbench.relationships.find.description'),
      prompt: t(locale, 'copilot.workbench.relationships.find.prompt', { subject }),
      icon: Link2,
    },
    {
      id: 'label_relationships',
      label: t(locale, 'copilot.workbench.relationships.labeling.label'),
      description: t(locale, 'copilot.workbench.relationships.labeling.description'),
      prompt: t(locale, 'copilot.workbench.relationships.labeling.prompt', { subject }),
      icon: Sparkles,
    },
    {
      id: 'collect_interactions',
      label: t(locale, 'copilot.workbench.relationships.collect.label'),
      description: t(locale, 'copilot.workbench.relationships.collect.description'),
      prompt: t(locale, 'copilot.workbench.relationships.collect.prompt', { subject }),
      icon: FileSearch,
    },
  ]
}

function draftCleanupActions(locale: UiLocale): CopilotQuickActionSpec[] {
  return [
    {
      id: 'review_drafts',
      label: t(locale, 'copilot.workbench.draft.review.label'),
      description: t(locale, 'copilot.workbench.draft.review.description'),
      prompt: t(locale, 'copilot.workbench.draft.review.prompt'),
      icon: FileText,
    },
    {
      id: 'normalize_terms',
      label: t(locale, 'copilot.workbench.draft.normalize.label'),
      description: t(locale, 'copilot.workbench.draft.normalize.description'),
      prompt: t(locale, 'copilot.workbench.draft.normalize.prompt'),
      icon: Sparkles,
    },
    {
      id: 'fill_missing_fields',
      label: t(locale, 'copilot.workbench.draft.fill.label'),
      description: t(locale, 'copilot.workbench.draft.fill.description'),
      prompt: t(locale, 'copilot.workbench.draft.fill.prompt'),
      icon: FileSearch,
    },
  ]
}

export function getCopilotWorkbenchMeta(prefill: CopilotPrefill, displayTitle: string, locale: UiLocale = resolveCurrentUiLocale()): CopilotWorkbenchMeta {
  const scenario = getCopilotScenario(prefill)
  const subject = displayTitle || translateUiMessage(locale, 'copilot.session.title.currentContext')

  switch (scenario) {
    case 'whole_book':
      return {
        introTitle: t(locale, 'copilot.workbench.wholeBook.title'),
        composerLabel: t(locale, 'copilot.workbench.wholeBook.composerLabel'),
        composerPlaceholder: t(locale, 'copilot.workbench.wholeBook.composerPlaceholder'),
        quickActions: wholeBookActions(locale),
      }
    case 'relationships':
      return {
        introTitle: t(locale, 'copilot.workbench.relationships.title', { subject }),
        composerLabel: t(locale, 'copilot.workbench.relationships.composerLabel'),
        composerPlaceholder: t(locale, 'copilot.workbench.relationships.composerPlaceholder', { subject }),
        quickActions: relationshipActions(locale, subject),
      }
    case 'draft_cleanup':
      return {
        introTitle: t(locale, 'copilot.workbench.draft.title'),
        composerLabel: t(locale, 'copilot.workbench.draft.composerLabel'),
        composerPlaceholder: t(locale, 'copilot.workbench.draft.composerPlaceholder'),
        quickActions: draftCleanupActions(locale),
      }
    default:
      return {
        introTitle: t(locale, 'copilot.workbench.entity.title', { subject }),
        composerLabel: t(locale, 'copilot.workbench.entity.composerLabel'),
        composerPlaceholder: t(locale, 'copilot.workbench.entity.composerPlaceholder', { subject }),
        quickActions: currentEntityActions(locale, subject),
      }
  }
}

// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { setStudioResultsStageSearchParams } from '@/components/novel-shell/NovelShellRouteState'
import { useAuth } from '@/contexts/AuthContext'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { getLlmApiErrorMessage } from '@/lib/llmErrorMessages'
import { api, ApiError } from '@/services/api'
import type { NovelContextSummary } from '@/types/api'
import {
  useCreateNovelContextSummary,
  useDeleteNovelContextSummary,
  useNovelContextSummaries,
  useRegenerateNovelContextSummary,
  useUpdateNovelContextSummary,
} from './useNovelContextSummaries'

type LengthOption = {
  label: string
  value: string
  disabled: boolean
}

export const LENGTH_OPTIONS: LengthOption[] = [
  { label: '2000', value: '2000', disabled: false },
  { label: '3000', value: '3000', disabled: false },
  { label: '4000', value: '4000', disabled: false },
]

const MIN_CONTEXT_CHAPTERS = 1
const MAX_CONTEXT_CHAPTERS = 5
const DEFAULT_CONTEXT_CHAPTERS = 5
const MAX_CONTEXT_SUMMARY_RANGE_CHAPTERS = 100

export function resolveTargetChars(selected: string): number {
  const opt = LENGTH_OPTIONS.find(option => option.value === selected)
  if (opt) return parseInt(opt.value, 10)
  return 3000
}

function clampInt(raw: string, min: number, max: number): number | undefined {
  const value = parseInt(raw, 10)
  if (Number.isNaN(value)) return undefined
  return Math.max(min, Math.min(max, value))
}

function parseSummaryRange(raw: string): { startChapter: number; endChapter: number } | null {
  const match = raw.trim().match(/^(\d+)\s*[-~至–—]\s*(\d+)$/)
  if (!match) return null
  return {
    startChapter: Number(match[1]),
    endChapter: Number(match[2]),
  }
}

function canUseSummary(summary: NovelContextSummary): boolean {
  return summary.review_status === 'confirmed' && !summary.is_stale
}

export function useContinuationSetupState(novelId: number, chapterNum: number | null) {
  const navigate = useNavigate()
  const { user } = useAuth()
  const { locale, t } = useUiLocale()

  const [instruction, setInstruction] = useState('')
  const [selectedLength, setSelectedLength] = useState('3000')
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [contextChapters, setContextChapters] = useState(String(DEFAULT_CONTEXT_CHAPTERS))
  const [numVersions, setNumVersions] = useState('1')
  const [temperature, setTemperature] = useState('0.8')
  const [prefsLoaded, setPrefsLoaded] = useState(false)
  const [selectedContextSummaryIdsState, setSelectedContextSummaryIds] = useState<number[]>([])
  const [contextSummaryRange, setContextSummaryRange] = useState('')
  const [contextSummaryActionError, setContextSummaryActionError] = useState<string | null>(null)
  const [reviewContextSummaryId, setReviewContextSummaryId] = useState<number | null>(null)

  const contextSummariesQuery = useNovelContextSummaries(novelId)
  const createContextSummary = useCreateNovelContextSummary(novelId)
  const updateContextSummary = useUpdateNovelContextSummary(novelId)
  const regenerateContextSummary = useRegenerateNovelContextSummary(novelId)
  const deleteContextSummary = useDeleteNovelContextSummary(novelId)
  const contextSummaries = useMemo(
    () => contextSummariesQuery.data ?? [],
    [contextSummariesQuery.data],
  )
  const selectedContextSummaryIds = useMemo(() => {
    if (!contextSummariesQuery.isSuccess) return selectedContextSummaryIdsState
    const usableIds = new Set(contextSummaries.filter(canUseSummary).map(summary => summary.id))
    return selectedContextSummaryIdsState.filter(id => usableIds.has(id))
  }, [contextSummaries, contextSummariesQuery.isSuccess, selectedContextSummaryIdsState])
  const reviewContextSummary = useMemo(
    () => contextSummaries.find(summary => summary.id === reviewContextSummaryId) ?? null,
    [contextSummaries, reviewContextSummaryId],
  )

  useEffect(() => {
    if (!contextSummariesQuery.isSuccess) return
    const usableIds = new Set(contextSummaries.filter(canUseSummary).map(summary => summary.id))
    queueMicrotask(() => {
      setSelectedContextSummaryIds(current => {
        const filtered = current.filter(id => usableIds.has(id))
        return filtered.length === current.length ? current : filtered
      })
    })
  }, [contextSummaries, contextSummariesQuery.isSuccess])

  useEffect(() => {
    if (prefsLoaded || !user?.preferences) return
    const preferences = user.preferences as Record<string, unknown>
    queueMicrotask(() => {
      if (preferences.num_versions != null) setNumVersions(String(preferences.num_versions))
      if (preferences.temperature != null) setTemperature(String(preferences.temperature))
      if (preferences.context_chapters != null) {
        const next = clampInt(
          String(preferences.context_chapters),
          MIN_CONTEXT_CHAPTERS,
          MAX_CONTEXT_CHAPTERS,
        )
        setContextChapters(String(next ?? DEFAULT_CONTEXT_CHAPTERS))
      }
      if (preferences.target_chars != null) {
        const targetChars = Number(preferences.target_chars)
        const match = LENGTH_OPTIONS.find(option => Number(option.value) === targetChars)
        if (match) setSelectedLength(match.value)
      }
      setPrefsLoaded(true)
    })
  }, [prefsLoaded, user?.preferences])

  const savePrefs = useCallback(() => {
    const preferences: Record<string, unknown> = {}
    const versions = parseInt(numVersions, 10)
    if (!Number.isNaN(versions)) preferences.num_versions = Math.max(1, Math.min(2, versions))
    const parsedTemperature = parseFloat(temperature)
    if (!Number.isNaN(parsedTemperature)) {
      preferences.temperature = Math.max(0, Math.min(2, parsedTemperature))
    }
    preferences.context_chapters = (
      clampInt(contextChapters, MIN_CONTEXT_CHAPTERS, MAX_CONTEXT_CHAPTERS)
      ?? DEFAULT_CONTEXT_CHAPTERS
    )
    preferences.target_chars = resolveTargetChars(selectedLength)
    api.updatePreferences(preferences).catch(() => {})
  }, [contextChapters, numVersions, selectedLength, temperature])

  const contextSummaryErrorMessage = useCallback((error: unknown): string => {
    if (error instanceof ApiError) {
      const llmMessage = getLlmApiErrorMessage(error, locale)
      if (llmMessage) return llmMessage
      switch (error.code) {
        case 'context_summary_range_too_large':
          return t('continuation.setup.contextSummary.error.rangeTooLarge')
        case 'context_summary_range_invalid':
        case 'context_summary_source_empty':
          return t('continuation.setup.contextSummary.error.rangeInvalid')
        case 'context_summary_source_too_large':
          return t('continuation.setup.contextSummary.error.sourceTooLarge')
        case 'context_summary_stale':
          return t('continuation.setup.contextSummary.error.stale')
        default:
          break
      }
    }
    return t('continuation.setup.contextSummary.error.actionFailed')
  }, [locale, t])

  const handleCreateContextSummary = useCallback(async () => {
    const range = parseSummaryRange(contextSummaryRange)
    if (
      range === null
      || chapterNum === null
      || range.startChapter < 1
      || range.endChapter < range.startChapter
      || range.endChapter > chapterNum
    ) {
      setContextSummaryActionError(t('continuation.setup.contextSummary.error.rangeInvalid'))
      return
    }
    if (range.endChapter - range.startChapter + 1 > MAX_CONTEXT_SUMMARY_RANGE_CHAPTERS) {
      setContextSummaryActionError(t('continuation.setup.contextSummary.error.rangeTooLarge'))
      return
    }

    setContextSummaryActionError(null)
    try {
      const created = await createContextSummary.mutateAsync(range)
      setContextSummaryRange('')
      setReviewContextSummaryId(created.id)
    } catch (error) {
      setContextSummaryActionError(contextSummaryErrorMessage(error))
    }
  }, [chapterNum, contextSummaryErrorMessage, contextSummaryRange, createContextSummary, t])

  const handleSaveContextSummary = useCallback(async (
    summaryId: number,
    content: string,
    reviewStatus: NovelContextSummary['review_status'],
  ) => {
    setContextSummaryActionError(null)
    try {
      const updated = await updateContextSummary.mutateAsync({
        id: summaryId,
        content,
        reviewStatus,
      })
      if (canUseSummary(updated)) {
        setSelectedContextSummaryIds(current => (
          current.includes(updated.id) ? current : [...current, updated.id]
        ))
      } else {
        setSelectedContextSummaryIds(current => current.filter(id => id !== updated.id))
      }
      return updated
    } catch (error) {
      setContextSummaryActionError(contextSummaryErrorMessage(error))
      throw error
    }
  }, [contextSummaryErrorMessage, updateContextSummary])

  const handleRegenerateContextSummary = useCallback(async (summaryId: number) => {
    setContextSummaryActionError(null)
    try {
      const updated = await regenerateContextSummary.mutateAsync(summaryId)
      setSelectedContextSummaryIds(current => current.filter(id => id !== updated.id))
      return updated
    } catch (error) {
      setContextSummaryActionError(contextSummaryErrorMessage(error))
      throw error
    }
  }, [contextSummaryErrorMessage, regenerateContextSummary])

  const handleDeleteContextSummary = useCallback(async (summaryId: number) => {
    setContextSummaryActionError(null)
    try {
      await deleteContextSummary.mutateAsync(summaryId)
      setSelectedContextSummaryIds(current => current.filter(id => id !== summaryId))
      setReviewContextSummaryId(current => (current === summaryId ? null : current))
    } catch {
      setContextSummaryActionError(t('continuation.setup.contextSummary.error.deleteFailed'))
    }
  }, [deleteContextSummary, t])

  const handleGenerate = useCallback(() => {
    if (chapterNum === null) return
    const parsedTemperature = parseFloat(temperature)
    const streamParams = {
      prompt: instruction.trim() || undefined,
      target_chars: resolveTargetChars(selectedLength),
      context_chapters: (
        clampInt(contextChapters, MIN_CONTEXT_CHAPTERS, MAX_CONTEXT_CHAPTERS)
        ?? DEFAULT_CONTEXT_CHAPTERS
      ),
      context_summary_ids: selectedContextSummaryIds,
      num_versions: clampInt(numVersions, 1, 2) || undefined,
      temperature: !Number.isNaN(parsedTemperature)
        ? Math.max(0, Math.min(2, parsedTemperature))
        : undefined,
    }
    savePrefs()
    const nextSearchParams = setStudioResultsStageSearchParams(new URLSearchParams(), chapterNum)
    navigate(`/novel/${novelId}?${nextSearchParams.toString()}`, {
      state: { streamParams, novelId },
    })
  }, [
    chapterNum,
    contextChapters,
    instruction,
    navigate,
    novelId,
    numVersions,
    savePrefs,
    selectedContextSummaryIds,
    selectedLength,
    temperature,
  ])

  return {
    instruction,
    setInstruction,
    selectedLength,
    setSelectedLength,
    advancedOpen,
    setAdvancedOpen,
    contextChapters,
    setContextChapters,
    numVersions,
    setNumVersions,
    temperature,
    setTemperature,
    contextSummaries,
    contextSummariesLoading: contextSummariesQuery.isLoading,
    contextSummaryError: contextSummaryActionError ?? (
      contextSummariesQuery.isError
        ? t('continuation.setup.contextSummary.error.loadFailed')
        : null
    ),
    selectedContextSummaryIds,
    setSelectedContextSummaryIds,
    contextSummaryRange,
    setContextSummaryRange,
    contextSummaryGenerating: createContextSummary.isPending,
    contextSummaryDeletingId: deleteContextSummary.isPending
      ? deleteContextSummary.variables ?? null
      : null,
    contextSummarySaving: updateContextSummary.isPending,
    contextSummaryRegenerating: regenerateContextSummary.isPending,
    reviewContextSummary,
    setReviewContextSummaryId,
    handleCreateContextSummary,
    handleSaveContextSummary,
    handleRegenerateContextSummary,
    handleDeleteContextSummary,
    handleGenerate,
  }
}

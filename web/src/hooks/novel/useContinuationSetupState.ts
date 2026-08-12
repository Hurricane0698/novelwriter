// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { setStudioResultsStageSearchParams } from '@/components/novel-shell/NovelShellRouteState'
import { useAuth } from '@/contexts/AuthContext'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { getLlmApiErrorMessage } from '@/lib/llmErrorMessages'
import { api, ApiError } from '@/services/api'
import {
  useCreateNovelOutline,
  useDeleteNovelOutline,
  useNovelOutlines,
} from './useNovelOutlines'

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
const MAX_OUTLINE_RANGE_CHAPTERS = 100

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

function parseOutlineRange(raw: string): { startChapter: number; endChapter: number } | null {
  const match = raw.trim().match(/^(\d+)\s*[-~至–—]\s*(\d+)$/)
  if (!match) return null
  return {
    startChapter: Number(match[1]),
    endChapter: Number(match[2]),
  }
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
  const [selectedOutlineIdsState, setSelectedOutlineIds] = useState<number[]>([])
  const [outlineRange, setOutlineRange] = useState('')
  const [outlineActionError, setOutlineActionError] = useState<string | null>(null)

  const outlinesQuery = useNovelOutlines(novelId)
  const createOutline = useCreateNovelOutline(novelId)
  const deleteOutline = useDeleteNovelOutline(novelId)
  const outlines = useMemo(() => outlinesQuery.data ?? [], [outlinesQuery.data])
  const selectedOutlineIds = useMemo(() => {
    if (!outlinesQuery.isSuccess) return selectedOutlineIdsState
    const availableIds = new Set(outlines.map(outline => outline.id))
    return selectedOutlineIdsState.filter(id => availableIds.has(id))
  }, [outlines, outlinesQuery.isSuccess, selectedOutlineIdsState])

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

  const outlineErrorMessage = useCallback((error: unknown): string => {
    if (error instanceof ApiError) {
      const llmMessage = getLlmApiErrorMessage(error, locale)
      if (llmMessage) return llmMessage
      switch (error.code) {
        case 'outline_range_too_large':
          return t('continuation.setup.outline.error.rangeTooLarge')
        case 'outline_range_invalid':
        case 'outline_source_empty':
          return t('continuation.setup.outline.error.rangeInvalid')
        case 'outline_source_too_large':
          return t('continuation.setup.outline.error.sourceTooLarge')
        default:
          break
      }
    }
    return t('continuation.setup.outline.error.generateFailed')
  }, [locale, t])

  const handleCreateOutline = useCallback(async () => {
    const range = parseOutlineRange(outlineRange)
    if (
      range === null
      || chapterNum === null
      || range.startChapter < 1
      || range.endChapter < range.startChapter
      || range.endChapter > chapterNum
    ) {
      setOutlineActionError(t('continuation.setup.outline.error.rangeInvalid'))
      return
    }
    if (range.endChapter - range.startChapter + 1 > MAX_OUTLINE_RANGE_CHAPTERS) {
      setOutlineActionError(t('continuation.setup.outline.error.rangeTooLarge'))
      return
    }

    setOutlineActionError(null)
    try {
      const created = await createOutline.mutateAsync(range)
      setSelectedOutlineIds(current => (
        current.includes(created.id) ? current : [...current, created.id]
      ))
      setOutlineRange('')
    } catch (error) {
      setOutlineActionError(outlineErrorMessage(error))
    }
  }, [chapterNum, createOutline, outlineErrorMessage, outlineRange, t])

  const handleDeleteOutline = useCallback(async (outlineId: number) => {
    setOutlineActionError(null)
    try {
      await deleteOutline.mutateAsync(outlineId)
      setSelectedOutlineIds(current => current.filter(id => id !== outlineId))
    } catch {
      setOutlineActionError(t('continuation.setup.outline.error.deleteFailed'))
    }
  }, [deleteOutline, t])

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
      outline_ids: selectedOutlineIds,
      num_versions: clampInt(numVersions, 1, 2) || undefined,
      temperature: !Number.isNaN(parsedTemperature)
        ? Math.max(0, Math.min(2, parsedTemperature))
        : undefined,
    }
    savePrefs()
    const nextSearchParams = setStudioResultsStageSearchParams(
      new URLSearchParams(),
      chapterNum,
    )
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
    selectedLength,
    selectedOutlineIds,
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
    outlines,
    outlinesLoading: outlinesQuery.isLoading,
    outlineError: outlineActionError ?? (
      outlinesQuery.isError ? t('continuation.setup.outline.error.loadFailed') : null
    ),
    selectedOutlineIds,
    setSelectedOutlineIds,
    outlineRange,
    setOutlineRange,
    outlineGenerating: createOutline.isPending,
    outlineDeletingId: deleteOutline.isPending ? deleteOutline.variables ?? null : null,
    handleCreateOutline,
    handleDeleteOutline,
    handleGenerate,
  }
}

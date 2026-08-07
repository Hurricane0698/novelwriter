// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'
import { api } from '@/services/api'
import { setStudioResultsStageSearchParams } from '@/components/novel-shell/NovelShellRouteState'
import type { NovelOutline } from '@/types/api'

// ── Constants ──

const MIN_CONTEXT_CHAPTERS = 1
const MAX_CONTEXT_CHAPTERS = 10000
const DEFAULT_CONTEXT_CHAPTERS = 5

// ── Helpers ──

export function resolveTargetChars(selected: string): number {
  const value = parseInt(selected, 10)
  if (Number.isFinite(value)) return Math.max(1000, Math.min(20000, value))
  return 3000
}

function clampInt(raw: string, min: number, max: number): number | undefined {
  const n = parseInt(raw, 10)
  if (Number.isNaN(n)) return undefined
  return Math.max(min, Math.min(max, n))
}

// ── Hook ──

/**
 * Shared continuation-setup form state.
 *
 * Hoisted at the page level so state survives stage-component mount/unmount
 * when the user switches between chapter and write stages.
 *
 * Keyed on `novelId` — a novel switch resets state naturally because the whole
 * `NovelStudioPage` remounts on `:novelId` change.
 */
export function useContinuationSetupState(novelId: number, chapterNum: number | null, totalChapters = 0) {
  const navigate = useNavigate()
  const { user } = useAuth()

  const [instruction, setInstruction] = useState('')
  const [selectedLength, setSelectedLength] = useState('3000')
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const contextLimit = Math.max(1, totalChapters || DEFAULT_CONTEXT_CHAPTERS)
  const [contextChapters, setContextChapters] = useState(String(Math.min(DEFAULT_CONTEXT_CHAPTERS, contextLimit)))
  const [numVersions, setNumVersions] = useState('1')
  const [temperature, setTemperature] = useState('0.8')
  const [outlines, setOutlines] = useState<NovelOutline[]>([])
  const [selectedOutlineIds, setSelectedOutlineIds] = useState<number[]>([])
  const [outlineRange, setOutlineRange] = useState('')
  const [outlineGenerating, setOutlineGenerating] = useState(false)
  const [prefsLoaded, setPrefsLoaded] = useState(false)

  useEffect(() => {
    api.listOutlines(novelId).then(setOutlines).catch(() => setOutlines([]))
  }, [novelId])

  // Load user preferences as defaults (once)
  useEffect(() => {
    if (prefsLoaded || !user?.preferences) return
    const p = user.preferences as Record<string, unknown>
    queueMicrotask(() => {
      if (p.num_versions != null) setNumVersions(String(p.num_versions))
      if (p.temperature != null) setTemperature(String(p.temperature))
      if (p.context_chapters != null) {
        const next = clampInt(String(p.context_chapters), MIN_CONTEXT_CHAPTERS, Math.min(MAX_CONTEXT_CHAPTERS, contextLimit))
        setContextChapters(String(next ?? DEFAULT_CONTEXT_CHAPTERS))
      }
      if (p.target_chars != null) {
        const tc = Number(p.target_chars)
        if (Number.isFinite(tc)) setSelectedLength(String(Math.max(1000, Math.min(20000, tc))))
      }
      setPrefsLoaded(true)
    })
  }, [user?.preferences, prefsLoaded])

  // Save preferences to server
  const savePrefs = useCallback(() => {
    const prefs: Record<string, unknown> = {}
    const nv = parseInt(numVersions, 10)
    if (!Number.isNaN(nv)) prefs.num_versions = Math.max(1, Math.min(2, nv))
    const temp = parseFloat(temperature)
    if (!Number.isNaN(temp)) prefs.temperature = Math.max(0, Math.min(2, temp))
    prefs.context_chapters = clampInt(contextChapters, MIN_CONTEXT_CHAPTERS, Math.min(MAX_CONTEXT_CHAPTERS, contextLimit)) ?? contextLimit
    prefs.target_chars = resolveTargetChars(selectedLength)
    api.updatePreferences(prefs).catch(() => {})
  }, [numVersions, temperature, contextChapters, selectedLength])

  const handleGenerate = useCallback(() => {
    if (chapterNum === null) return
    const parsedTemp = parseFloat(temperature)
    const streamParams = {
      prompt: instruction.trim() || undefined,
      target_chars: resolveTargetChars(selectedLength),
      context_chapters: clampInt(contextChapters, MIN_CONTEXT_CHAPTERS, Math.min(MAX_CONTEXT_CHAPTERS, contextLimit)) ?? contextLimit,
      outline_ids: selectedOutlineIds,
      num_versions: clampInt(numVersions, 1, 2) || undefined,
      temperature: !Number.isNaN(parsedTemp) ? Math.max(0, Math.min(2, parsedTemp)) : undefined,
    }
    savePrefs()
    const nextSearchParams = setStudioResultsStageSearchParams(new URLSearchParams(), chapterNum)
    navigate(`/novel/${novelId}?${nextSearchParams.toString()}`, {
      state: { streamParams, novelId },
    })
  }, [chapterNum, contextChapters, instruction, navigate, novelId, numVersions, savePrefs, selectedLength, selectedOutlineIds, temperature])

  const handleCreateOutline = useCallback(async () => {
    const match = outlineRange.trim().match(/^(\d+)\s*[-~至]\s*(\d+)$/)
    if (!match) return
    const start = Number(match[1])
    const end = Number(match[2])
    if (start < 1 || end < start || end > contextLimit) return
    setOutlineGenerating(true)
    try {
      const created = await api.createOutline(novelId, start, end)
      setOutlines((current) => [...current, created].sort((a, b) => a.start_chapter - b.start_chapter || a.end_chapter - b.end_chapter))
      setSelectedOutlineIds((current) => current.includes(created.id) ? current : [...current, created.id])
      setOutlineRange('')
    } finally {
      setOutlineGenerating(false)
    }
  }, [contextLimit, novelId, outlineRange])

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
    selectedOutlineIds,
    setSelectedOutlineIds,
    outlineRange,
    setOutlineRange,
    outlineGenerating,
    handleCreateOutline,
    handleGenerate,
  }
}

import { useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  setAtlasStudioOriginSearchParams, setNovelShellArtifactPanelSearchParams,
  setResultsProvenanceSearchParams, setStudioChapterSearchParams,
  setStudioEntityStageSearchParams, setStudioRelationshipStageSearchParams,
  setStudioResultsStageSearchParams, setStudioSystemStageSearchParams,
  setStudioReviewKindSearchParams, setStudioStageSearchParams,
} from '@/components/novel-shell/NovelShellRouteState'
import type { useStudioArtifactState } from '@/hooks/novel/useStudioArtifactState'
import type { useStudioChapterEditor } from '@/hooks/novel/useStudioChapterEditor'
import type { CopilotReviewKind } from '@/types/copilot'

interface WorldStageOptions {
  chapterNumber?: number | null
  replace?: boolean
}

type ArtifactNavigationContext = Pick<ReturnType<typeof useStudioArtifactState>,
  'activeArtifactPanelState' | 'applyActiveArtifactContextSearchParams' |
  'atlasStudioOrigin' | 'effectiveResultsProvenance' | 'resultsNavigationState'>
type EditorNavigationContext = Pick<ReturnType<typeof useStudioChapterEditor>,
  'editMode' | 'setEditMode' | 'saveCurrentEditorNow'>

/** Preserve artifact and handoff context consistently across Studio stage changes. */
export function useStudioNavigation({
  novelId, activeChapterNum, artifacts, editor, applyWorldEntryRouteSearchParams, warmAtlasAssist,
}: {
  novelId: number
  activeChapterNum: number | null
  artifacts: ArtifactNavigationContext
  editor: EditorNavigationContext
  applyWorldEntryRouteSearchParams: (params: URLSearchParams) => URLSearchParams
  warmAtlasAssist: () => void
}) {
  const navigate = useNavigate()
  const {
    activeArtifactPanelState, applyActiveArtifactContextSearchParams,
    atlasStudioOrigin, effectiveResultsProvenance, resultsNavigationState,
  } = artifacts
  const { editMode, setEditMode, saveCurrentEditorNow } = editor

  const navigateToChapterStage = useCallback((chapterNumber: number | null = null) => {
    let nextSearchParams = setStudioChapterSearchParams(new URLSearchParams(), chapterNumber)
    nextSearchParams = setResultsProvenanceSearchParams(nextSearchParams, null)
    nextSearchParams = setNovelShellArtifactPanelSearchParams(nextSearchParams, null)
    nextSearchParams = applyWorldEntryRouteSearchParams(nextSearchParams)
    const nextSearch = nextSearchParams.toString()
    navigate(nextSearch ? `/novel/${novelId}?${nextSearch}` : `/novel/${novelId}`, { replace: true, state: null })
  }, [applyWorldEntryRouteSearchParams, navigate, novelId])
  const navigateToResultsStage = useCallback((options?: { replace?: boolean }) => {
    let nextSearchParams = setStudioResultsStageSearchParams(new URLSearchParams(), activeChapterNum)
    nextSearchParams = setResultsProvenanceSearchParams(nextSearchParams, null)
    if (effectiveResultsProvenance) {
      nextSearchParams.set('continuations', effectiveResultsProvenance.continuations)
      if (effectiveResultsProvenance.totalVariants !== null) {
        nextSearchParams.set('total_variants', String(effectiveResultsProvenance.totalVariants))
      } else {
        nextSearchParams.delete('total_variants')
      }
    } else {
      nextSearchParams.delete('continuations')
      nextSearchParams.delete('total_variants')
    }
    nextSearchParams = setNovelShellArtifactPanelSearchParams(nextSearchParams, activeArtifactPanelState)
    nextSearchParams = applyWorldEntryRouteSearchParams(nextSearchParams)
    navigate(`/novel/${novelId}?${nextSearchParams.toString()}`, {
      replace: options?.replace ?? false,
      state: resultsNavigationState,
    })
  }, [activeArtifactPanelState, activeChapterNum, applyWorldEntryRouteSearchParams, effectiveResultsProvenance, navigate, novelId, resultsNavigationState])
  const navigateToWriteStage = useCallback(() => {
    let nextSearchParams = setStudioStageSearchParams(new URLSearchParams(), 'write')
    nextSearchParams = setResultsProvenanceSearchParams(nextSearchParams, null)
    nextSearchParams = setNovelShellArtifactPanelSearchParams(nextSearchParams, null)
    nextSearchParams = applyWorldEntryRouteSearchParams(nextSearchParams)
    navigate(`/novel/${novelId}?${nextSearchParams.toString()}`, { replace: true, state: null })
  }, [applyWorldEntryRouteSearchParams, navigate, novelId])
  const navigateToWorldStage = useCallback((
    selectStage: (params: URLSearchParams) => URLSearchParams,
    options?: WorldStageOptions,
  ) => {
    let next = setStudioChapterSearchParams(new URLSearchParams(), options?.chapterNumber ?? activeChapterNum)
    next = selectStage(next)
    next = applyActiveArtifactContextSearchParams(next)
    next = applyWorldEntryRouteSearchParams(next)
    navigate(`/novel/${novelId}?${next.toString()}`, {
      replace: options?.replace ?? false, state: resultsNavigationState,
    })
  }, [activeChapterNum, applyActiveArtifactContextSearchParams, applyWorldEntryRouteSearchParams, navigate, novelId, resultsNavigationState])

  const navigateToEntityStage = useCallback((id: number | null, options?: WorldStageOptions) => (
    navigateToWorldStage(params => setStudioEntityStageSearchParams(params, id), options)
  ), [navigateToWorldStage])
  const navigateToRelationshipStage = useCallback((id: number | null, options?: WorldStageOptions) => (
    navigateToWorldStage(params => setStudioRelationshipStageSearchParams(params, id), options)
  ), [navigateToWorldStage])
  const navigateToSystemStage = useCallback((id: number | null, options?: WorldStageOptions) => (
    navigateToWorldStage(params => setStudioSystemStageSearchParams(params, id), options)
  ), [navigateToWorldStage])
  const navigateToReviewStage = useCallback((kind: CopilotReviewKind, options?: WorldStageOptions) => (
    navigateToWorldStage(params => setStudioReviewKindSearchParams(params, kind), options)
  ), [navigateToWorldStage])

  const navigateToAtlas = useCallback((params?: URLSearchParams) => {
    warmAtlasAssist()

    const commitNavigation = () => {
      let nextParams = applyWorldEntryRouteSearchParams(params ?? new URLSearchParams())
      nextParams = setAtlasStudioOriginSearchParams(nextParams, atlasStudioOrigin)
      const nextSearch = nextParams.toString()
      navigate(nextSearch ? `/world/${novelId}?${nextSearch}` : `/world/${novelId}`)
    }

    if (editMode) {
      void saveCurrentEditorNow()
        .then((isCurrentSave) => {
          if (!isCurrentSave) return
          setEditMode(false)
          commitNavigation()
        })
        .catch(() => {
          // Save failed — stay on the current Studio stage so the user can retry.
        })
      return
    }

    commitNavigation()
  }, [applyWorldEntryRouteSearchParams, atlasStudioOrigin, editMode, navigate, novelId, saveCurrentEditorNow, setEditMode, warmAtlasAssist])
  return {
    navigateToChapterStage, navigateToResultsStage, navigateToWriteStage,
    navigateToEntityStage, navigateToReviewStage, navigateToRelationshipStage,
    navigateToSystemStage, navigateToAtlas,
  }
}

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { ChapterEditorSaveErrorCode } from '@/components/detail/ChapterEditor'
import { useDebouncedAutoSave } from '@/hooks/useDebouncedAutoSave'
import { isMarkdownChapterBodyInvalidError } from '@/lib/chapterMutationError'

const AUTO_SAVE_DELAY = 3000

/** Own editor state and reject completions from a previous chapter or navigation. */
export function useStudioChapterEditor({
  novelId, chapterNumber: activeChapterNum, locationKey, chapterContent, saveChapter,
}: {
  novelId: number
  chapterNumber: number | null
  locationKey: string
  chapterContent: string
  saveChapter: (update: { content: string }) => Promise<unknown>
}) {
  const [editMode, setEditMode] = useState(false)
  const [editorContent, setEditorContent] = useState('')
  const [editorSaveError, setEditorSaveError] = useState<{
    novelId: number
    chapterNumber: number
    locationKey: string
    saveGeneration: number
    code: ChapterEditorSaveErrorCode
  } | null>(null)
  const editorSaveGenerationRef = useRef(0)
  const editorSaveContextRef = useRef({
    novelId,
    chapterNumber: activeChapterNum,
    locationKey,
  })
  useLayoutEffect(() => {
    const nextContext = {
      novelId,
      chapterNumber: activeChapterNum,
      locationKey,
    }
    if (
      editorSaveContextRef.current.novelId !== nextContext.novelId
      || editorSaveContextRef.current.chapterNumber !== nextContext.chapterNumber
      || editorSaveContextRef.current.locationKey !== nextContext.locationKey
    ) {
      editorSaveContextRef.current = nextContext
      editorSaveGenerationRef.current += 1
    }
  }, [activeChapterNum, locationKey, novelId])
  useLayoutEffect(() => () => {
    // A completed save must not navigate back into an editor that was closed.
    editorSaveGenerationRef.current += 1
  }, [])
  const editorSaveErrorCode = (
    editorSaveError?.novelId === novelId
    && editorSaveError.chapterNumber === activeChapterNum
    && editorSaveError.locationKey === locationKey
  )
    ? editorSaveError.code
    : null
  const {
    status: autoSaveStatus,
    schedule: scheduleAutoSave,
    saveNow: saveNowAutoSave,
    cancel: cancelAutoSave,
  } = useDebouncedAutoSave<string>({
    delayMs: AUTO_SAVE_DELAY,
    save: async (content) => {
      const savingNovelId = novelId
      const savingChapterNumber = activeChapterNum
      const savingLocationKey = locationKey
      if (savingChapterNumber === null) return
      const saveGeneration = editorSaveGenerationRef.current + 1
      editorSaveGenerationRef.current = saveGeneration
      setEditorSaveError(null)
      const isCurrentSave = () => (
        editorSaveGenerationRef.current === saveGeneration
        && editorSaveContextRef.current.novelId === savingNovelId
        && editorSaveContextRef.current.chapterNumber === savingChapterNumber
        && editorSaveContextRef.current.locationKey === savingLocationKey
      )
      try {
        await saveChapter({ content })
        if (isCurrentSave()) {
          setEditorSaveError(null)
        }
      } catch (error) {
        if (isCurrentSave()) {
          setEditorSaveError({
            novelId: savingNovelId,
            chapterNumber: savingChapterNumber,
            locationKey: savingLocationKey,
            saveGeneration,
            code: isMarkdownChapterBodyInvalidError(error) ? error.code : 'chapter_save_failed',
          })
        }
        throw error
      }
    },
  })
  const saveCurrentEditorNow = useCallback(async (): Promise<boolean> => {
    const targetNovelId = novelId
    const targetChapterNumber = activeChapterNum
    const targetLocationKey = locationKey
    if (targetChapterNumber === null) return false
    const savePromise = saveNowAutoSave(editorContent)
    // useDebouncedAutoSave invokes the current save callback synchronously before
    // yielding, so this is the generation reserved for this manual save.
    const saveGeneration = editorSaveGenerationRef.current
    await savePromise
    return (
      editorSaveGenerationRef.current === saveGeneration
      && editorSaveContextRef.current.novelId === targetNovelId
      && editorSaveContextRef.current.chapterNumber === targetChapterNumber
      && editorSaveContextRef.current.locationKey === targetLocationKey
    )
  }, [activeChapterNum, editorContent, locationKey, novelId, saveNowAutoSave])

  useEffect(() => {
    // Prevent autosave timers from leaking across chapter switches.
    cancelAutoSave()
  }, [activeChapterNum, cancelAutoSave, locationKey, novelId])

  const handleEditorChange = (val: string) => {
    editorSaveGenerationRef.current += 1
    setEditorSaveError(null)
    setEditorContent(val)
    scheduleAutoSave(val)
  }
  const handleSave = () => {
    if (activeChapterNum === null) return
    void saveCurrentEditorNow()
      .then((isCurrentSave) => {
        if (isCurrentSave) setEditMode(false)
      })
      .catch(() => {
        // Keep the editor open; user can retry.
      })
  }
  const resetEditor = useCallback((content = '', editing = false) => {
    editorSaveGenerationRef.current += 1
    cancelAutoSave()
    setEditorContent(content)
    setEditorSaveError(null)
    setEditMode(editing)
  }, [cancelAutoSave])

  const handleCancelEdit = () => resetEditor(chapterContent)

  const toggleEdit = () => {
    if (activeChapterNum === null) return
    resetEditor(editMode ? editorContent : chapterContent, !editMode)
  }

  return {
    editMode, setEditMode, editorContent, editorSaveErrorCode, autoSaveStatus,
    handleEditorChange, handleSave, handleCancelEdit, saveCurrentEditorNow,
    resetEditor, toggleEdit,
  }
}

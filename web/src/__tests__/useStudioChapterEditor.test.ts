import { act, renderHook } from '@testing-library/react'
import { expect, it } from 'vitest'
import { useStudioChapterEditor } from '@/hooks/novel/useStudioChapterEditor'

it('does not authorize navigation when a manual save finishes after the editor unmounts', async () => {
  let finishSave!: () => void
  const pendingSave = new Promise<void>(resolve => { finishSave = resolve })
  const { result, unmount } = renderHook(() => useStudioChapterEditor({
    novelId: 7, chapterNumber: 1, locationKey: 'studio', chapterContent: '正文',
    saveChapter: () => pendingSave,
  }))

  let canNavigate!: Promise<boolean>
  act(() => { canNavigate = result.current.saveCurrentEditorNow() })
  unmount()
  await act(async () => { finishSave(); await pendingSave })

  expect(await canNavigate).toBe(false)
})

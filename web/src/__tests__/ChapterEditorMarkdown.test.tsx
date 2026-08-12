import { createRef, useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import '@/lib/uiMessagePacks/novel'
import { UiLocaleProvider } from '@/contexts/UiLocaleContext'
import {
  ChapterEditor,
  type ChapterEditorSaveErrorCode,
} from '@/components/detail/ChapterEditor'
import { MARKDOWN_CHAPTER_BODY_INVALID } from '@/lib/chapterMutationError'

function EditorHarness({
  onSave,
  saveErrorCode = null,
}: {
  onSave: () => void
  saveErrorCode?: ChapterEditorSaveErrorCode | null
}) {
  const [value, setValue] = useState('初始正文')
  return (
    <UiLocaleProvider>
      <ChapterEditor
        textareaRef={createRef<HTMLTextAreaElement>()}
        value={value}
        onChange={setValue}
        onSelectionChange={() => undefined}
        cursorInfo={{ para: 1, col: 1 }}
        autoSaveStatus="unsaved"
        saveErrorCode={saveErrorCode}
        onUndo={() => undefined}
        onRedo={() => undefined}
        onCancel={() => undefined}
        onSave={onSave}
        contentFormat="markdown"
        warningTerms={[{ code: 'unknown_term', term: '新内容' }]}
        previewAnnotations={[{
          id: 'warning',
          term: '新内容',
          className: 'nw-drift-highlight',
        }]}
      />
    </UiLocaleProvider>
  )
}

describe('ChapterEditor Markdown mode', () => {
  it('previews the unsaved source buffer without saving on tab changes', async () => {
    const onSave = vi.fn()
    render(<EditorHarness onSave={onSave} />)

    const textarea = screen.getByRole('textbox')
    await userEvent.clear(textarea)
    await userEvent.type(textarea, '**新内容**')
    await userEvent.click(screen.getByRole('button', { name: '预览' }))

    expect(screen.getByTestId('markdown-editor-preview')).toHaveTextContent('新内容')
    expect(document.querySelector('strong')).toHaveTextContent('新内容')
    expect(document.querySelector('.nw-drift-highlight')).toHaveTextContent('新内容')
    expect(onSave).not.toHaveBeenCalled()

    await userEvent.click(screen.getByRole('button', { name: '源码' }))
    expect(screen.getByRole('textbox')).toHaveValue('**新内容**')
  })

  it('renders structured Markdown validation without exposing diagnostic text', () => {
    render(
      <EditorHarness
        onSave={vi.fn()}
        saveErrorCode={MARKDOWN_CHAPTER_BODY_INVALID}
      />,
    )

    expect(screen.getByRole('alert')).toHaveTextContent(
      '无法保存：Markdown 章节正文结构不合法或超过支持的复杂度。请移除一级或二级标题，闭合代码围栏和 HTML 块，并精简异常密集的块结构。',
    )
    expect(screen.queryByText(/traceback|HTTP 422/i)).not.toBeInTheDocument()
  })
})

import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { UiLocaleProvider } from '@/contexts/UiLocaleContext'
import '@/lib/uiMessagePacks/copilot'
import { NovelCopilotComposer } from '@/components/novel-copilot/NovelCopilotComposer'

function composer(sessionId: string, onSubmit: (text: string) => void) {
  return <UiLocaleProvider><NovelCopilotComposer sessionId={sessionId} onSubmit={onSubmit} label="问题" /></UiLocaleProvider>
}

describe('NovelCopilotComposer', () => {
  it('keeps an independent unfinished question for each session', () => {
    const onSubmit = vi.fn()
    const { rerender } = render(composer('whole-book', onSubmit))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: '查找白骨夫人的出处' } })
    rerender(composer('entity', onSubmit))
    expect(screen.getByRole('textbox')).toHaveValue('')
    fireEvent.change(screen.getByRole('textbox'), { target: { value: '补充唐僧的约束' } })
    rerender(composer('whole-book', onSubmit))
    expect(screen.getByRole('textbox')).toHaveValue('查找白骨夫人的出处')
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('does not send when Enter confirms Chinese input, and sends after composition ends', () => {
    const onSubmit = vi.fn()
    render(composer('whole-book', onSubmit))
    const input = screen.getByRole('textbox')
    fireEvent.change(input, { target: { value: '孙悟空' } })
    fireEvent.keyDown(input, { key: 'Enter', isComposing: true, keyCode: 229 })
    expect(onSubmit).not.toHaveBeenCalled()
    expect(input).toHaveValue('孙悟空')
    fireEvent.keyDown(input, { key: 'Enter', shiftKey: true })
    expect(onSubmit).not.toHaveBeenCalled()
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onSubmit).toHaveBeenCalledWith('孙悟空')
    expect(input).toHaveValue('')
  })
})

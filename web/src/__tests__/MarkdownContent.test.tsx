import type { ReactNode } from 'react'
import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { UiLocaleProvider } from '@/contexts/UiLocaleContext'
import { MarkdownContent } from '@/components/ui/markdown-content'

function renderWithProvider(element: ReactNode) {
  return render(<UiLocaleProvider>{element}</UiLocaleProvider>)
}

describe('MarkdownContent', () => {
  it('renders the CommonMark authoring baseline', () => {
    const { container } = renderWithProvider(
      <MarkdownContent
        content={'### 小节\n\n**粗体** 和 *斜体*\n\n- 列表\n\n> 引用\n\n---\n\n`code`'}
      />,
    )

    expect(screen.getByRole('heading', { name: '小节' })).toBeVisible()
    expect(screen.getByText('粗体').tagName).toBe('STRONG')
    expect(screen.getByText('斜体').tagName).toBe('EM')
    expect(screen.getByRole('list')).toBeVisible()
    expect(container.querySelector('blockquote')).not.toBeNull()
    expect(container.querySelector('hr')).not.toBeNull()
    expect(screen.getByText('code').tagName).toBe('CODE')
  })

  it('does not execute raw HTML, load images, or link dangerous URLs', () => {
    const { container } = renderWithProvider(
      <MarkdownContent
        content={'<script>window.hacked = true</script>\n\n<img src="https://tracker.invalid/raw.png">\n\n![remote](https://tracker.invalid/image.png)\n\n[bad](javascript:alert(1))\n\n[safe](https://example.com)'}
      />,
    )

    expect(container.querySelector('script')).toBeNull()
    expect(container.querySelector('img')).toBeNull()
    expect(screen.getByText('bad').closest('a')).toBeNull()
    expect(screen.getByRole('link', { name: 'safe' })).toHaveAttribute('href', 'https://example.com')
  })

  it('keeps postcheck annotations inside Markdown text nodes', () => {
    const annotations = [{
      id: 'warning',
      term: '未知名词',
      className: 'nw-drift-highlight',
      renderPopover: () => <span>警告详情</span>,
    }]
    const { container, rerender } = renderWithProvider(
      <MarkdownContent
        content="**未知名词** 再次出现"
        annotations={annotations}
      />,
    )

    expect(container.querySelector('.nw-drift-highlight')).toHaveTextContent('未知名词')
    fireEvent.click(screen.getByRole('button', { name: '未知名词' }))
    expect(screen.getByText('警告详情')).toBeVisible()
    rerender(<UiLocaleProvider><MarkdownContent content="**未知名词** 再次出现，更多正文" annotations={annotations} /></UiLocaleProvider>)
    expect(screen.getByText('警告详情')).toBeVisible()

    rerender(<UiLocaleProvider><MarkdownContent content="**未知名词** 再次出现，更多正文" annotations={[{ ...annotations[0], term: '更多正文' }]} /></UiLocaleProvider>)
    expect(container.querySelectorAll('.nw-drift-highlight')).toHaveLength(1)
    expect(container.querySelector('.nw-drift-highlight')).toHaveTextContent('更多正文')
  })

  it('updates streamed text while preserving existing paragraph DOM nodes', () => {
    const content = Array.from({ length: 100 }, (_, index) => `段落 ${index}`).join('\n\n')
    const { container, rerender } = renderWithProvider(<MarkdownContent content={content} />)
    const paragraphs = Array.from(container.querySelectorAll('p'))
    rerender(<UiLocaleProvider><MarkdownContent content={`${content} 追加文本`} /></UiLocaleProvider>)
    const updatedParagraphs = Array.from(container.querySelectorAll('p'))
    expect(updatedParagraphs).toHaveLength(100)
    expect(updatedParagraphs.filter((node, index) => node !== paragraphs[index])).toHaveLength(0)
    expect(updatedParagraphs[99]).toHaveTextContent('段落 99 追加文本')
  })
})

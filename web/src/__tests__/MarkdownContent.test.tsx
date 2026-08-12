import type { ReactNode } from 'react'
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
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
    const { container } = renderWithProvider(
      <MarkdownContent
        content="**未知名词** 再次出现"
        annotations={[{
          id: 'warning',
          term: '未知名词',
          className: 'nw-drift-highlight',
        }]}
      />,
    )

    expect(container.querySelector('.nw-drift-highlight')).toHaveTextContent('未知名词')
  })
})

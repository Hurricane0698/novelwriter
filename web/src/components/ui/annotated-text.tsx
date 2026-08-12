import { useState, type ReactNode } from 'react'
import * as Popover from '@radix-ui/react-popover'
import { cn } from '@/lib/utils'

export interface TextAnnotation {
  id: string
  term: string
  className?: string
  renderPopover?: (props: { onClose: () => void }) => ReactNode
}
function AnnotatedSpan({
  annotation,
  matchedText,
}: {
  annotation: TextAnnotation
  matchedText: string
}) {
  const [open, setOpen] = useState(false)

  if (!annotation.renderPopover) {
    return <span className={cn('rounded-sm', annotation.className)}>{matchedText}</span>
  }

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <span
          className={cn('cursor-default rounded-sm', annotation.className)}
          role="button"
          tabIndex={0}
        >
          {matchedText}
        </span>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          side="top"
          sideOffset={6}
          align="center"
          className="z-50 animate-in fade-in-0 zoom-in-95 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95"
          onOpenAutoFocus={(event) => event.preventDefault()}
        >
          {annotation.renderPopover({ onClose: () => setOpen(false) })}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}

export function AnnotatedText({
  text,
  annotations,
}: {
  text: string
  annotations: TextAnnotation[]
}) {
  if (annotations.length === 0) return <>{text}</>

  const matches: { start: number; end: number; annotation: TextAnnotation }[] = []
  for (const annotation of annotations) {
    if (!annotation.term) continue
    let searchFrom = 0
    while (searchFrom < text.length) {
      const start = text.indexOf(annotation.term, searchFrom)
      if (start === -1) break
      matches.push({
        start,
        end: start + annotation.term.length,
        annotation,
      })
      searchFrom = start + 1
    }
  }

  matches.sort((a, b) => a.start - b.start || (b.end - b.start) - (a.end - a.start))

  const selected: typeof matches = []
  let cursor = 0
  for (const match of matches) {
    if (match.start >= cursor) {
      selected.push(match)
      cursor = match.end
    }
  }
  if (selected.length === 0) return <>{text}</>

  const segments: ReactNode[] = []
  let position = 0
  selected.forEach((match) => {
    if (match.start > position) segments.push(text.slice(position, match.start))
    segments.push(
      <AnnotatedSpan
        key={`${match.annotation.id}-${match.start}`}
        annotation={match.annotation}
        matchedText={text.slice(match.start, match.end)}
      />,
    )
    position = match.end
  })
  if (position < text.length) segments.push(text.slice(position))

  return <>{segments}</>
}

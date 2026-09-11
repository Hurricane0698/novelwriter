export const copilotDrawerShellClassName =
  'border-l border-[var(--nw-copilot-border)] bg-background'

export const copilotPanelClassName =
  'border border-[var(--nw-copilot-border)] bg-[var(--nw-copilot-panel-bg)]'

export const copilotPanelStrongClassName =
  'border border-[var(--nw-copilot-border-strong)] bg-[var(--nw-copilot-panel-strong-bg)]'

export const copilotPanelMutedClassName =
  'border border-[var(--nw-copilot-border)] bg-[var(--nw-copilot-panel-muted-bg)]'

export const copilotPillClassName =
  'bg-[var(--nw-copilot-pill-bg)]'

export const copilotPillInteractiveClassName =
  'border border-transparent bg-[var(--nw-copilot-pill-bg)] transition-colors duration-200 hover:border-[var(--nw-copilot-border)] hover:bg-[var(--nw-copilot-pill-hover-bg)]'

export function getCopilotResearchStatusClassName(tone: 'warning' | 'success' | 'muted') {
  if (tone === 'warning') return 'text-[hsl(var(--color-warning))]'
  if (tone === 'success') return 'text-foreground/82'
  return 'text-muted-foreground/72'
}

export const copilotQuoteClassName =
  'border border-[var(--nw-copilot-border)] bg-[var(--nw-copilot-quote-bg)]'

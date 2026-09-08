import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { StudioOnboardingStage } from '@/components/studio/stages/StudioOnboardingStage'

vi.mock('@/components/detail/EmptyWorldOnboarding', () => ({
  EmptyWorldOnboarding: ({
    onGenerate,
    onBootstrap,
    onDismiss,
    bootstrapPending,
    bootstrapError,
  }: {
    onGenerate: () => void
    onBootstrap: () => void
    onDismiss: () => void
    bootstrapPending: boolean
    bootstrapError: string | null
  }) => (
    <div data-testid="world-onboarding">
      <div>{bootstrapPending ? 'pending' : 'idle'}</div>
      <div>{bootstrapError ?? 'no-error'}</div>
      <button type="button" onClick={onGenerate}>generate</button>
      <button type="button" onClick={onBootstrap}>bootstrap</button>
      <button type="button" onClick={onDismiss}>dismiss</button>
    </div>
  ),
}))

describe('StudioOnboardingStage', () => {
  it('renders the preparation gate when preparation state is active', async () => {
    const user = userEvent.setup()
    const onRetry = vi.fn()
    const onDefer = vi.fn()

    render(
      <StudioOnboardingStage
        preparationGate={{
          title: 'Preparing',
          description: 'Please wait',
          detail: 'Queued',
          error: 'Boom',
          primaryActionLabel: 'Retry',
          onPrimaryAction: onRetry,
          secondaryActionLabel: 'Defer',
          onSecondaryAction: onDefer,
        }}
        showWorldOnboarding={false}
        bootstrapPending={false}
        bootstrapError={null}
        chaptersAvailable
        onWorldGenOpenChange={vi.fn()}
        onTriggerBootstrap={vi.fn()}
        onDismissWorldOnboarding={vi.fn()}
      />,
    )

    expect(screen.getByTestId('studio-preparation-gate')).toBeInTheDocument()
    expect(screen.queryByTestId('world-onboarding')).not.toBeInTheDocument()

    await user.click(screen.getByTestId('studio-preparation-primary-action'))
    await user.click(screen.getByTestId('studio-preparation-secondary-action'))

    expect(onRetry).toHaveBeenCalledTimes(1)
    expect(onDefer).toHaveBeenCalledTimes(1)
  })

  it('renders the empty-world onboarding branch and wires callbacks', async () => {
    const user = userEvent.setup()
    const onWorldGenOpenChange = vi.fn()
    const onTriggerBootstrap = vi.fn()
    const onDismissWorldOnboarding = vi.fn()

    render(
      <StudioOnboardingStage
        preparationGate={null}
        showWorldOnboarding
        bootstrapPending
        bootstrapError="bootstrap failed"
        chaptersAvailable
        onWorldGenOpenChange={onWorldGenOpenChange}
        onTriggerBootstrap={onTriggerBootstrap}
        onDismissWorldOnboarding={onDismissWorldOnboarding}
      />,
    )

    expect(screen.getByTestId('world-onboarding')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'generate' }))
    await user.click(screen.getByRole('button', { name: 'bootstrap' }))
    await user.click(screen.getByRole('button', { name: 'dismiss' }))

    expect(onWorldGenOpenChange).toHaveBeenCalledWith(true)
    expect(onTriggerBootstrap).toHaveBeenCalledTimes(1)
    expect(onDismissWorldOnboarding).toHaveBeenCalledTimes(1)
  })
})

import { usePerformanceMode } from '@/contexts/PerformanceModeContext'

/** Animated gradient blobs behind all content. See component-guidelines.md § Animated Background Parameters. */
export function AnimatedBackground() {
    const { showAmbientBackground } = usePerformanceMode()

    if (!showAmbientBackground) return null

    return (
        <div
            aria-hidden="true"
            data-testid="animated-background"
            className="pointer-events-none fixed inset-0 -z-10 overflow-hidden"
        >
            <div className="nw-starfield" />
            <div className="animated-blob blob-1" />
            <div className="animated-blob blob-2" />
            <div className="animated-blob blob-3" />
        </div>
    );
}

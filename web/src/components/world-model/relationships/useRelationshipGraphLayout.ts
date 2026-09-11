import { useEffect, useState } from 'react'
import type { GraphPositions } from './relationshipGraphGeometry'

export function useRelationshipGraphLayout(topologyKey: string) {
  const [attempt, setAttempt] = useState(0)
  const [result, setResult] = useState<{
    key: string
    positions: GraphPositions | null
  } | null>(null)

  useEffect(() => {
    // Geometry never runs on the rendering thread, including the first large graph.
    const worker = new Worker(new URL('./relationshipGraph.worker.ts', import.meta.url), { type: 'module' })
    worker.onmessage = (event: MessageEvent<GraphPositions>) => {
      setResult({ key: topologyKey, positions: event.data })
      worker.terminate()
    }
    worker.onerror = () => {
      setResult({ key: topologyKey, positions: null })
      worker.terminate()
    }
    worker.postMessage(JSON.parse(topologyKey))
    return () => {
      worker.onmessage = null
      worker.onerror = null
      worker.terminate()
    }
  }, [topologyKey, attempt])

  return {
    positions: result?.key === topologyKey ? result.positions : null,
    failed: result?.key === topologyKey && result.positions === null,
    retry: () => { setResult(null); setAttempt(current => current + 1) },
  }
}

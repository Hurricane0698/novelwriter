import { layoutRelationshipGraph, type RelationshipGraphTopology } from './relationshipGraphGeometry'

self.onmessage = (event: MessageEvent<RelationshipGraphTopology>) => {
  self.postMessage(layoutRelationshipGraph(event.data))
}

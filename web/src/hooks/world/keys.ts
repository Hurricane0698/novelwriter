export const worldKeys = {
  all: (novelId: number) => ['world', novelId] as const,
  entities: (novelId: number) => ['world', novelId, 'entities'] as const,
  entity: (novelId: number, entityId: number) => ['world', novelId, 'entities', entityId] as const,
  relationships: (novelId: number) => ['world', novelId, 'relationships'] as const,
  systems: (novelId: number) => ['world', novelId, 'systems'] as const,
  system: (novelId: number, systemId: number) => ['world', novelId, 'systems', systemId] as const,
  bootstrapStatus: (novelId: number) => ['world', novelId, 'bootstrapStatus'] as const,
}

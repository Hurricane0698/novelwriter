import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { saveAllCandidateDrafts } from '@/hooks/novel/candidateDrafts'
import { registerDesktopSave } from '@/lib/desktopExit'

/** Stay mounted across routes so desktop exit also saves closed editors. */
export function CandidateDraftPersistence() {
  const client = useQueryClient()
  useEffect(() => registerDesktopSave(() => saveAllCandidateDrafts(client)), [client])
  return null
}

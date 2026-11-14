import { useCallback, useEffect, useState } from 'react'
import { loadEarthPatch, loadMoonPatch } from './api'
import type { PatchGrid } from './types'

export type GridState = {
  grid: PatchGrid | null
  status: 'loading' | 'ready' | 'error'
  retry: () => void
}

type Slot = { key: string; grid?: PatchGrid; error?: boolean }

export function usePatchGrid(body: 'moon' | 'earth', id: string, enabled: boolean): GridState {
  const key = `${body}:${id}`
  const [slot, setSlot] = useState<Slot>({ key: '' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (!enabled) return
    let live = true
    const load = body === 'moon' ? loadMoonPatch : loadEarthPatch
    load(id).then(
      (grid) => live && setSlot({ key, grid }),
      () => live && setSlot({ key, error: true }),
    )
    return () => {
      live = false
    }
  }, [body, id, key, enabled, attempt])

  const retry = useCallback(() => {
    setSlot({ key })
    setAttempt((n) => n + 1)
  }, [key])

  const cur = slot.key === key ? slot : null
  return { grid: cur?.grid ?? null, status: cur?.grid ? 'ready' : cur?.error ? 'error' : 'loading', retry }
}

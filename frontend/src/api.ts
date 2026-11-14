import type { AnalogsResponse, MoonSite, PatchGrid } from './types'
import sampleSites from './mocks/moon_sites.json'

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export type SitesResult = { sites: MoonSite[]; source: 'api' | 'sample' }

// Falls back to bundled sample data so the UI works without the backend.
export async function loadMoonSites(): Promise<SitesResult> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/moon/sites`, { signal: AbortSignal.timeout(2500) })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return { sites: (await res.json()) as MoonSite[], source: 'api' }
  } catch {
    return { sites: sampleSites as MoonSite[], source: 'sample' }
  }
}

const analogCache = new Map<string, AnalogsResponse>()

const patchCache = new Map<string, Promise<PatchGrid>>()

function fetchPatch(key: string, path: string): Promise<PatchGrid> {
  let p = patchCache.get(key)
  if (!p) {
    p = fetch(`${API_BASE}/api/v1${path}`, { signal: AbortSignal.timeout(10000) }).then((res) => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      return res.json() as Promise<PatchGrid>
    })
    patchCache.set(key, p)
    p.catch(() => patchCache.delete(key))
  }
  return p
}

export const loadMoonPatch = (siteId: string) => fetchPatch(`moon:${siteId}`, `/moon/patch?site_id=${encodeURIComponent(siteId)}`)

export const loadEarthPatch = (patchId: string) => fetchPatch(`earth:${patchId}`, `/earth/patches/${encodeURIComponent(patchId)}`)

// One result per region keeps the five pins spread across the globe.
export async function loadAnalogs(siteId: string): Promise<AnalogsResponse> {
  const cached = analogCache.get(siteId)
  if (cached) return cached
  let data: AnalogsResponse
  try {
    const res = await fetch(`${API_BASE}/api/v1/analogs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ moon: { site_id: siteId }, top_k: 5, max_per_region: 1 }),
      signal: AbortSignal.timeout(8000),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    data = (await res.json()) as AnalogsResponse
  } catch {
    const sample = (await import('./mocks/analogs.json')).default as unknown as Record<string, AnalogsResponse>
    if (!sample[siteId]) throw new Error('No sample matches for this place')
    data = sample[siteId]
  }
  analogCache.set(siteId, data)
  return data
}

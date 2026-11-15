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

// One result per region keeps the pins spread across the globe. The API returns PIN_COUNT + extra candidates
// (same ranking, longer list) so the Pareto chart has more points to compare; the globe uses the first PIN_COUNT.
export const PIN_COUNT = 5
const CANDIDATE_COUNT = 20

export async function loadAnalogs(siteId: string): Promise<AnalogsResponse> {
  const cached = analogCache.get(siteId)
  if (cached) return cached
  let data: AnalogsResponse
  try {
    const res = await fetch(`${API_BASE}/api/v1/analogs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      // Terrain 60%, temperature swing 20%, sunlight 20%. Rock composition is shown but not ranked on.
      body: JSON.stringify({ moon: { site_id: siteId }, top_k: CANDIDATE_COUNT, max_per_region: 1, w_thermal: 0.2, w_illum: 0.2, include_practicality: true }),
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

export type ChatTurn = { role: 'user' | 'assistant'; content: string }

// Reads the server-sent events of POST /chat and calls onDelta for every piece of the answer.
export async function streamChat(
  body: { siteId: string; twinId: string | null; messages: ChatTurn[] },
  onDelta: (text: string) => void,
  signal: AbortSignal,
): Promise<void> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}/api/v1/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ moon_site_id: body.siteId, selected_twin_id: body.twinId, messages: body.messages }),
      signal,
    })
  } catch (e) {
    if (signal.aborted) throw e
    throw new Error('Cannot reach the server. Is the API running?')
  }
  if (!res.ok || !res.body) {
    const detail = (await res.json().catch(() => null)) as { message?: string } | null
    throw new Error(detail?.message ?? `The assistant is unavailable (HTTP ${res.status}).`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const events = buffer.split('\n\n')
    buffer = events.pop() ?? ''
    for (const raw of events) {
      const name = /^event: (.+)$/m.exec(raw)?.[1]
      const data = /^data: (.+)$/m.exec(raw)?.[1]
      if (!name || !data) continue
      const payload = JSON.parse(data) as { text?: string; message?: string }
      if (name === 'delta' && payload.text) onDelta(payload.text)
      if (name === 'error') throw new Error(payload.message ?? 'The assistant did not answer.')
    }
  }
}

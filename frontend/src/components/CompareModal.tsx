import { Suspense, lazy, useEffect, useRef, useState } from 'react'
import { loadEarthPatch } from '../api'
import { RAMP_CSS, sharedRange } from '../terrain'
import type { Analog } from '../types'
import { usePatchGrid } from '../usePatchGrid'
import PatchImage from './PatchImage'
import Chat, { useChat } from './Chat'
import TerrainMap from './TerrainMap'
import TradeoffView from './TradeoffView'

const Terrain3D = lazy(() => import('./Terrain3D'))

const BASE_TABS = [
  { id: 'imagery', label: 'Imagery' },
  { id: 'terrain', label: 'Terrain' },
  { id: 'terrain3d', label: '3D terrain' },
  { id: 'tradeoff', label: 'Trade-off' },
  { id: 'ask', label: 'Ask' },
] as const

type TabId = (typeof BASE_TABS)[number]['id']

const EXAGGERATIONS = [1, 2, 4]

export default function CompareModal({
  moon,
  results,
  candidates,
  activeRank,
  onSelectRank,
  onClose,
}: {
  moon: { id: string; name: string; lat: number; lon: number }
  results: Analog[]
  /** All ranked candidates; the Trade-off tab needs practicality data on them. */
  candidates: Analog[]
  activeRank: number
  onSelectRank: (rank: number) => void
  onClose: () => void
}) {
  const dialogRef = useRef<HTMLDivElement>(null)
  const analog = results.find((a) => a.rank === activeRank) ?? candidates.find((a) => a.rank === activeRank) ?? results[0]
  const hasTradeoff = candidates.filter((a) => a.practicality).length >= 2
  const TABS = BASE_TABS.filter((t) => t.id !== 'tradeoff' || hasTradeoff)
  const [tab, setTab] = useState<TabId>('imagery')
  const [matched, setMatched] = useState(true)
  const [exaggeration, setExaggeration] = useState(2)
  const chat = useChat(moon.id, analog?.patch_id ?? null)

  const needsTerrain = tab === 'terrain' || tab === 'terrain3d'
  const moonGrid = usePatchGrid('moon', moon.id, needsTerrain)
  const earthGrid = usePatchGrid('earth', analog?.patch_id ?? '', needsTerrain && !!analog)
  const range = sharedRange(moonGrid.grid, earthGrid.grid)

  useEffect(() => {
    // Warm the cache so switching between matches does not wait on the network.
    if (needsTerrain) results.forEach((a) => loadEarthPatch(a.patch_id).catch(() => undefined))
  }, [needsTerrain, results])

  useEffect(() => {
    dialogRef.current?.focus()
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLInputElement) return
      const list = tab === 'tradeoff' ? candidates : results
      const i = list.findIndex((a) => a.rank === activeRank)
      if (e.key === 'ArrowRight' && i < list.length - 1) onSelectRank(list[i + 1].rank)
      if (e.key === 'ArrowLeft' && i > 0) onSelectRank(list[i - 1].rank)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [results, candidates, tab, activeRank, onSelectRank])

  if (!analog) return null

  const moonSide = { title: moon.name, lat: moon.lat, lon: moon.lon, state: moonGrid }
  const earthSide = { title: analog.region_name, lat: analog.lat, lon: analog.lon, state: earthGrid }
  const first = results[0].region_name
  const suggestions = [
    `Why is ${first} the closest match?`,
    'Which match is best for a field campaign?',
    'Which matches have legal or protection issues?',
    `How do the minerals of ${first} compare with ${moon.name}?`,
    'Which match would you avoid, and why?',
  ]
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="compare-title" tabIndex={-1} ref={dialogRef}>
        <h2 id="compare-title" className="sr-only">
          {moon.name} compared with {analog.region_name}
        </h2>
        <div role="tablist" aria-orientation="vertical" className="rail">
          {TABS.map((t) => (
            <button key={t.id} role="tab" type="button" aria-selected={t.id === tab} onClick={() => setTab(t.id)}>
              {t.label}
            </button>
          ))}
        </div>
        <div className="modal-main" data-bare={tab === 'ask' || tab === 'tradeoff' || undefined}>
        <header className="modal-bar">
          {tab !== 'ask' && tab !== 'tradeoff' && (
            <ol className="picks" aria-label="Earth matches">
              {results.map((a) => (
                <li key={a.patch_id}>
                  <button type="button" className="pick" aria-current={a.rank === activeRank} onClick={() => onSelectRank(a.rank)}>
                    <b>{a.rank}</b>
                    <span>{a.region_name}</span>
                  </button>
                </li>
              ))}
            </ol>
          )}
          <button type="button" className="modal-close" onClick={onClose}>
            Close
          </button>
        </header>

        <div className="modal-body">
          {tab === 'imagery' && (
            <>
              <PatchImage body="moon" title={moon.name} lat={moon.lat} lon={moon.lon} />
              <PatchImage body="earth" title={analog.region_name} lat={analog.lat} lon={analog.lon} matchMoon={matched} />
            </>
          )}
          {tab === 'terrain' && <TerrainMap moon={moonSide} earth={earthSide} range={range} />}
          {tab === 'tradeoff' && <TradeoffView candidates={candidates} activeRank={activeRank} onSelect={onSelectRank} />}
          {tab === 'ask' && <Chat moonName={moon.name} suggestions={suggestions} chat={chat} />}
          {tab === 'terrain3d' && (
            <Suspense fallback={null}>
              <Terrain3D moon={moonSide} earth={earthSide} range={range} exaggeration={exaggeration} />
            </Suspense>
          )}
        </div>

        <footer className="modal-foot">
          {tab === 'imagery' ? (
            <p className="sources">
              Moon: NASA LRO camera. Earth: Esri, Maxar, Earthstar Geographics.
              {matched ? ' Both at about 100 m per pixel.' : ' Earth in full detail.'}
            </p>
          ) : tab === 'tradeoff' ? (
            <p className="sources">
              Practicality never changes the ranking. Scores: higher is easier and cheaper. Some access and power values are estimates; check flags before planning a real campaign.
            </p>
          ) : tab === 'ask' ? (
            <p className="sources">
              The assistant reads the data for this place and its five matches, including logistics and protection flags that are not shown elsewhere. It can be wrong: check numbers that matter.
            </p>
          ) : (
            <div className="legend">
              <span className="legend-bar" style={{ backgroundImage: RAMP_CSS }} />
              <span className="legend-ticks">
                <span>0 m</span>
                <span>{Math.round(range).toLocaleString('en-US')} m</span>
              </span>
              <p className="sources">
                {tab === 'terrain'
                  ? 'Height above the lowest point of each patch, on one shared scale.'
                  : 'Drag to rotate. Both views move together, on one shared height scale.'}
              </p>
            </div>
          )}
          {tab === 'imagery' && (
            <button type="button" className="modal-toggle" aria-pressed={!matched} onClick={() => setMatched((m) => !m)}>
              Earth in full detail
            </button>
          )}
          {tab === 'terrain3d' && (
            <div className="exag" role="group" aria-label="Height exaggeration">
              <span>Heights</span>
              {EXAGGERATIONS.map((x) => (
                <button key={x} type="button" aria-pressed={x === exaggeration} onClick={() => setExaggeration(x)}>
                  {x}×
                </button>
              ))}
            </div>
          )}
        </footer>
        </div>
      </div>
    </div>
  )
}

import { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { PIN_COUNT, loadAnalogs, loadMoonSites, type SitesResult } from './api'
import { toDisplaySites } from './sites'
import type { AnalogsResponse } from './types'
import SiteIndex from './components/SiteIndex'
import SiteDetail from './components/SiteDetail'
import TwinList from './components/TwinList'
import TwinDetail from './components/TwinDetail'
import CompareModal from './components/CompareModal'

const MoonScene = lazy(() => import('./components/MoonScene'))

export default function App() {
  const [data, setData] = useState<SitesResult | null>(null)
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [ready, setReady] = useState(false)
  const [mode, setMode] = useState<'moon' | 'pair'>('moon')
  const [twins, setTwins] = useState<AnalogsResponse | null>(null)
  const [finding, setFinding] = useState(false)
  const [findError, setFindError] = useState<string | null>(null)
  const [activeRank, setActiveRank] = useState(1)
  const [hoveredRank, setHoveredRank] = useState<number | null>(null)
  const [compareOpen, setCompareOpen] = useState(false)
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (mode !== 'pair') setCompareOpen(false)
  }, [mode])

  useEffect(() => {
    loadMoonSites().then(setData)
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      if (compareOpen) setCompareOpen(false)
      else if (mode === 'pair') setMode('moon')
      else setSelectedId(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [mode, compareOpen])

  useEffect(() => {
    // On phones the panel scrolls; bring the details of the new selection into view.
    if (selectedId) panelRef.current?.scrollTo({ top: 0, behavior: 'smooth' })
  }, [selectedId])

  const sites = useMemo(() => (data ? toDisplaySites(data.sites) : []), [data])
  const selected = sites.find((s) => s.id === selectedId) ?? null
  const onReady = useCallback(() => setReady(true), [])
  const toggle = useCallback((id: string) => {
    setFindError(null)
    setSelectedId((cur) => (cur === id ? null : id))
  }, [])

  const findTwins = useCallback(() => {
    if (!selectedId || finding) return
    setFinding(true)
    setFindError(null)
    loadAnalogs(selectedId)
      .then((res) => {
        setTwins(res)
        setActiveRank(1)
        setHoveredRank(null)
        setMode('pair')
      })
      .catch(() => setFindError('Could not find matches. Check that the API is running and try again.'))
      .finally(() => setFinding(false))
  }, [selectedId, finding])

  const inPair = mode === 'pair' && twins !== null && selected !== null
  const candidates = useMemo(() => twins?.results ?? [], [twins])
  const results = useMemo(() => candidates.slice(0, PIN_COUNT), [candidates])
  const activeTwin = candidates.find((a) => a.rank === activeRank) ?? null
  // Keep a selected candidate outside the top pins available to the Explore Data view.
  const compareResults = activeTwin && activeTwin.rank > PIN_COUNT ? [...results, activeTwin] : results

  return (
    <main className="app" data-mode={inPair ? 'pair' : 'moon'}>
      <header className="brand">
        <h1>Space Twin</h1>
        <p>{inPair ? 'The places on Earth whose terrain is closest to this spot on the Moon.' : 'Pick a place on the Moon. We find the places on Earth with the same terrain.'}</p>
      </header>

      <div className="stage" data-ready={ready}>
        {data && (
          <Suspense fallback={null}>
            <MoonScene
              sites={sites}
              hoveredId={hoveredId}
              selectedId={selectedId}
              onHover={setHoveredId}
              onSelect={toggle}
              onReady={onReady}
              mode={mode}
              analogs={results}
              activeRank={activeRank}
              hoveredRank={hoveredRank}
              onHoverRank={setHoveredRank}
              onSelectRank={setActiveRank}
            />
          </Suspense>
        )}
        <p className="loading" role="status">
          {ready ? '' : 'Loading NASA maps'}
        </p>
      </div>

      <div className="panel" ref={panelRef}>
        {inPair && activeTwin ? (
          <>
            <TwinDetail
              analog={activeTwin}
              count={candidates.length}
              moon={twins.moon}
              moonName={selected.name}
              moonFeatures={selected.features}
              outOfRange={twins.out_of_range}
              onCompare={() => setCompareOpen(true)}
            />
            <TwinList
              moonName={selected.name}
              results={results}
              activeRank={activeRank}
              hoveredRank={hoveredRank}
              onHover={setHoveredRank}
              onSelect={setActiveRank}
              onBack={() => setMode('moon')}
            />
          </>
        ) : (
          <>
            <SiteDetail site={selected} onFind={findTwins} finding={finding} error={findError} />
            <SiteIndex sites={sites} hoveredId={hoveredId} selectedId={selectedId} onHover={setHoveredId} onSelect={toggle} />
          </>
        )}
      </div>

      {inPair && compareOpen && (
        <CompareModal
          moon={{ id: selected.id, name: selected.name, lat: selected.lat, lon: selected.lon }}
          results={compareResults}
          candidates={candidates}
          activeRank={activeRank}
          onSelectRank={setActiveRank}
          onClose={() => setCompareOpen(false)}
        />
      )}

      <p className="credit">
        {inPair
          ? 'Moon and Earth: NASA Scientific Visualization Studio. Sizes and distance are not to scale.'
          : 'Surface: NASA Scientific Visualization Studio, from LRO camera and laser altimeter data.'}
        {data?.source === 'sample' && ' Showing sample data because the API is offline.'}
      </p>
    </main>
  )
}

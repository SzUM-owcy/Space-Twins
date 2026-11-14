import { useEffect, useRef, useState } from 'react'
import type { Analog } from '../types'
import PatchImage from './PatchImage'

type Tab = { id: string; label: string }

// New comparisons (terrain, features) are added here as extra tabs.
const TABS: Tab[] = [{ id: 'imagery', label: 'Imagery' }]

export default function CompareModal({
  moon,
  results,
  activeRank,
  onSelectRank,
  onClose,
}: {
  moon: { name: string; lat: number; lon: number }
  results: Analog[]
  activeRank: number
  onSelectRank: (rank: number) => void
  onClose: () => void
}) {
  const dialogRef = useRef<HTMLDivElement>(null)
  const analog = results.find((a) => a.rank === activeRank) ?? results[0]
  const tab = TABS[0]
  const [matched, setMatched] = useState(true)

  useEffect(() => {
    dialogRef.current?.focus()
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const i = results.findIndex((a) => a.rank === activeRank)
      if (e.key === 'ArrowRight' && i < results.length - 1) onSelectRank(results[i + 1].rank)
      if (e.key === 'ArrowLeft' && i > 0) onSelectRank(results[i - 1].rank)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [results, activeRank, onSelectRank])

  if (!analog) return null

  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="compare-title" tabIndex={-1} ref={dialogRef}>
        <h2 id="compare-title" className="sr-only">
          {moon.name} compared with {analog.region_name}
        </h2>
        <header className="modal-bar">
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
          {TABS.length > 1 && (
            <div role="tablist" className="tabs">
              {TABS.map((t) => (
                <button key={t.id} role="tab" type="button" aria-selected={t.id === tab.id}>
                  {t.label}
                </button>
              ))}
            </div>
          )}
          <button type="button" className="modal-close" onClick={onClose}>
            Close
          </button>
        </header>

        <div className="modal-body">
          <PatchImage body="moon" title={moon.name} lat={moon.lat} lon={moon.lon} />
          <PatchImage body="earth" title={analog.region_name} lat={analog.lat} lon={analog.lon} matchMoon={matched} />
        </div>

        <footer className="modal-foot">
          <p className="sources">
            Moon: NASA LRO camera. Earth: Esri, Maxar, Earthstar Geographics.
            {matched ? ' Both at about 100 m per pixel.' : ' Earth in full detail.'}
          </p>
          <button type="button" className="modal-toggle" aria-pressed={!matched} onClick={() => setMatched((m) => !m)}>
            Earth in full detail
          </button>
        </footer>
      </div>
    </div>
  )
}

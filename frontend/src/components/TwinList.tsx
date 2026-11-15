import type { ReactNode } from 'react'
import { formatCoords } from '../sites'
import type { Analog } from '../types'

export default function TwinList({
  moonName,
  results,
  activeRank,
  hoveredRank,
  onHover,
  onSelect,
  onBack,
  children,
}: {
  moonName: string
  results: Analog[]
  activeRank: number
  hoveredRank: number | null
  onHover: (rank: number | null) => void
  onSelect: (rank: number) => void
  onBack: () => void
  children?: ReactNode
}) {
  return (
    <nav className="index twins" aria-label="Closest places on Earth">
      <button type="button" className="back" onClick={onBack}>
        Back to the Moon
      </button>
      <h2 className="twins-title">Closest to {moonName}</h2>
      <ol>
        {results.map((a) => (
          <li key={a.patch_id}>
            <button
              type="button"
              className="twin"
              aria-pressed={a.rank === activeRank}
              data-hover={a.rank === hoveredRank}
              onClick={() => onSelect(a.rank)}
              onMouseEnter={() => onHover(a.rank)}
              onMouseLeave={() => onHover(null)}
              onFocus={() => onHover(a.rank)}
              onBlur={() => onHover(null)}
            >
              <span className="rank">{a.rank}</span>
              <span className="twin-text">
                <span className="twin-name">{a.region_name}</span>
                <span className="twin-coords">{formatCoords(a.lat, a.lon)}</span>
              </span>
            </button>
          </li>
        ))}
      </ol>
      {children}
    </nav>
  )
}

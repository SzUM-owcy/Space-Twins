import { useState } from 'react'
import type { Analog } from '../types'

type Profile = 'field' | 'facility'

const W = 320
const H = 230
const PAD = { l: 38, r: 12, t: 12, b: 38 }
const PLOT_W = W - PAD.l - PAD.r
const PLOT_H = H - PAD.t - PAD.b

const PROFILES: Record<Profile, { label: string; hint: string }> = {
  field: { label: 'Field campaign', hint: 'short rover and instrument tests' },
  facility: { label: 'Facility', hint: 'repeated campaigns and habitat tests' },
}

type Point = { a: Analog; x: number; d: number; pareto: boolean; excluded: boolean }

function toPoints(candidates: Analog[], profile: Profile): Point[] {
  const out: Point[] = []
  for (const a of candidates) {
    const p = a.practicality
    const x = profile === 'field' ? p?.field_campaign_score : p?.facility_score
    if (x == null) continue
    out.push({
      a,
      x,
      d: a.total_distance,
      pareto: profile === 'field' ? !!p?.pareto_field : !!p?.pareto_facility,
      excluded: !!a.constraints?.hard_excluded,
    })
  }
  return out
}

export default function ParetoChart({
  candidates,
  activeRank,
  hoveredRank,
  onHover,
  onSelect,
}: {
  candidates: Analog[]
  activeRank: number
  hoveredRank: number | null
  onHover: (rank: number | null) => void
  onSelect: (rank: number) => void
}) {
  const [profile, setProfile] = useState<Profile>('field')
  const points = toPoints(candidates, profile)
  if (points.length < 2) return null

  const maxD = Math.max(...points.map((p) => p.d)) * 1.08 || 1
  // Up = closer match, right = easier to run.
  const sx = (x: number) => PAD.l + (x / 100) * PLOT_W
  const sy = (d: number) => PAD.t + (d / maxD) * PLOT_H
  const front = points.filter((p) => p.pareto && !p.excluded).sort((a, b) => a.x - b.x)
  const focus = points.find((p) => p.a.rank === (hoveredRank ?? activeRank)) ?? null
  const cost = (p: Point) => (profile === 'field' ? p.a.practicality?.field_cost_class : p.a.practicality?.facility_cost_class)

  return (
    <section className="pareto" aria-label="Scientific match versus practicality">
      <div className="pareto-head">
        <h3>Match vs. practicality</h3>
        <div className="pareto-toggle" role="group" aria-label="Practicality profile">
          {(Object.keys(PROFILES) as Profile[]).map((id) => (
            <button key={id} type="button" aria-pressed={id === profile} onClick={() => setProfile(id)}>
              {PROFILES[id].label}
            </button>
          ))}
        </div>
      </div>

      <svg viewBox={`0 0 ${W} ${H}`} role="group" aria-label={`Candidates: ${PROFILES[profile].hint}`}>
        <rect x={PAD.l} y={PAD.t} width={PLOT_W} height={PLOT_H} className="pareto-frame" />
        {[0, 25, 50, 75, 100].map((t) => (
          <g key={t}>
            <line x1={sx(t)} x2={sx(t)} y1={PAD.t} y2={PAD.t + PLOT_H} className="pareto-grid" />
            <text x={sx(t)} y={H - PAD.b + 14} textAnchor="middle" className="pareto-tick">
              {t}
            </text>
          </g>
        ))}
        <text x={PAD.l + PLOT_W / 2} y={H - 6} textAnchor="middle" className="pareto-axis">
          Easier and cheaper to run →
        </text>
        <text transform={`translate(11 ${PAD.t + PLOT_H / 2}) rotate(-90)`} textAnchor="middle" className="pareto-axis">
          Closer match →
        </text>

        {front.length > 1 && (
          <polyline className="pareto-front" points={front.map((p) => `${sx(p.x)},${sy(p.d)}`).join(' ')} />
        )}

        {points.map((p) => {
          const rank = p.a.rank
          const cx = sx(p.x)
          const cy = sy(p.d)
          const isActive = rank === activeRank
          const state = p.excluded ? 'excluded' : p.pareto ? 'pareto' : 'other'
          return (
            <g
              key={p.a.patch_id}
              className="pareto-point"
              data-state={state}
              data-active={isActive}
              data-hover={rank === hoveredRank}
              role="button"
              tabIndex={0}
              aria-label={`${p.a.region_name}, match ${rank}${p.pareto ? ', best trade-off' : ''}${p.excluded ? ', excluded' : ''}`}
              aria-pressed={isActive}
              onClick={() => onSelect(rank)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  onSelect(rank)
                }
              }}
              onMouseEnter={() => onHover(rank)}
              onMouseLeave={() => onHover(null)}
              onFocus={() => onHover(rank)}
              onBlur={() => onHover(null)}
            >
              <circle cx={cx} cy={cy} r={11} className="pareto-hit" />
              {p.excluded ? (
                <path d={`M${cx - 4} ${cy - 4}L${cx + 4} ${cy + 4}M${cx + 4} ${cy - 4}L${cx - 4} ${cy + 4}`} className="pareto-cross" />
              ) : (
                <circle cx={cx} cy={cy} r={isActive ? 6 : 4.5} className="pareto-dot" />
              )}
            </g>
          )
        })}
      </svg>

      <p className="pareto-focus" aria-live="polite">
        {focus ? (
          <>
            <strong>{focus.a.region_name}</strong>
            {' · '}
            {focus.excluded ? 'excluded, needs manual review' : `${cost(focus)?.toLowerCase() ?? 'unknown'} cost`}
            {focus.pareto && !focus.excluded && ' · best trade-off'}
          </>
        ) : (
          'Hover or pick a point.'
        )}
      </p>
      <ul className="pareto-legend">
        <li data-state="pareto">Best trade-off</li>
        <li data-state="other">Other candidate</li>
        <li data-state="excluded">Excluded</li>
      </ul>
      <details className="pareto-help" open>
        <summary>How to read this</summary>
        <ul>
          <li>Each dot is a candidate place on Earth. Higher means its terrain is a closer match to the Moon site.</li>
          <li>Further right means it is easier and cheaper to run a simulation there (access, buildability, medical help, power).</li>
          <li>
            Yellow dots are the best trade-offs: no other candidate is both closer and easier. The dashed line joins them. Pick one
            if you want a good match without a hard logistics problem.
          </li>
          <li>A red cross has a hard constraint, such as a strict protected area. It stays visible but needs manual review.</li>
        </ul>
        <p>
          Practicality never changes the ranking. Only these {points.length} candidates are compared, and some access and power
          values are estimates.
        </p>
      </details>
    </section>
  )
}

import { useState } from 'react'
import type { Analog, FlagStatus } from '../types'
import { PROFILES, type Profile } from '../profiles'
import ParetoChart from './ParetoChart'

const SCORES = [
  { key: 'access_score', label: 'Access', hint: 'travel time to cities, airports and roads' },
  { key: 'buildability_score', label: 'Buildable ground', hint: 'flat 1 km area for a base' },
  { key: 'emergency_support_score', label: 'Medical help', hint: 'travel time to healthcare' },
  { key: 'infrastructure_score', label: 'Power', hint: 'distance to the electric grid' },
] as const

const FLAGS = [
  { key: 'protected_area_status', label: 'Protected area' },
  { key: 'world_heritage_status', label: 'World Heritage' },
  { key: 'community_rights_status', label: 'Community and land rights' },
  { key: 'biodiversity_status', label: 'Habitat' },
  { key: 'water_stress_status', label: 'Water stress' },
  { key: 'hazard_status', label: 'Natural hazard' },
  { key: 'security_status', label: 'Security' },
] as const

const STATUS_TEXT: Record<FlagStatus, string> = {
  ok: 'ok',
  warning: 'warning',
  manual_review: 'needs review',
  excluded: 'excluded',
  missing: 'no data',
}

function Selected({ analog }: { analog: Analog }) {
  const p = analog.practicality
  const c = analog.constraints
  const flags = c ? FLAGS.filter((f) => c[f.key] !== 'ok') : []
  return (
    <div className="tradeoff-side">
      <h3>{analog.region_name}</h3>
      {p && (
        <p className="tradeoff-cost">
          Field campaign: <b>{c?.hard_excluded ? 'excluded' : (p.field_cost_class ?? '–').toLowerCase()}</b>
          {' · '}Facility: <b>{c?.hard_excluded ? 'excluded' : (p.facility_cost_class ?? '–').toLowerCase()}</b>
        </p>
      )}
      {p && (
        <ul className="scores" aria-label="Practicality scores, higher is easier">
          {SCORES.map((s) => {
            const v = p[s.key]
            return (
              <li key={s.key} title={s.hint}>
                <span>{s.label}</span>
                <span className="score-bar" aria-hidden="true">
                  <i style={{ width: `${v ?? 0}%` }} />
                </span>
                <b>{v == null ? '–' : Math.round(v)}</b>
              </li>
            )
          })}
        </ul>
      )}
      {flags.length > 0 && (
        <ul className="flag-list" aria-label="Constraints to check">
          {flags.map((f) => (
            <li key={f.key} data-status={c?.[f.key]}>
              {f.label}: {STATUS_TEXT[c![f.key]]}
            </li>
          ))}
        </ul>
      )}
      {c?.hard_excluded && c.exclusion_reasons.length > 0 && <p className="tradeoff-note">Excluded because: {c.exclusion_reasons.join(', ').replaceAll('_', ' ')}.</p>}
      {p?.grid_source === 'estimated' && <p className="tradeoff-note">The power grid distance for this region is an estimate.</p>}
    </div>
  )
}

export default function TradeoffView({
  candidates,
  activeRank,
  onSelect,
}: {
  candidates: Analog[]
  activeRank: number
  onSelect: (rank: number) => void
}) {
  const [profile, setProfile] = useState<Profile>('field')
  const [hovered, setHovered] = useState<number | null>(null)
  const active = candidates.find((a) => a.rank === activeRank) ?? candidates[0]
  return (
    <div className="tradeoff-wrap">
      <div className="profile-toggle" role="group" aria-label="Practicality profile">
        {(Object.keys(PROFILES) as Profile[]).map((id) => (
          <button key={id} type="button" aria-pressed={id === profile} onClick={() => setProfile(id)}>
            <span>{PROFILES[id].label}</span>
            <small>{PROFILES[id].hint}</small>
          </button>
        ))}
      </div>
      <div className="tradeoff">
        <ParetoChart profile={profile} candidates={candidates} activeRank={activeRank} hoveredRank={hovered} onHover={setHovered} onSelect={onSelect} />
        {active && <Selected analog={active} />}
      </div>
    </div>
  )
}

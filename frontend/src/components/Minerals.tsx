export const MINERALS = [
  { key: 'plagioclase', label: 'Plagioclase', color: '#ffffff' },
  { key: 'pyroxene', label: 'Pyroxene', color: '#2e96f5' },
  { key: 'olivine', label: 'Olivine', color: '#e43700' },
  { key: 'other', label: 'Other', color: '#6f7d9e' },
] as const

export type Mix = Record<(typeof MINERALS)[number]['key'], number>

// Moon unmixing can return small negatives or sums above 1; clamp and rescale so the bar always adds up.
export function normalise(mix: Mix): Mix | null {
  const c = {
    plagioclase: Math.max(0, mix.plagioclase),
    pyroxene: Math.max(0, mix.pyroxene),
    olivine: Math.max(0, mix.olivine),
    other: Math.max(0, mix.other),
  }
  const sum = c.plagioclase + c.pyroxene + c.olivine + c.other
  if (sum <= 0) return null
  return { plagioclase: c.plagioclase / sum, pyroxene: c.pyroxene / sum, olivine: c.olivine / sum, other: c.other / sum }
}

export function moonMix(m: { plagioclase: number; pyroxene: number; olivine: number } | null | undefined): Mix | null {
  return m ? normalise({ plagioclase: m.plagioclase, pyroxene: m.pyroxene, olivine: m.olivine, other: 0 }) : null
}

export function MixBar({ label, mix, empty }: { label: string; mix: Mix | null; empty: string }) {
  return (
    <div className="mix-row">
      <span className="mix-label">{label}</span>
      {mix ? (
        <span className="mix-bar" role="img" aria-label={MINERALS.map((m) => `${m.label} ${Math.round(mix[m.key] * 100)}%`).join(', ')}>
          {MINERALS.map((m) => (
            <i key={m.key} style={{ flexGrow: mix[m.key], background: m.color }} />
          ))}
        </span>
      ) : (
        <span className="mix-empty">{empty}</span>
      )}
    </div>
  )
}

export function MixLegend({ withOther = true }: { withOther?: boolean }) {
  return (
    <ul className="mix-legend">
      {MINERALS.filter((m) => withOther || m.key !== 'other').map((m) => (
        <li key={m.key}>
          <i style={{ background: m.color }} />
          {m.label}
        </li>
      ))}
    </ul>
  )
}

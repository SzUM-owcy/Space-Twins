import { formatCoords } from '../sites'
import type { Analog } from '../types'

const ROWS: { key: string; label: string; unit: string; digits: number }[] = [
  { key: 'relief_range', label: 'Height range', unit: 'm', digits: 0 },
  { key: 'slope_p50', label: 'Median slope', unit: '°', digits: 1 },
  { key: 'tri_mean', label: 'Ruggedness', unit: 'm', digits: 1 },
]

const fmt = (v: number | undefined, digits: number) =>
  v === undefined ? '–' : v.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })

export default function TwinDetail({
  analog,
  count,
  moonName,
  moonFeatures,
  outOfRange,
}: {
  analog: Analog
  count: number
  moonName: string
  moonFeatures: Record<string, number>
  outOfRange: string[]
}) {
  return (
    <section className="detail twin-detail" aria-live="polite" key={analog.patch_id}>
      <h2 className="name">{analog.region_name}</h2>
      <p className="coords">
        {formatCoords(analog.lat, analog.lon)}
        <span className="sep">Match {analog.rank} of {count}</span>
      </p>
      <table className="compare">
        <thead>
          <tr>
            <td />
            <th scope="col">{moonName}</th>
            <th scope="col">{analog.region_name}</th>
          </tr>
        </thead>
        <tbody>
          {ROWS.map((r) => (
            <tr key={r.key}>
              <th scope="row">{r.label}</th>
              <td>
                {fmt(moonFeatures[r.key], r.digits)}
                <span className="unit">{r.unit}</span>
              </td>
              <td>
                {fmt(analog.features[r.key], r.digits)}
                <span className="unit">{r.unit}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {outOfRange.length > 0 && (
        <p className="warn">Some measurements of this place are more extreme than any Earth terrain we hold, so this ranking is less reliable.</p>
      )}
      <p className="note">
        Ranked by terrain shape only: slope and relief across 10 × 10 km patches ({analog.source}). It says nothing about rock type, climate or atmosphere.
      </p>
    </section>
  )
}

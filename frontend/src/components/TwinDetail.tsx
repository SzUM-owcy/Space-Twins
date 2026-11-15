import { formatCoords } from '../sites'
import type { Analog, MoonSummary } from '../types'
import { MixBar, MixLegend, moonMix, normalise, type Mix } from './Minerals'

type Row = { label: string; unit: string; digits: number; moon: number | undefined; earth: number | undefined }

const fmt = (v: number | undefined, digits: number) =>
  v === undefined ? '–' : v.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })

function earthMix(a: Analog): Mix | null {
  if (a.earth_mineral_status !== 'estimated') return null
  return normalise({
    plagioclase: a.earth_plagioclase_fraction ?? 0,
    pyroxene: a.earth_pyroxene_fraction ?? 0,
    olivine: a.earth_olivine_fraction ?? 0,
    other: a.earth_other_fraction ?? 0,
  })
}

const LITHOLOGY: Record<string, string> = {
  mafic: 'Dark volcanic rock',
  felsic: 'Light granite-type rock',
  anorthosite: 'Anorthosite',
  carbonate: 'Limestone-type rock',
  evaporite: 'Salt and gypsum',
  sedimentary: 'Sedimentary rock',
  unconsolidated: 'Loose sediment',
}

export default function TwinDetail({
  analog,
  count,
  moon,
  moonName,
  moonFeatures,
  outOfRange,
  onCompare,
}: {
  analog: Analog
  count: number
  moon: MoonSummary
  moonName: string
  moonFeatures: Record<string, number>
  outOfRange: string[]
  onCompare: () => void
}) {
  const pct = (v: number | null | undefined) => (v == null ? undefined : v * 100)
  const rows: Row[] = [
    { label: 'Height range', unit: 'm', digits: 0, moon: moonFeatures.relief_range, earth: analog.features.relief_range },
    { label: 'Median slope', unit: '°', digits: 1, moon: moonFeatures.slope_p50, earth: analog.features.slope_p50 },
    { label: 'Ruggedness', unit: 'm', digits: 1, moon: moonFeatures.tri_mean, earth: analog.features.tri_mean },
  ]
  if (moon.thermal_range_k != null || analog.thermal_range_k != null) {
    rows.push({ label: 'Day–night swing', unit: 'K', digits: 0, moon: moon.thermal_range_k ?? undefined, earth: analog.thermal_range_k ?? undefined })
  }
  if (moon.solar_visibility_fraction != null || analog.solar_visibility_fraction != null) {
    rows.push({ label: 'Sunlit daytime', unit: '%', digits: 0, moon: pct(moon.solar_visibility_fraction), earth: pct(analog.solar_visibility_fraction) })
  }

  const mMix = moonMix(moon.minerals)
  const eMix = earthMix(analog)
  const rock = analog.dominant_lithology ? LITHOLOGY[analog.dominant_lithology] : undefined
  const showRock = mMix !== null || eMix !== null

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
          {rows.map((r) => (
            <tr key={r.label}>
              <th scope="row">{r.label}</th>
              <td>
                {fmt(r.moon, r.digits)}
                <span className="unit">{r.unit}</span>
              </td>
              <td>
                {fmt(r.earth, r.digits)}
                <span className="unit">{r.unit}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {showRock && (
        <div className="rock">
          <div className="rock-head">
            <span>Minerals</span>
            {rock && <span className="rock-type">{analog.mixed_lithology_flag ? `Mixed, mostly ${rock.toLowerCase()}` : rock}</span>}
          </div>
          <MixBar label="Moon" mix={mMix} empty="Not mapped here" />
          <MixBar label="Earth" mix={eMix} empty="No rock map for this place" />
          <MixLegend />
        </div>
      )}

      <button type="button" className="cta" onClick={onCompare}>
        Compare views
      </button>
      {outOfRange.length > 0 && (
        <p className="warn">Some measurements of this place are more extreme than any Earth terrain we hold, so this ranking is less reliable.</p>
      )}
    </section>
  )
}

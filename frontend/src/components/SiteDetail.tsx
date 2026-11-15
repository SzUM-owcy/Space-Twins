import { formatCoords, type DisplaySite } from '../sites'
import { MixBar, MixLegend, moonMix } from './Minerals'

function Figure({ label, value, unit }: { label: string; value: string; unit: string }) {
  return (
    <div className="figure">
      <dt>{label}</dt>
      <dd>
        {value}
        <span className="unit">{unit}</span>
      </dd>
    </div>
  )
}

export default function SiteDetail({
  site,
  onFind,
  finding,
  error,
}: {
  site: DisplaySite | null
  onFind: () => void
  finding: boolean
  error: string | null
}) {
  return (
    <section className="detail" aria-live="polite">
      {site ? (
        <>
          <h2 className="name">{site.name}</h2>
          <p className="coords">{formatCoords(site.lat, site.lon)}</p>
          {site.blurb && <p className="blurb">{site.blurb}</p>}
          <dl className="figures">
            <Figure label="Height range" value={Math.round(site.features.relief_range).toLocaleString('en-US')} unit="m" />
            <Figure label="Median slope" value={site.features.slope_p50.toFixed(1)} unit="°" />
            <Figure label="Ruggedness" value={site.features.tri_mean.toFixed(1)} unit="m" />
            {site.thermalRangeK !== null && <Figure label="Day–night swing" value={Math.round(site.thermalRangeK).toLocaleString('en-US')} unit="K" />}
            {site.sunlitFraction !== null && <Figure label="Sunlit daytime" value={Math.round(site.sunlitFraction * 100).toString()} unit="%" />}
          </dl>
          {moonMix(site.minerals) && (
            <div className="rock site-rock">
              <div className="rock-head">
                <span>Minerals</span>
              </div>
              <MixBar label="Moon" mix={moonMix(site.minerals)} empty="Not mapped here" />
              <MixLegend withOther={false} />
            </div>
          )}
          <button type="button" className="cta" onClick={onFind} disabled={finding}>
            {finding ? 'Searching Earth…' : 'Find Earth twins'}
          </button>
          {error && <p className="warn">{error}</p>}
          <p className="note">Measured across a 10 × 10 km patch centred on this point.</p>
        </>
      ) : (
        <>
          <p className="empty">Choose a marker on the Moon, or a name from the list.</p>
          <p className="note">Each square marks a 10 × 10 km patch, drawn larger so you can see it.</p>
        </>
      )}
    </section>
  )
}

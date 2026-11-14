import { GROUPS, GROUP_COLOR, type DisplaySite } from '../sites'

export default function SiteIndex({
  sites,
  hoveredId,
  selectedId,
  onHover,
  onSelect,
}: {
  sites: DisplaySite[]
  hoveredId: string | null
  selectedId: string | null
  onHover: (id: string | null) => void
  onSelect: (id: string) => void
}) {
  return (
    <nav className="index" aria-label="Places on the Moon">
      {GROUPS.map((group) => {
        const items = sites.filter((s) => s.group === group.id)
        if (items.length === 0) return null
        return (
          <section key={group.id} className="group">
            <h2>
              <span>{group.title}</span>
              <span className="count">{items.length}</span>
            </h2>
            <ul>
              {items.map((site) => (
                <li key={site.id}>
                  <button
                    type="button"
                    className="site"
                    style={{ '--c': GROUP_COLOR[site.group] } as React.CSSProperties}
                    aria-pressed={site.id === selectedId}
                    data-hover={site.id === hoveredId}
                    onClick={() => onSelect(site.id)}
                    onMouseEnter={() => onHover(site.id)}
                    onMouseLeave={() => onHover(null)}
                    onFocus={() => onHover(site.id)}
                    onBlur={() => onHover(null)}
                  >
                    <span className="swatch" aria-hidden="true" />
                    {site.name}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )
      })}
    </nav>
  )
}

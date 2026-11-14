export const COLORS = {
  void: '#07173F',
  rocket: '#E43700',
  yonder: '#2E96F5',
  white: '#FFFFFF',
  signal: '#EAFE07',
} as const

export type GroupId = 'apollo' | 'pole' | 'terrain'

export const GROUPS: { id: GroupId; title: string; color: string }[] = [
  { id: 'apollo', title: 'Apollo landing sites', color: COLORS.rocket },
  { id: 'pole', title: 'South pole', color: COLORS.yonder },
  { id: 'terrain', title: 'Craters, highlands and plains', color: COLORS.white },
]

export const GROUP_COLOR: Record<GroupId, string> = {
  apollo: COLORS.rocket,
  pole: COLORS.yonder,
  terrain: COLORS.white,
}

type SiteInfo = { name: string; group: GroupId; blurb: string }

// Keyed by site_id from the API. Order here = order in the index.
export const SITE_INFO: Record<string, SiteInfo> = {
  moon_apollo_11: { name: 'Apollo 11', group: 'apollo', blurb: 'First crewed landing, July 1969, on the edge of Mare Tranquillitatis.' },
  moon_apollo_12: { name: 'Apollo 12', group: 'apollo', blurb: 'November 1969, Oceanus Procellarum, a short walk from the Surveyor 3 probe.' },
  moon_apollo_14: { name: 'Apollo 14', group: 'apollo', blurb: 'February 1971, the Fra Mauro highlands.' },
  moon_apollo_15: { name: 'Apollo 15', group: 'apollo', blurb: 'Summer 1971, between the Apennine mountains and Hadley Rille. First lunar rover.' },
  moon_apollo_16: { name: 'Apollo 16', group: 'apollo', blurb: 'April 1972, the Descartes highlands.' },
  moon_apollo_17: { name: 'Apollo 17', group: 'apollo', blurb: 'December 1972, the Taurus-Littrow valley. The last crewed landing so far.' },
  moon_shackleton: { name: 'Shackleton', group: 'pole', blurb: 'Crater at the south pole. Its rim sees almost constant sunlight, its floor none at all.' },
  moon_haworth: { name: 'Haworth', group: 'pole', blurb: 'Permanently shadowed crater near the south pole.' },
  moon_de_gerlache: { name: 'De Gerlache', group: 'pole', blurb: 'Crater beside Shackleton, with deeply shadowed ground.' },
  moon_malapert: { name: 'Malapert', group: 'pole', blurb: 'Massif near the south pole that keeps a line of sight to Earth.' },
  moon_tycho: { name: 'Tycho', group: 'terrain', blurb: 'Young crater, about 108 million years old, with bright rays reaching across the near side.' },
  moon_copernicus: { name: 'Copernicus', group: 'terrain', blurb: 'Crater with terraced walls and central peaks, about 800 million years old.' },
  moon_aristarchus_crater: { name: 'Aristarchus', group: 'terrain', blurb: 'One of the brightest craters on the Moon, beside a sinuous valley.' },
  moon_highlands_hipparchus: { name: 'Hipparchus highlands', group: 'terrain', blurb: 'Ancient, heavily cratered terrain in the central highlands.' },
  moon_highlands_maurolycus: { name: 'Maurolycus highlands', group: 'terrain', blurb: 'Rugged southern highlands, crowded with overlapping craters.' },
  moon_mare_imbrium: { name: 'Mare Imbrium', group: 'terrain', blurb: 'Vast basin flooded with dark basalt.' },
  moon_mare_serenitatis: { name: 'Mare Serenitatis', group: 'terrain', blurb: 'Smooth basalt plain, next to the Apollo 17 valley.' },
  moon_marius_hills: { name: 'Marius Hills', group: 'terrain', blurb: 'Field of volcanic domes and winding rilles.' },
}

export type DisplaySite = {
  id: string
  name: string
  group: GroupId
  blurb: string
  lat: number
  lon: number
  features: Record<string, number>
}

export function toDisplaySites(raw: { site_id: string; name: string; lat: number; lon: number; features: Record<string, number> }[]): DisplaySite[] {
  const known = Object.keys(SITE_INFO)
  const rank = (id: string) => {
    const i = known.indexOf(id)
    return i === -1 ? known.length : i
  }
  return raw
    .map((s) => {
      const info = SITE_INFO[s.site_id]
      return {
        id: s.site_id,
        name: info?.name ?? s.name,
        group: info?.group ?? 'terrain',
        blurb: info?.blurb ?? '',
        lat: s.lat,
        lon: s.lon,
        features: s.features,
      } satisfies DisplaySite
    })
    .sort((a, b) => rank(a.id) - rank(b.id))
}

export function formatCoords(lat: number, lon: number): string {
  const ns = lat >= 0 ? 'N' : 'S'
  const ew = lon >= 0 ? 'E' : 'W'
  return `${Math.abs(lat).toFixed(2)}°${ns}, ${Math.abs(lon).toFixed(2)}°${ew}`
}

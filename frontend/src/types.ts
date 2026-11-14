export type MoonSite = {
  site_id: string
  name: string
  lat: number
  lon: number
  features: Record<string, number>
}

export type Analog = {
  rank: number
  patch_id: string
  region: string
  region_name: string
  source: 'NASADEM' | 'COPDEM'
  lat: number
  lon: number
  total_distance: number
  features: Record<string, number>
}

export type AnalogsResponse = {
  moon: { site_id: string | null; name: string; features: Record<string, number> }
  out_of_range: string[]
  results: Analog[]
}

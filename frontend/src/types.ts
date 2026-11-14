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

export type PatchGrid = {
  patch_id: string | null
  body: 'moon' | 'earth'
  region: string | null
  lat: number
  lon: number
  size_m: number
  grid_n: number
  pixel_size_m: number
  min_m: number
  max_m: number
  /** heights_m[row][col]; row 0 is north, col 0 is west. */
  heights_m: number[][]
}

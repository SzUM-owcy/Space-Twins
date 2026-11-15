export type MoonSite = {
  site_id: string
  name: string
  lat: number
  lon: number
  features: Record<string, number>
  thermal_range_k?: number | null
  solar_visibility_fraction?: number | null
  minerals?: { plagioclase: number; pyroxene: number; olivine: number } | null
}

export type Quality = 'good' | 'moderate' | 'poor'

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
  // Added with the thermal, illumination and composition work; absent in the bundled sample data.
  terrain_quality?: Quality | null
  thermal_quality?: Quality | null
  illumination_quality?: Quality | null
  dominant_lithology?: string | null
  thermal_range_k?: number | null
  solar_visibility_fraction?: number | null
  mixed_lithology_flag?: boolean | null
  earth_plagioclase_fraction?: number | null
  earth_pyroxene_fraction?: number | null
  earth_olivine_fraction?: number | null
  earth_other_fraction?: number | null
  earth_mineral_status?: 'estimated' | 'no_lithology' | null
}

export type MoonSummary = {
  site_id: string | null
  name: string
  features: Record<string, number>
  thermal_range_percentile?: number | null
  thermal_range_k?: number | null
  solar_visibility_fraction?: number | null
  minerals?: { plagioclase: number; pyroxene: number; olivine: number } | null
}

export type AnalogsResponse = {
  moon: MoonSummary
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

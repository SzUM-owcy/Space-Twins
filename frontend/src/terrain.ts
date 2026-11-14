import type { PatchGrid } from './types'

// Classic hypsometric tints: lowlands green, through tan and brown, to pale peaks.
const STOPS: [number, [number, number, number]][] = [
  [0, [47, 107, 58]],
  [0.25, [143, 174, 79]],
  [0.5, [227, 207, 138]],
  [0.75, [160, 113, 74]],
  [1, [244, 241, 236]],
]

export function rampColor(t: number): [number, number, number] {
  const x = Math.min(1, Math.max(0, t))
  for (let i = 1; i < STOPS.length; i++) {
    const [t1, c1] = STOPS[i]
    if (x <= t1) {
      const [t0, c0] = STOPS[i - 1]
      const f = (x - t0) / (t1 - t0)
      return [c0[0] + (c1[0] - c0[0]) * f, c0[1] + (c1[1] - c0[1]) * f, c0[2] + (c1[2] - c0[2]) * f]
    }
  }
  return STOPS[STOPS.length - 1][1]
}

export const RAMP_CSS = `linear-gradient(to right, ${STOPS.map(([t, c]) => `rgb(${c.join(',')}) ${t * 100}%`).join(', ')})`

/** Heights above the lowest point of each patch; one shared range keeps the two patches comparable. */
export const sharedRange = (...grids: (PatchGrid | null)[]) =>
  Math.max(1, ...grids.map((g) => (g ? g.max_m - g.min_m : 0)))

const cubic = (p0: number, p1: number, p2: number, p3: number, t: number) =>
  p1 + 0.5 * t * (p2 - p0 + t * (2 * p0 - 5 * p1 + 4 * p2 - p3 + t * (3 * (p1 - p2) + p3 - p0)))

function upsample(grid: PatchGrid, m: number): Float32Array {
  const n = grid.grid_n
  const h = grid.heights_m
  const at = (r: number, c: number) => h[Math.min(n - 1, Math.max(0, r))][Math.min(n - 1, Math.max(0, c))]
  const out = new Float32Array(m * m)
  const step = (n - 1) / (m - 1)
  for (let i = 0; i < m; i++) {
    const fy = i * step
    const r = Math.floor(fy)
    const ty = fy - r
    for (let j = 0; j < m; j++) {
      const fx = j * step
      const c = Math.floor(fx)
      const tx = fx - c
      const rows = [-1, 0, 1, 2].map((dr) =>
        cubic(at(r + dr, c - 1), at(r + dr, c), at(r + dr, c + 1), at(r + dr, c + 2), tx),
      )
      out[i * m + j] = cubic(rows[0], rows[1], rows[2], rows[3], ty)
    }
  }
  return out
}

const AZIMUTH = (315 * Math.PI) / 180
const ALTITUDE = (45 * Math.PI) / 180
const SHADE_EXAGGERATION = 2

/** Hillshade (light from the north-west) tinted by height above the patch minimum. */
export function drawTerrain(canvas: HTMLCanvasElement, grid: PatchGrid, range: number): void {
  const m = grid.grid_n * 6
  const z = upsample(grid, m)
  const spacing = (grid.pixel_size_m * (grid.grid_n - 1)) / (m - 1)
  const lx = Math.sin(AZIMUTH) * Math.cos(ALTITUDE)
  const ly = Math.cos(AZIMUTH) * Math.cos(ALTITUDE)
  const lz = Math.sin(ALTITUDE)
  canvas.width = canvas.height = m
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  const img = ctx.createImageData(m, m)
  for (let i = 0; i < m; i++) {
    for (let j = 0; j < m; j++) {
      const i0 = Math.max(0, i - 1)
      const i1 = Math.min(m - 1, i + 1)
      const j0 = Math.max(0, j - 1)
      const j1 = Math.min(m - 1, j + 1)
      const dzdx = ((z[i * m + j1] - z[i * m + j0]) / ((j1 - j0) * spacing)) * SHADE_EXAGGERATION
      const dzdy = ((z[i1 * m + j] - z[i0 * m + j]) / ((i1 - i0) * spacing)) * SHADE_EXAGGERATION
      // Row 0 is north, so the northward slope is minus the row derivative.
      const nx = -dzdx
      const ny = dzdy
      const len = Math.hypot(nx, ny, 1)
      const shade = Math.max(0, (nx * lx + ny * ly + lz) / len) / lz
      const k = Math.min(1.3, 0.35 + 0.65 * shade)
      const [r, g, b] = rampColor((z[i * m + j] - grid.min_m) / range)
      const p = (i * m + j) * 4
      img.data[p] = Math.min(255, r * k)
      img.data[p + 1] = Math.min(255, g * k)
      img.data[p + 2] = Math.min(255, b * k)
      img.data[p + 3] = 255
    }
  }
  ctx.putImageData(img, 0, 0)
}

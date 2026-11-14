// Live map tiles for a 10 x 10 km patch. Nothing is stored locally: the browser pulls a handful of tiles per view.

export const PATCH_KM = 10
const MOON_KM_PER_DEG = 30.3382
const EARTH_CIRCUMFERENCE_M = 40075016.686
const TILE = 256

const MOON_MAX_ZOOM = 8
const EARTH_MAX_ZOOM = 17

const moonUrl = (z: number, x: number, y: number) =>
  `https://trek.nasa.gov/tiles/Moon/EQ/LRO_WAC_Mosaic_Global_303ppd_v02/1.0.0/default/default028mm/${z}/${y}/${x}.jpg`

const earthUrl = (z: number, x: number, y: number) =>
  `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/${z}/${y}/${x}`

type Tile = { img: HTMLImageElement; x: number; y: number }

function loadTile(url: string, x: number, y: number, signal: AbortSignal): Promise<Tile | null> {
  const attempt = (tries: number): Promise<Tile | null> =>
    new Promise((resolve) => {
      const img = new Image()
      img.crossOrigin = 'anonymous'
      img.decoding = 'async'
      const onAbort = () => {
        img.onload = img.onerror = null
        img.src = ''
        resolve(null)
      }
      signal.addEventListener('abort', onAbort, { once: true })
      img.onload = () => {
        signal.removeEventListener('abort', onAbort)
        resolve({ img, x, y })
      }
      img.onerror = () => {
        signal.removeEventListener('abort', onAbort)
        // NASA's tile server occasionally drops a connection; a short retry is enough.
        if (tries > 1 && !signal.aborted) setTimeout(() => attempt(tries - 1).then(resolve), 400)
        else resolve(null)
      }
      img.src = url
    })
  return attempt(3)
}

type View = {
  // Source window in world pixels at the chosen zoom.
  x0: number
  y0: number
  w: number
  h: number
  z: number
  cols: number
  rows: number
  wrapX: boolean
  url: (z: number, x: number, y: number) => string
}

function moonView(lat: number, lon: number): View {
  const z = MOON_MAX_ZOOM
  const cols = 2 ** (z + 1)
  const rows = 2 ** z
  const pxPerDeg = (TILE * rows) / 180
  const halfLat = PATCH_KM / 2 / MOON_KM_PER_DEG
  const halfLon = halfLat / Math.max(Math.cos((lat * Math.PI) / 180), 0.05)
  const cx = ((lon + 180) / 360) * cols * TILE
  const cy = ((90 - lat) / 180) * rows * TILE
  return {
    x0: cx - halfLon * pxPerDeg,
    y0: cy - halfLat * pxPerDeg,
    w: 2 * halfLon * pxPerDeg,
    h: 2 * halfLat * pxPerDeg,
    z,
    cols,
    rows,
    wrapX: true,
    url: moonUrl,
  }
}

function earthView(lat: number, lon: number, outputPx: number): View {
  const cosLat = Math.cos((lat * Math.PI) / 180)
  // Pick the zoom where one source pixel covers no more than one output pixel.
  const wantMetersPerPx = (PATCH_KM * 1000) / outputPx
  const z = Math.min(
    EARTH_MAX_ZOOM,
    Math.max(0, Math.ceil(Math.log2((EARTH_CIRCUMFERENCE_M / TILE) * cosLat / wantMetersPerPx))),
  )
  const n = 2 ** z
  const world = n * TILE
  const latRad = (lat * Math.PI) / 180
  const cx = ((lon + 180) / 360) * world
  const cy = ((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) * world
  const half = ((PATCH_KM * 1000) / 2 / (EARTH_CIRCUMFERENCE_M * cosLat)) * world
  return { x0: cx - half, y0: cy - half, w: 2 * half, h: 2 * half, z, cols: n, rows: n, wrapX: true, url: earthUrl }
}

export type Body = 'moon' | 'earth'

// The Moon mosaic covers a 10 km patch with about this many pixels at its best zoom.
const MOON_PATCH_PX = Math.round(((PATCH_KM / MOON_KM_PER_DEG) * TILE * 2 ** MOON_MAX_ZOOM) / 180)

/**
 * Draws the 10 x 10 km patch centred on lat/lon. Resolves false if no tile could be loaded.
 * With matchMoon, Earth is rendered at the Moon's pixel density so both patches show the same level of detail.
 */
export async function drawPatch(
  canvas: HTMLCanvasElement,
  body: Body,
  lat: number,
  lon: number,
  signal: AbortSignal,
  matchMoon = false,
): Promise<boolean> {
  const size = canvas.width
  const renderPx = body === 'earth' && matchMoon ? MOON_PATCH_PX : size
  const v = body === 'moon' ? moonView(lat, lon) : earthView(lat, lon, renderPx)
  const tx0 = Math.floor(v.x0 / TILE)
  const tx1 = Math.floor((v.x0 + v.w) / TILE)
  const ty0 = Math.max(0, Math.floor(v.y0 / TILE))
  const ty1 = Math.min(v.rows - 1, Math.floor((v.y0 + v.h) / TILE))

  const jobs: Promise<Tile | null>[] = []
  for (let ty = ty0; ty <= ty1; ty++) {
    for (let tx = tx0; tx <= tx1; tx++) {
      const wrapped = ((tx % v.cols) + v.cols) % v.cols
      jobs.push(loadTile(v.url(v.z, wrapped, ty), tx, ty, signal))
    }
  }
  const tiles = (await Promise.all(jobs)).filter((t): t is Tile => t !== null)
  if (signal.aborted || tiles.length === 0) return false

  const out = canvas.getContext('2d')
  if (!out) return false
  const target = renderPx === size ? canvas : document.createElement('canvas')
  target.width = target.height = renderPx
  const ctx = target.getContext('2d')
  if (!ctx) return false
  ctx.imageSmoothingEnabled = true
  ctx.imageSmoothingQuality = 'high'
  ctx.fillStyle = '#050f2b'
  ctx.fillRect(0, 0, renderPx, renderPx)
  const sx = renderPx / v.w
  const sy = renderPx / v.h
  for (const t of tiles) {
    // Round outwards so neighbouring tiles do not leave hairline seams.
    const dx = Math.floor((t.x * TILE - v.x0) * sx)
    const dy = Math.floor((t.y * TILE - v.y0) * sy)
    const dw = Math.ceil(TILE * sx) + 1
    const dh = Math.ceil(TILE * sy) + 1
    ctx.drawImage(t.img, dx, dy, dw, dh)
  }
  if (target !== canvas) {
    out.imageSmoothingEnabled = true
    out.imageSmoothingQuality = 'high'
    out.drawImage(target, 0, 0, size, size)
  }
  return true
}

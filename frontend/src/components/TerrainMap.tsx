import { useEffect, useRef, useState, type PointerEvent } from 'react'
import { drawTerrain } from '../terrain'
import type { GridState } from '../usePatchGrid'
import type { PatchGrid } from '../types'
import PatchFrame from './PatchFrame'

export type TerrainSide = { title: string; lat: number; lon: number; state: GridState }

function TerrainCanvas({ grid, range, label }: { grid: PatchGrid; range: number; label: string }) {
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    if (ref.current) drawTerrain(ref.current, grid, range)
  }, [grid, range])
  return <canvas ref={ref} role="img" aria-label={label} />
}

const heightAt = (grid: PatchGrid, u: number, v: number) => {
  const n = grid.grid_n
  const col = Math.min(n - 1, Math.max(0, Math.round(u * (n - 1))))
  const row = Math.min(n - 1, Math.max(0, Math.round(v * (n - 1))))
  return grid.heights_m[row][col] - grid.min_m
}

export default function TerrainMap({ moon, earth, range }: { moon: TerrainSide; earth: TerrainSide; range: number }) {
  const [cursor, setCursor] = useState<{ u: number; v: number } | null>(null)

  const track = (e: PointerEvent<HTMLElement>) => {
    const r = e.currentTarget.getBoundingClientRect()
    setCursor({ u: (e.clientX - r.left) / r.width, v: (e.clientY - r.top) / r.height })
  }

  return (
    <>
      {(['moon', 'earth'] as const).map((body) => {
        const side = body === 'moon' ? moon : earth
        const { grid, status, retry } = side.state
        return (
          <PatchFrame
            key={body}
            body={body}
            title={side.title}
            lat={side.lat}
            lon={side.lon}
            status={status}
            loadingText="Loading terrain"
            errorText="Terrain data is unavailable. Check that the API is running."
            onRetry={retry}
            onPointerMove={track}
            onPointerLeave={() => setCursor(null)}
          >
            {grid && <TerrainCanvas grid={grid} range={range} label={`${side.title} terrain, 10 by 10 kilometres`} />}
            {grid && cursor && (
              <>
                <span className="cross-v" style={{ left: `${cursor.u * 100}%` }} />
                <span className="cross-h" style={{ top: `${cursor.v * 100}%` }} />
                <span className="readout">{Math.round(heightAt(grid, cursor.u, cursor.v)).toLocaleString('en-US')} m</span>
              </>
            )}
          </PatchFrame>
        )
      })}
    </>
  )
}

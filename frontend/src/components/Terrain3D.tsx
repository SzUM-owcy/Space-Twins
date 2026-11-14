import { useEffect, useMemo, useRef, type ComponentRef } from 'react'
import { Canvas, useThree } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import * as THREE from 'three'
import { rampColor } from '../terrain'
import type { PatchGrid } from '../types'
import PatchFrame from './PatchFrame'
import type { TerrainSide } from './TerrainMap'

type Controls = ComponentRef<typeof OrbitControls>
type View = { camera: THREE.Camera; controls: Controls }
type Registry = { views: Set<View>; busy: boolean }

// Positions are in kilometres: x east, z south, y up (heights are scaled by the chosen exaggeration).
function terrainGeometry(grid: PatchGrid, range: number) {
  const n = grid.grid_n
  const sizeKm = grid.size_m / 1000
  const geo = new THREE.PlaneGeometry(sizeKm, sizeKm, n - 1, n - 1)
  const pos = geo.attributes.position
  const colors = new Float32Array(pos.count * 3)
  const tint = new THREE.Color()
  for (let i = 0; i < pos.count; i++) {
    const h = grid.heights_m[Math.floor(i / n)][i % n] - grid.min_m
    const [r, g, b] = rampColor(h / range)
    pos.setXYZ(i, pos.getX(i), h / 1000, -pos.getY(i))
    // Convert from sRGB so lighting does not wash the tints out.
    tint.setRGB(r / 255, g / 255, b / 255, THREE.SRGBColorSpace)
    colors.set([tint.r, tint.g, tint.b], i * 3)
  }
  geo.setAttribute('color', new THREE.BufferAttribute(colors, 3))
  geo.computeVertexNormals()
  return geo
}

function Terrain({ grid, range, exaggeration }: { grid: PatchGrid; range: number; exaggeration: number }) {
  const geo = useMemo(() => terrainGeometry(grid, range), [grid, range])
  const outline = useMemo(() => {
    const h = grid.size_m / 2000
    const pts = [new THREE.Vector3(-h, 0, -h), new THREE.Vector3(h, 0, -h), new THREE.Vector3(h, 0, h), new THREE.Vector3(-h, 0, h)]
    return new THREE.BufferGeometry().setFromPoints(pts)
  }, [grid])
  useEffect(() => () => geo.dispose(), [geo])
  return (
    <>
      <mesh geometry={geo} scale={[1, exaggeration, 1]}>
        <meshStandardMaterial vertexColors roughness={1} metalness={0} />
      </mesh>
      <lineLoop geometry={outline}>
        <lineBasicMaterial color="#ffffff" transparent opacity={0.45} />
      </lineLoop>
    </>
  )
}

// Both views share one camera: moving either one moves the other.
function LinkedControls({ registry }: { registry: Registry }) {
  const camera = useThree((s) => s.camera)
  const ref = useRef<Controls>(null)

  useEffect(() => {
    const view = { camera, controls: ref.current! }
    registry.views.add(view)
    return () => {
      registry.views.delete(view)
    }
  }, [camera, registry])

  const onChange = () => {
    const me = ref.current
    if (!me || registry.busy) return
    registry.busy = true
    registry.views.forEach((v) => {
      if (v.controls === me) return
      v.camera.position.copy(camera.position)
      v.controls.target.copy(me.target)
      v.controls.update()
    })
    registry.busy = false
  }

  return (
    <OrbitControls
      ref={ref}
      target={[0, 0.6, 0]}
      enablePan={false}
      enableDamping={false}
      rotateSpeed={0.6}
      minDistance={10}
      maxDistance={40}
      maxPolarAngle={1.45}
      onChange={onChange}
    />
  )
}

export default function Terrain3D({
  moon,
  earth,
  range,
  exaggeration,
}: {
  moon: TerrainSide
  earth: TerrainSide
  range: number
  exaggeration: number
}) {
  const registry = useRef<Registry>({ views: new Set(), busy: false })
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
            showScale={false}
          >
            {grid && (
              <Canvas camera={{ position: [12, 10, 14], fov: 38, near: 0.1, far: 200 }} dpr={[1, 2]} aria-label={`${side.title} terrain in 3D`}>
                <ambientLight intensity={0.7} />
                <directionalLight position={[-9, 7, 5]} intensity={1.8} />
                <Terrain grid={grid} range={range} exaggeration={exaggeration} />
                <LinkedControls registry={registry.current} />
              </Canvas>
            )}
          </PatchFrame>
        )
      })}
    </>
  )
}

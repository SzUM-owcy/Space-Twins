import { Suspense, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type RefObject } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Html, Line, OrbitControls, useTexture } from '@react-three/drei'
import * as THREE from 'three'
import { COLORS, GROUP_COLOR, type DisplaySite, type GroupId } from '../sites'
import type { Analog } from '../types'

const FOV = 32
const reducedMotion = typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

// NASA CGI Moon Kit maps are equirectangular with longitude 0 at the image centre, east to the right.
function surfacePoint(lat: number, lon: number, r = 1): THREE.Vector3 {
  const la = THREE.MathUtils.degToRad(lat)
  const lo = THREE.MathUtils.degToRad(lon)
  return new THREE.Vector3(r * Math.cos(la) * Math.cos(lo), r * Math.sin(la), -r * Math.cos(la) * Math.sin(lo))
}

function MoonBody({ meshRef, onReady }: { meshRef: RefObject<THREE.Mesh | null>; onReady: () => void }) {
  const gl = useThree((s) => s.gl)
  const [color, height] = useTexture(['/textures/moon_color_4k.jpg', '/textures/moon_height.jpg'])

  useLayoutEffect(() => {
    color.colorSpace = THREE.SRGBColorSpace
    color.anisotropy = gl.capabilities.getMaxAnisotropy()
    color.needsUpdate = true
    onReady()
  }, [color, gl, onReady])

  // Stops pointer events from reaching markers on the far side of the Moon.
  const block = (e: { stopPropagation: () => void }) => e.stopPropagation()

  return (
    <mesh ref={meshRef} onPointerOver={block} onPointerMove={block} onClick={block}>
      <sphereGeometry args={[1, 160, 80]} />
      <meshStandardMaterial map={color} bumpMap={height} bumpScale={2.2} roughness={1} metalness={0} />
    </mesh>
  )
}

// Light is tied to the camera so the terminator stays in the same place while the Moon turns.
function Sun() {
  const ref = useRef<THREE.DirectionalLight>(null)
  const offset = useMemo(() => new THREE.Vector3(-4, 2.4, 3), [])
  useFrame(({ camera }) => {
    ref.current?.position.copy(offset).applyQuaternion(camera.quaternion)
  })
  return <directionalLight ref={ref} intensity={3.1} color="#fff4e6" />
}

function Graticule() {
  const positions = useMemo(() => {
    const pts: number[] = []
    const push = (a: THREE.Vector3, b: THREE.Vector3) => pts.push(a.x, a.y, a.z, b.x, b.y, b.z)
    const r = 1.0012
    for (let lat = -60; lat <= 60; lat += 30) {
      for (let lon = 0; lon < 360; lon += 4) push(surfacePoint(lat, lon, r), surfacePoint(lat, lon + 4, r))
    }
    for (let lon = -180; lon < 180; lon += 30) {
      for (let lat = -88; lat < 88; lat += 4) push(surfacePoint(lat, lon, r), surfacePoint(Math.min(lat + 4, 88), lon, r))
    }
    return new Float32Array(pts)
  }, [])
  return (
    <lineSegments>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <lineBasicMaterial color="#ffffff" transparent opacity={0.07} depthWrite={false} />
    </lineSegments>
  )
}

type MarkerState = 'idle' | 'hover' | 'selected'

// Switch between 'flag' (pole with a flag standing on the surface) and 'square' (outline lying on the surface).
const MARKER_STYLE = { value: 'square' as 'flag' | 'square' }

type MarkerProps = {
  site: DisplaySite
  state: MarkerState
  index: number
  moonRef: RefObject<THREE.Mesh | null>
  onHover: (id: string | null) => void
  onSelect: (id: string) => void
}

function pointerHandlers(site: DisplaySite, onHover: MarkerProps['onHover'], onSelect: MarkerProps['onSelect']) {
  return {
    onPointerOver: (e: { stopPropagation: () => void }) => {
      e.stopPropagation()
      onHover(site.id)
      document.body.style.cursor = 'pointer'
    },
    onPointerOut: () => {
      onHover(null)
      document.body.style.cursor = ''
    },
    onClick: (e: { stopPropagation: () => void }) => {
      e.stopPropagation()
      onSelect(site.id)
    },
  }
}

function squarePoints(h: number): [number, number, number][] {
  return [[-h, -h, 0], [h, -h, 0], [h, h, 0], [-h, h, 0], [-h, -h, 0]]
}

function circlePoints(r: number, n = 48): [number, number, number][] {
  return Array.from({ length: n + 1 }, (_, i) => [r * Math.cos((i / n) * Math.PI * 2), r * Math.sin((i / n) * Math.PI * 2), 0])
}

function Pulse({ points }: { points: [number, number, number][] }) {
  const ref = useRef<{ scale: THREE.Vector3; material: THREE.Material & { opacity: number } } | null>(null)
  useFrame(({ clock }) => {
    const node = ref.current
    if (!node) return
    const k = (clock.elapsedTime % 2) / 2
    node.scale.setScalar(1 + k * 1.3)
    node.material.opacity = (1 - k) * 0.85
  })
  return <Line ref={ref as never} points={points} color={COLORS.signal} lineWidth={2} transparent opacity={0.85} depthWrite={false} renderOrder={3} />
}

function SquareMarker({ site, state, moonRef, onHover, onSelect }: MarkerProps) {
  const group = useRef<THREE.Group>(null)
  const normal = useMemo(() => surfacePoint(site.lat, site.lon, 1), [site.lat, site.lon])

  useLayoutEffect(() => {
    const g = group.current
    if (!g) return
    g.position.copy(normal).multiplyScalar(1.004)
    g.lookAt(normal.clone().multiplyScalar(2))
  }, [normal])

  const active = state !== 'idle'
  const h = state === 'selected' ? 0.04 : state === 'hover' ? 0.036 : 0.026
  const color = state === 'selected' ? COLORS.signal : GROUP_COLOR[site.group]
  const points = useMemo(() => squarePoints(h), [h])

  return (
    <group ref={group}>
      <Line points={points} color={COLORS.void} lineWidth={4.5} transparent opacity={0.6} depthWrite={false} renderOrder={1} />
      <Line points={points} color={color} lineWidth={state === 'selected' ? 2.6 : 2} transparent depthWrite={false} renderOrder={2} />
      {state === 'selected' && <Pulse points={points} />}
      {active && (
        <>
          <Line points={[[0, 0, 0], [0, 0, 0.2]]} color={color} lineWidth={1.5} transparent depthWrite={false} renderOrder={2} />
          <Html position={[0, 0, 0.22]} center occlude={[moonRef as RefObject<THREE.Object3D>]} style={{ pointerEvents: 'none' }}>
            <span className={`tag${state === 'selected' ? ' tag-selected' : ''}`}>{site.name}</span>
          </Html>
        </>
      )}
      <mesh {...pointerHandlers(site, onHover, onSelect)}>
        <planeGeometry args={[0.15, 0.15]} />
        <meshBasicMaterial transparent opacity={0} depthWrite={false} />
      </mesh>
    </group>
  )
}

const POLE_H = 0.155
const FLAG_W = 0.1
const FLAG_H = 0.057
const CLOTH_TILT = 0.55
const RING = circlePoints(0.03)
const PLANT_DELAY = 1.3 // flags are planted while the camera is still moving in

type Emblem = 'star' | 'peak' | 'tile'
type Fabric = { color: string; ink: string }

const FABRIC: Record<GroupId, Fabric> = {
  apollo: { color: COLORS.rocket, ink: '#ffffff' },
  pole: { color: COLORS.yonder, ink: COLORS.void },
  terrain: { color: '#eaf1ff', ink: COLORS.void },
}
const SELECTED_FABRIC: Fabric = { color: COLORS.signal, ink: COLORS.void }
const EMBLEM: Record<GroupId, Emblem> = { apollo: 'star', pole: 'peak', terrain: 'tile' }

const easeOutCubic = (t: number) => 1 - Math.pow(1 - t, 3)
const easeOutBack = (t: number) => 1 + 2.4 * Math.pow(t - 1, 3) + 1.4 * Math.pow(t - 1, 2)
const tint = (hex: string, f: number) => `#${new THREE.Color(hex).multiplyScalar(f).getHexString()}`

const clothCache = new Map<string, THREE.CanvasTexture>()

// Swallow-tailed pennant painted on a canvas: woven texture, folded-edge highlight, emblem near the pole.
function clothTexture(fabric: Fabric, emblem: Emblem): THREE.CanvasTexture {
  const key = `${fabric.color}|${fabric.ink}|${emblem}`
  const cached = clothCache.get(key)
  if (cached) return cached

  const W = 512
  const H = 256
  const canvas = document.createElement('canvas')
  canvas.width = W
  canvas.height = H
  const g = canvas.getContext('2d')!

  g.beginPath()
  g.moveTo(0, 0)
  g.lineTo(W, H * 0.14)
  g.lineTo(W * 0.78, H * 0.5)
  g.lineTo(W, H * 0.86)
  g.lineTo(0, H)
  g.closePath()
  g.save()
  g.clip()

  const base = g.createLinearGradient(0, 0, W, 0)
  base.addColorStop(0, tint(fabric.color, 1.08))
  base.addColorStop(1, tint(fabric.color, 0.78))
  g.fillStyle = base
  g.fillRect(0, 0, W, H)

  g.fillStyle = 'rgba(255,255,255,0.06)'
  for (let x = 0; x < W; x += 4) g.fillRect(x, 0, 1, H)
  g.fillStyle = 'rgba(0,0,0,0.07)'
  for (let y = 0; y < H; y += 4) g.fillRect(0, y, W, 1)

  g.fillStyle = 'rgba(0,0,0,0.28)'
  g.fillRect(0, 0, 16, H) // sleeve the pole runs through

  const cx = W * 0.27
  const cy = H * 0.5
  const s = H * 0.2
  g.fillStyle = fabric.ink
  g.strokeStyle = fabric.ink
  g.lineWidth = 9
  g.lineJoin = 'round'
  if (emblem === 'star') {
    g.beginPath()
    for (let i = 0; i < 10; i++) {
      const r = i % 2 === 0 ? s * 1.15 : s * 0.48
      const a = -Math.PI / 2 + (i * Math.PI) / 5
      g[i === 0 ? 'moveTo' : 'lineTo'](cx + r * Math.cos(a), cy + r * Math.sin(a))
    }
    g.closePath()
    g.fill()
  } else if (emblem === 'peak') {
    g.beginPath()
    g.moveTo(cx - s * 1.1, cy + s * 0.85)
    g.lineTo(cx, cy - s * 1.0)
    g.lineTo(cx + s * 1.1, cy + s * 0.85)
    g.closePath()
    g.fill()
  } else {
    g.strokeRect(cx - s, cy - s, s * 2, s * 2)
    g.fillRect(cx - s * 0.35, cy - s * 0.35, s * 0.7, s * 0.7)
  }

  g.restore()
  g.beginPath()
  g.moveTo(0, 0)
  g.lineTo(W, H * 0.14)
  g.lineTo(W * 0.78, H * 0.5)
  g.lineTo(W, H * 0.86)
  g.lineTo(0, H)
  g.closePath()
  g.lineWidth = 7
  g.strokeStyle = 'rgba(255,255,255,0.28)'
  g.stroke()

  const tex = new THREE.CanvasTexture(canvas)
  tex.colorSpace = THREE.SRGBColorSpace
  tex.anisotropy = 8
  clothCache.set(key, tex)
  return tex
}

let shadowTexture: THREE.CanvasTexture | null = null

function contactShadow(): THREE.CanvasTexture {
  if (shadowTexture) return shadowTexture
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = 128
  const g = canvas.getContext('2d')!
  const grad = g.createRadialGradient(64, 64, 0, 64, 64, 64)
  grad.addColorStop(0, 'rgba(0,0,0,0.6)')
  grad.addColorStop(1, 'rgba(0,0,0,0)')
  g.fillStyle = grad
  g.fillRect(0, 0, 128, 128)
  shadowTexture = new THREE.CanvasTexture(canvas)
  return shadowTexture
}

// Cloth with a slow travelling ripple, anchored at the pole.
function Cloth({ fabric, emblem, phase, glow }: { fabric: Fabric; emblem: Emblem; phase: number; glow: number }) {
  const tex = useMemo(() => clothTexture(fabric, emblem), [fabric, emblem])
  const geo = useMemo(() => {
    const g = new THREE.PlaneGeometry(FLAG_W, FLAG_H, 22, 8)
    g.translate(FLAG_W / 2, -FLAG_H / 2, 0)
    return g
  }, [])
  const rest = useMemo(() => Float32Array.from(geo.attributes.position.array), [geo])

  useFrame(({ clock }) => {
    const t = reducedMotion ? 0 : clock.elapsedTime
    const pos = geo.attributes.position
    for (let i = 0; i < pos.count; i++) {
      const u = Math.max(0, rest[i * 3] / FLAG_W)
      const fold = Math.sin(u * 7 - t * 1.5 + phase) * 0.62 + Math.sin(u * 13 - t * 2.2 + phase * 1.7) * 0.24
      pos.setZ(i, 0.013 * Math.pow(u, 1.25) * fold)
    }
    pos.needsUpdate = true
    geo.computeVertexNormals()
  })

  return (
    <mesh geometry={geo} rotation={[Math.PI / 2, 0, 0]}>
      <meshStandardMaterial
        map={tex}
        emissiveMap={tex}
        emissive="#ffffff"
        emissiveIntensity={glow}
        color="#c4c4c4"
        alphaTest={0.5}
        alphaToCoverage
        side={THREE.DoubleSide}
        roughness={0.92}
        metalness={0}
      />
    </mesh>
  )
}

// A flag planted on the surface. It is a real 3D object, so it foreshortens as the Moon turns.
function FlagMarker({ site, state, index, moonRef, onHover, onSelect }: MarkerProps) {
  const group = useRef<THREE.Group>(null)
  const inner = useRef<THREE.Group>(null)
  const cloth = useRef<THREE.Group>(null)
  const pop = useRef(1)
  const normal = useMemo(() => surfacePoint(site.lat, site.lon, 1), [site.lat, site.lon])
  const shadow = useMemo(() => contactShadow(), [])

  useLayoutEffect(() => {
    const g = group.current
    if (!g) return
    g.position.copy(normal).multiplyScalar(0.999)
    g.lookAt(normal.clone().multiplyScalar(2))
  }, [normal])

  const targetScale = state === 'selected' ? 1.45 : state === 'hover' ? 1.2 : 1
  useFrame(({ clock }, dt) => {
    const g = inner.current
    const c = cloth.current
    if (!g || !c) return
    const start = reducedMotion ? -10 : PLANT_DELAY + index * 0.07
    const rise = easeOutBack(THREE.MathUtils.clamp((clock.elapsedTime - start) / 0.8, 0, 1))
    const unfurl = easeOutCubic(THREE.MathUtils.clamp((clock.elapsedTime - start - 0.35) / 0.7, 0, 1))
    pop.current = THREE.MathUtils.lerp(pop.current, targetScale, 1 - Math.exp(-Math.min(dt, 1 / 30) * 14))
    g.scale.set(pop.current, pop.current, Math.max(0.001, pop.current * rise))
    c.scale.set(Math.max(0.001, unfurl), 1, 1)
  })

  const fabric = state === 'selected' ? SELECTED_FABRIC : FABRIC[site.group]

  return (
    <group ref={group}>
      <mesh position={[0.008, 0, 0.0008]}>
        <planeGeometry args={[0.075, 0.075]} />
        <meshBasicMaterial map={shadow} transparent depthWrite={false} polygonOffset polygonOffsetFactor={-1} polygonOffsetUnits={-1} />
      </mesh>
      {state === 'selected' && <Pulse points={RING} />}
      <group ref={inner} scale={[1, 1, 0.001]}>
        <mesh position={[0, 0, 0.0025]} rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[0.009, 0.012, 0.005, 18]} />
          <meshStandardMaterial color="#2a3550" roughness={0.6} metalness={0.3} />
        </mesh>
        <mesh position={[0, 0, POLE_H / 2]} rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[0.0017, 0.0027, POLE_H, 10]} />
          <meshStandardMaterial color="#cfd8ec" roughness={0.4} metalness={0.35} emissive="#cfd8ec" emissiveIntensity={0.18} />
        </mesh>
        <mesh position={[0, 0, POLE_H + 0.002]}>
          <sphereGeometry args={[0.0048, 14, 10]} />
          <meshStandardMaterial color="#f4f7ff" roughness={0.3} metalness={0.4} emissive="#f4f7ff" emissiveIntensity={0.25} />
        </mesh>
        {/* Cloth tilted away from vertical so it stays visible when seen from straight above. */}
        <group ref={cloth} position={[0.0012, 0, POLE_H - 0.002]} rotation={[CLOTH_TILT, 0, 0]}>
          <Cloth fabric={fabric} emblem={EMBLEM[site.group]} phase={index * 1.7} glow={state === 'selected' ? 0.95 : 0.55} />
        </group>
        {state !== 'idle' && (
          <Html position={[FLAG_W / 2, 0, POLE_H]} occlude={[moonRef as RefObject<THREE.Object3D>]} style={{ pointerEvents: 'none' }}>
            <span className={`tag tag-up${state === 'selected' ? ' tag-selected' : ''}`}>{site.name}</span>
          </Html>
        )}
        <mesh position={[0.03, 0, POLE_H / 2]} {...pointerHandlers(site, onHover, onSelect)}>
          <sphereGeometry args={[0.08, 8, 8]} />
          <meshBasicMaterial transparent opacity={0} depthWrite={false} />
        </mesh>
      </group>
    </group>
  )
}

const SiteMarker = MARKER_STYLE.value === 'flag' ? FlagMarker : SquareMarker

// Moon size follows the free space between the side columns on desktop and the stage on mobile.
function useBaseDistance(): number {
  const size = useThree((s) => s.size)
  const desktop = size.width >= 960
  const moonPx = Math.max(240, desktop ? Math.min(size.height * 0.8, size.width - 760) : Math.min(size.width - 48, size.height * 0.78))
  return size.height / (moonPx * Math.tan(THREE.MathUtils.degToRad(FOV / 2)))
}

const easeInOut = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2)

type Flight = { from: THREE.Vector3; fromLen: number; swing: THREE.Quaternion; angle: number; elapsed: number; duration: number }

function CameraRig({
  selected,
  baseDistance,
  paused,
  introDone,
}: {
  selected: DisplaySite | null
  baseDistance: number
  paused: boolean
  introDone: RefObject<boolean>
}) {
  const camera = useThree((s) => s.camera)
  const target = useRef<THREE.Vector3 | null>(null)
  const flight = useRef<Flight | null>(null)
  const intro = useRef(reducedMotion || introDone.current ? 1 : 0)
  const base = useRef(baseDistance)
  const prevBase = useRef(baseDistance)
  const tmp = useMemo(() => ({ dir: new THREE.Vector3(), q: new THREE.Quaternion(), id: new THREE.Quaternion() }), [])

  useEffect(() => {
    base.current = baseDistance
  }, [baseDistance])

  useEffect(() => {
    flight.current = null
    if (!selected) {
      target.current = null
      return
    }
    const d = surfacePoint(selected.lat, selected.lon, 1)
    d.y = THREE.MathUtils.clamp(d.y, -0.94, 0.94)
    target.current = d.normalize()
    if (reducedMotion) camera.position.copy(target.current).multiplyScalar(base.current * 0.95)
  }, [selected, camera])

  useEffect(() => {
    if (prevBase.current !== baseDistance && intro.current >= 1 && !flight.current) camera.position.setLength(baseDistance)
    prevBase.current = baseDistance
  }, [baseDistance, camera])

  useFrame((_, rawDt) => {
    const dt = Math.min(rawDt, 1 / 30) // a slow frame must not turn into a visible jump
    if (intro.current < 1) {
      intro.current = Math.min(1, intro.current + dt / 2.6)
      const e = 1 - Math.pow(1 - intro.current, 3)
      camera.position.setLength(THREE.MathUtils.lerp(base.current * 1.9, base.current, e))
      if (intro.current >= 1) introDone.current = true
      return
    }
    if (reducedMotion) return

    if (target.current && !flight.current) {
      const from = camera.position.clone().normalize()
      const angle = from.angleTo(target.current)
      flight.current = {
        from,
        fromLen: camera.position.length(),
        swing: new THREE.Quaternion().setFromUnitVectors(from, target.current),
        angle,
        elapsed: 0,
        duration: THREE.MathUtils.clamp(0.9 + angle * 0.5, 0.9, 2.2),
      }
      target.current = null
    }

    const f = flight.current
    if (!f) return
    f.elapsed += dt
    const t = Math.min(1, f.elapsed / f.duration)
    const e = easeInOut(t)
    tmp.q.copy(tmp.id).slerp(f.swing, e)
    tmp.dir.copy(f.from).applyQuaternion(tmp.q)
    const len = THREE.MathUtils.lerp(f.fromLen, base.current * 0.95, e)
    camera.position.copy(tmp.dir).multiplyScalar(len)
    if (t >= 1) flight.current = null
  })

  return (
    <OrbitControls
      makeDefault
      enablePan={false}
      enableDamping
      dampingFactor={0.07}
      rotateSpeed={0.55}
      zoomSpeed={0.6}
      minDistance={baseDistance * 0.5}
      maxDistance={baseDistance * 1.7}
      autoRotate={!paused && !reducedMotion}
      autoRotateSpeed={0.35}
      onStart={() => {
        target.current = null
        flight.current = null
      }}
    />
  )
}

type Phase = 'moon' | 'to-pair' | 'pair' | 'to-moon'

const EARTH_R = 2.2 // not to scale: the real Earth is 3.7 Moon radii and 30 Earth diameters away
const EARTH_GAP = 1
const UP = new THREE.Vector3(0, 1, 0)

const noRaycast = () => null

function EarthBody({ meshRef, active }: { meshRef: RefObject<THREE.Mesh | null>; active: boolean }) {
  const gl = useThree((s) => s.gl)
  const color = useTexture('/textures/earth_color_2k.jpg')

  useLayoutEffect(() => {
    color.colorSpace = THREE.SRGBColorSpace
    color.anisotropy = gl.capabilities.getMaxAnisotropy()
    color.needsUpdate = true
  }, [color, gl])

  const block = (e: { stopPropagation: () => void }) => e.stopPropagation()

  return (
    <>
      {/* Raycasting ignores `visible`, so a hidden Earth must be taken out of picking explicitly or it covers the Moon. */}
      <mesh ref={meshRef} raycast={active ? THREE.Mesh.prototype.raycast : noRaycast} onPointerOver={block} onPointerMove={block} onClick={block}>
        <sphereGeometry args={[1, 128, 64]} />
        <meshStandardMaterial map={color} color="#c9c9c9" roughness={0.9} metalness={0} />
      </mesh>
      <mesh>
        <sphereGeometry args={[1.08, 64, 32]} />
        <shaderMaterial
          side={THREE.BackSide}
          transparent
          depthWrite={false}
          blending={THREE.AdditiveBlending}
          vertexShader={`varying vec3 vN; void main(){ vN = normalize(normalMatrix * normal); gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`}
          fragmentShader={`varying vec3 vN; void main(){ float f = clamp(-vN.z / 0.38, 0.0, 1.0); gl_FragColor = vec4(0.18, 0.5, 0.95, 1.0) * pow(f, 2.2) * 0.6; }`}
        />
      </mesh>
    </>
  )
}

type PinProps = {
  analog: Analog
  state: MarkerState
  earthRef: RefObject<THREE.Mesh | null>
  onHover: (rank: number | null) => void
  onSelect: (rank: number) => void
}

function EarthPin({ analog, state, earthRef, onHover, onSelect }: PinProps) {
  const group = useRef<THREE.Group>(null)
  const normal = useMemo(() => surfacePoint(analog.lat, analog.lon, 1), [analog.lat, analog.lon])

  useLayoutEffect(() => {
    const g = group.current
    if (!g) return
    g.position.copy(normal).multiplyScalar(1.004)
    g.quaternion.setFromRotationMatrix(new THREE.Matrix4().lookAt(normal.clone().multiplyScalar(2), normal, UP))
  }, [normal])

  const active = state !== 'idle'
  const h = state === 'selected' ? 0.04 : state === 'hover' ? 0.036 : 0.026
  const color = state === 'selected' ? COLORS.signal : COLORS.white
  const points = useMemo(() => squarePoints(h), [h])
  const handlers = {
    onPointerOver: (e: { stopPropagation: () => void }) => {
      e.stopPropagation()
      onHover(analog.rank)
      document.body.style.cursor = 'pointer'
    },
    onPointerOut: () => {
      onHover(null)
      document.body.style.cursor = ''
    },
    onClick: (e: { stopPropagation: () => void }) => {
      e.stopPropagation()
      onSelect(analog.rank)
    },
  }

  return (
    <group ref={group}>
      <Line points={points} color={COLORS.void} lineWidth={4.5} transparent opacity={0.6} depthWrite={false} renderOrder={1} />
      <Line points={points} color={color} lineWidth={state === 'selected' ? 2.6 : 2} transparent depthWrite={false} renderOrder={2} />
      {state === 'selected' && <Pulse points={points} />}
      <Line points={[[0, 0, 0], [0, 0, 0.12]]} color={color} lineWidth={1.5} transparent depthWrite={false} renderOrder={2} />
      <Html position={[0, 0, 0.13]} center occlude={[earthRef as RefObject<THREE.Object3D>]} style={{ pointerEvents: 'none' }}>
        <span className={`tag pin${state === 'selected' ? ' tag-selected' : ''}`}>
          <b>{analog.rank}</b>
          {active && ` ${analog.region_name}`}
        </span>
      </Html>
      <mesh {...handlers}>
        <planeGeometry args={[0.15, 0.15]} />
        <meshBasicMaterial transparent opacity={0} depthWrite={false} />
      </mesh>
    </group>
  )
}

type EarthPose = { yaw: [number, number]; tilt: [number, number] }

type Anim = {
  t: number
  duration: number
  camFrom: THREE.Vector3
  camTo: THREE.Vector3
  lookFrom: THREE.Vector3
  lookTo: THREE.Vector3
  moonFrom: THREE.Quaternion
  moonTo: THREE.Quaternion
  earth: EarthPose | null
  end: Phase
}

type Settle = { moonFrom: THREE.Quaternion; moonTo: THREE.Quaternion; earth: EarthPose; t: number; duration: number }

// Rotation that brings a point of a body to face the camera, keeping the body's current orientation otherwise.
function faceQuaternion(current: THREE.Quaternion, normal: THREE.Vector3, bodyPos: THREE.Vector3, camPos: THREE.Vector3) {
  const now = normal.clone().applyQuaternion(current)
  const want = camPos.clone().sub(bodyPos).normalize()
  return new THREE.Quaternion().setFromUnitVectors(now, want).multiply(current)
}

const wrapPi = (a: number) => a - Math.PI * 2 * Math.round(a / (Math.PI * 2))
const MAX_TILT = 1.4

type EarthFrame = { align: THREE.Quaternion; right: THREE.Vector3; earthPos: THREE.Vector3; camPair: THREE.Vector3 }

// The Earth turns like a turntable: it spins about its polar axis (yaw) and tips towards or away from the viewer (tilt),
// so the north pole always stays in the vertical plane through the view and never rolls sideways.
function earthFrame(camPair: THREE.Vector3, mid: THREE.Vector3, earthPos: THREE.Vector3): EarthFrame {
  const view = new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().lookAt(camPair, mid, UP))
  return {
    align: new THREE.Quaternion().setFromUnitVectors(UP, UP.clone().applyQuaternion(view)),
    right: new THREE.Vector3(1, 0, 0).applyQuaternion(view),
    earthPos,
    camPair,
  }
}

// Spin and tilt that turn a place on the Earth towards the camera, taking the shortest way round from the current spin.
function earthPoseFor(f: EarthFrame, normal: THREE.Vector3, currentYaw: number, currentTilt: number): EarthPose {
  const face = f.camPair.clone().sub(f.earthPos).normalize()
  const local = face.clone().applyQuaternion(f.align.clone().invert())
  const yaw = currentYaw + wrapPi(Math.atan2(local.x, local.z) - Math.atan2(normal.x, normal.z) - currentYaw)
  const spun = normal.clone().applyQuaternion(f.align.clone().multiply(new THREE.Quaternion().setFromAxisAngle(UP, yaw)))
  const flat = (v: THREE.Vector3) => v.clone().addScaledVector(f.right, -v.dot(f.right))
  const a = flat(spun)
  const b = flat(face)
  const tilt = THREE.MathUtils.clamp(Math.atan2(a.clone().cross(b).dot(f.right), a.dot(b)), -MAX_TILT, MAX_TILT)
  return { yaw: [currentYaw, yaw], tilt: [currentTilt, tilt] }
}

type RigProps = {
  phase: Phase
  onPhase: (p: Phase) => void
  moonGroup: RefObject<THREE.Group | null>
  earthGroup: RefObject<THREE.Group | null>
  moonNormal: THREE.Vector3 | null
  earthNormal: THREE.Vector3 | null
}

// Moves the camera between the Moon view and the Moon + Earth view, and in the pair view lets one drag spin both bodies together.
function PairRig({ phase, onPhase, moonGroup, earthGroup, moonNormal, earthNormal }: RigProps) {
  const camera = useThree((s) => s.camera)
  const gl = useThree((s) => s.gl)
  const size = useThree((s) => s.size)
  const anim = useRef<Anim | null>(null)
  const settle = useRef<Settle | null>(null)
  const look = useRef(new THREE.Vector3())
  const saved = useRef<{ camMoon: THREE.Vector3; frame: EarthFrame } | null>(null)
  const pose = useRef({ yaw: 0, tilt: 0 })
  const spin = useRef({ active: false, dx: 0, dy: 0, vx: 0, vy: 0 })
  const tmp = useMemo(
    () => ({ right: new THREE.Vector3(), up: new THREE.Vector3(), q: new THREE.Quaternion(), qa: new THREE.Quaternion(), qy: new THREE.Quaternion() }),
    [],
  )

  const applyEarth = (earth: THREE.Group, f: EarthFrame, yaw: number, tilt: number) => {
    pose.current.yaw = yaw
    pose.current.tilt = tilt
    earth.quaternion.setFromAxisAngle(f.right, tilt).multiply(f.align).multiply(tmp.qy.setFromAxisAngle(UP, yaw))
  }

  // A new phase starts a camera move.
  useEffect(() => {
    const moon = moonGroup.current
    const earth = earthGroup.current
    if (!moon || !earth) return
    settle.current = null

    if (phase === 'to-pair') {
      const c = camera.position.clone().normalize()
      const right = new THREE.Vector3(1, 0, 0).applyQuaternion(camera.quaternion)
      right.addScaledVector(c, -right.dot(c)).normalize()
      const d = 1 + EARTH_GAP + EARTH_R
      const earthPos = right.clone().multiplyScalar(d)
      const mid = right.clone().multiplyScalar((d + EARTH_R - 1) / 2)
      const usable = Math.max(360, size.width - 760)
      const pxPerUnit = Math.min(usable / ((2 + EARTH_GAP + 2 * EARTH_R) * 1.04), (size.height * 0.74) / (2 * EARTH_R))
      const dist = size.height / (2 * pxPerUnit * Math.tan(THREE.MathUtils.degToRad(FOV / 2)))
      const camPair = mid.clone().add(c.multiplyScalar(dist))
      const frame = earthFrame(camPair, mid, earthPos)
      saved.current = { camMoon: camera.position.clone(), frame }

      earth.position.copy(earthPos)
      const moonTo = moonNormal ? faceQuaternion(moon.quaternion, moonNormal, new THREE.Vector3(), camPair) : moon.quaternion.clone()
      const to = earthNormal ? earthPoseFor(frame, earthNormal, 0, 0) : { yaw: [0, 0], tilt: [0, 0] }
      const earthPose: EarthPose = { yaw: [to.yaw[1] - 1.5, to.yaw[1]], tilt: [to.tilt[1], to.tilt[1]] }
      applyEarth(earth, frame, earthPose.yaw[0], earthPose.tilt[0])
      look.current.set(0, 0, 0)
      anim.current = {
        t: 0,
        duration: reducedMotion ? 0.01 : 2.6,
        camFrom: camera.position.clone(),
        camTo: camPair,
        lookFrom: look.current.clone(),
        lookTo: mid,
        moonFrom: moon.quaternion.clone(),
        moonTo,
        earth: earthPose,
        end: 'pair',
      }
    } else if (phase === 'to-moon' && saved.current) {
      anim.current = {
        t: 0,
        duration: reducedMotion ? 0.01 : 2.2,
        camFrom: camera.position.clone(),
        camTo: saved.current.camMoon,
        lookFrom: look.current.clone(),
        lookTo: new THREE.Vector3(),
        moonFrom: moon.quaternion.clone(),
        moonTo: new THREE.Quaternion(),
        earth: null,
        end: 'moon',
      }
    }
  }, [phase]) // eslint-disable-line react-hooks/exhaustive-deps

  // Picking another match turns both bodies to show the pair.
  useEffect(() => {
    const moon = moonGroup.current
    const earth = earthGroup.current
    const s = saved.current
    if (phase !== 'pair' || !moon || !earth || !s || !moonNormal || !earthNormal) return
    const moonTo = faceQuaternion(moon.quaternion, moonNormal, new THREE.Vector3(), s.frame.camPair)
    const target = earthPoseFor(s.frame, earthNormal, pose.current.yaw, pose.current.tilt)
    const angle = Math.max(
      moon.quaternion.angleTo(moonTo),
      Math.abs(target.yaw[1] - target.yaw[0]),
      Math.abs(target.tilt[1] - target.tilt[0]),
    )
    settle.current = {
      moonFrom: moon.quaternion.clone(),
      moonTo,
      earth: target,
      t: 0,
      duration: reducedMotion ? 0.01 : THREE.MathUtils.clamp(0.7 + angle * 0.45, 0.8, 1.8),
    }
  }, [phase, moonNormal, earthNormal]) // eslint-disable-line react-hooks/exhaustive-deps

  // Dragging spins both bodies together around the camera's axes.
  useEffect(() => {
    if (phase !== 'pair') return
    const el = gl.domElement
    const st = spin.current
    let last: { x: number; y: number } | null = null
    const down = (e: PointerEvent) => {
      if (e.button !== 0) return
      last = { x: e.clientX, y: e.clientY }
      st.active = true
      settle.current = null
    }
    const move = (e: PointerEvent) => {
      if (!last) return
      st.dx += e.clientX - last.x
      st.dy += e.clientY - last.y
      last = { x: e.clientX, y: e.clientY }
    }
    const up = () => {
      last = null
      st.active = false
    }
    el.addEventListener('pointerdown', down)
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
    window.addEventListener('pointercancel', up)
    return () => {
      el.removeEventListener('pointerdown', down)
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      window.removeEventListener('pointercancel', up)
      st.active = false
      st.dx = st.dy = st.vx = st.vy = 0
    }
  }, [phase, gl])

  useFrame((_, rawDt) => {
    const moon = moonGroup.current
    const earth = earthGroup.current
    if (!moon || !earth) return
    const dt = Math.min(rawDt, 1 / 30)

    const a = anim.current
    if (a) {
      a.t = Math.min(1, a.t + dt / a.duration)
      const e = easeInOut(a.t)
      camera.position.lerpVectors(a.camFrom, a.camTo, e)
      look.current.lerpVectors(a.lookFrom, a.lookTo, e)
      camera.lookAt(look.current)
      moon.quaternion.copy(a.moonFrom).slerp(a.moonTo, e)
      if (a.earth && saved.current) {
        const p = a.earth
        applyEarth(earth, saved.current.frame, THREE.MathUtils.lerp(p.yaw[0], p.yaw[1], e), THREE.MathUtils.lerp(p.tilt[0], p.tilt[1], e))
      }
      if (a.t >= 1) {
        anim.current = null
        onPhase(a.end)
      }
      return
    }
    if (phase !== 'pair') return

    const s = settle.current
    if (s && saved.current) {
      s.t = Math.min(1, s.t + dt / s.duration)
      const e = easeInOut(s.t)
      moon.quaternion.copy(s.moonFrom).slerp(s.moonTo, e)
      const p = s.earth
      applyEarth(earth, saved.current.frame, THREE.MathUtils.lerp(p.yaw[0], p.yaw[1], e), THREE.MathUtils.lerp(p.tilt[0], p.tilt[1], e))
      if (s.t >= 1) settle.current = null
      return
    }

    const st = spin.current
    let ax: number
    let ay: number
    if (st.active) {
      ax = st.dx * 0.0055
      ay = st.dy * 0.0055
      st.dx = st.dy = 0
      st.vx = ax / dt
      st.vy = ay / dt
    } else {
      ax = st.vx * dt
      ay = st.vy * dt
      const k = Math.exp(-3.2 * dt)
      st.vx *= k
      st.vy *= k
    }
    if (Math.abs(ax) + Math.abs(ay) < 1e-6) return
    tmp.up.set(0, 1, 0).applyQuaternion(camera.quaternion)
    tmp.right.set(1, 0, 0).applyQuaternion(camera.quaternion)
    tmp.q.setFromAxisAngle(tmp.up, ax)
    tmp.qa.setFromAxisAngle(tmp.right, ay)
    tmp.q.premultiply(tmp.qa)
    moon.quaternion.premultiply(tmp.q)
    // The Earth turns like a turntable: sideways drag spins it, up/down drag tips it, and it never rolls.
    if (saved.current) {
      applyEarth(earth, saved.current.frame, pose.current.yaw + ax, THREE.MathUtils.clamp(pose.current.tilt + ay, -MAX_TILT, MAX_TILT))
    }
  })

  return null
}

// Arc from the chosen Moon site to the chosen place on Earth, with a spark travelling along it.
function TwinArc({
  phase,
  moonGroup,
  earthGroup,
  moonNormal,
  earthNormal,
}: {
  phase: Phase
  moonGroup: RefObject<THREE.Group | null>
  earthGroup: RefObject<THREE.Group | null>
  moonNormal: THREE.Vector3 | null
  earthNormal: THREE.Vector3 | null
}) {
  const line = useRef<{ geometry: { setPositions: (a: number[]) => void }; material: THREE.Material & { opacity: number } } | null>(null)
  const spark = useRef<THREE.Mesh>(null)
  const shown = useRef(0)
  const t = useMemo(
    () => ({ a: new THREE.Vector3(), b: new THREE.Vector3(), c: new THREE.Vector3(), p: new THREE.Vector3(), n: new THREE.Vector3(), view: new THREE.Vector3() }),
    [],
  )
  const initial = useMemo<[number, number, number][]>(() => Array.from({ length: 49 }, () => [0, 0, 0]), [])
  const SEGMENTS = 48

  useFrame(({ camera, clock }, rawDt) => {
    const moon = moonGroup.current
    const earth = earthGroup.current
    const l = line.current
    if (!moon || !earth || !l || !moonNormal || !earthNormal) return
    const want = phase === 'pair' ? 1 : 0
    shown.current += (want - shown.current) * Math.min(1, Math.min(rawDt, 1 / 30) * 3)

    moon.updateWorldMatrix(true, false)
    earth.updateWorldMatrix(true, false)
    t.a.copy(moonNormal).multiplyScalar(1.004).applyMatrix4(moon.matrixWorld)
    t.b.copy(earthNormal).multiplyScalar(1.004).applyMatrix4(earth.matrixWorld)

    // Only draw while both ends face the camera.
    const facing = (n: THREE.Vector3, q: THREE.Quaternion, at: THREE.Vector3) =>
      t.n.copy(n).applyQuaternion(q).dot(t.view.copy(camera.position).sub(at).normalize())
    const visible = Math.min(facing(moonNormal, moon.quaternion, t.a), facing(earthNormal, earth.quaternion, t.b)) > 0.12
    const o = visible ? shown.current : 0
    l.material.opacity = 0.75 * o
    if (spark.current) spark.current.visible = o > 0.05
    if (o < 0.01) return

    t.c.copy(t.a).add(t.b).multiplyScalar(0.5)
    t.view.copy(camera.position).sub(t.c).normalize()
    t.n.set(0, 1, 0).applyQuaternion(camera.quaternion)
    const span = t.a.distanceTo(t.b)
    t.c.addScaledVector(t.n, span * 0.3).addScaledVector(t.view, span * 0.12)

    const pts: number[] = []
    for (let i = 0; i <= SEGMENTS; i++) {
      const u = i / SEGMENTS
      const k = 1 - u
      t.p.set(0, 0, 0).addScaledVector(t.a, k * k).addScaledVector(t.c, 2 * k * u).addScaledVector(t.b, u * u)
      pts.push(t.p.x, t.p.y, t.p.z)
    }
    l.geometry.setPositions(pts)

    if (spark.current) {
      const u = (clock.elapsedTime * 0.35) % 1
      const k = 1 - u
      spark.current.position.set(0, 0, 0).addScaledVector(t.a, k * k).addScaledVector(t.c, 2 * k * u).addScaledVector(t.b, u * u)
      spark.current.scale.setScalar(0.7 + Math.sin(u * Math.PI) * 0.6)
    }
  })

  return (
    <>
      <Line ref={line as never} points={initial} color={COLORS.signal} lineWidth={1.6} transparent opacity={0} depthWrite={false} renderOrder={4} frustumCulled={false} />
      <mesh ref={spark} renderOrder={5} visible={false}>
        <sphereGeometry args={[0.035, 16, 16]} />
        <meshBasicMaterial color={COLORS.signal} depthTest={false} />
      </mesh>
    </>
  )
}

type SceneProps = {
  sites: DisplaySite[]
  hoveredId: string | null
  selectedId: string | null
  onHover: (id: string | null) => void
  onSelect: (id: string) => void
  onReady: () => void
  mode: 'moon' | 'pair'
  analogs: Analog[]
  activeRank: number
  hoveredRank: number | null
  onHoverRank: (rank: number | null) => void
  onSelectRank: (rank: number) => void
}

function Scene({
  sites,
  hoveredId,
  selectedId,
  onHover,
  onSelect,
  onReady,
  mode,
  analogs,
  activeRank,
  hoveredRank,
  onHoverRank,
  onSelectRank,
}: SceneProps) {
  const moonRef = useRef<THREE.Mesh>(null)
  const earthRef = useRef<THREE.Mesh>(null)
  const moonGroup = useRef<THREE.Group>(null)
  const earthGroup = useRef<THREE.Group>(null)
  const introDone = useRef(false)
  const baseDistance = useBaseDistance()
  const [phase, setPhase] = useState<Phase>('moon')
  const selected = sites.find((s) => s.id === selectedId) ?? null

  useEffect(() => {
    if (mode === 'pair') setPhase((p) => (p === 'moon' || p === 'to-moon' ? 'to-pair' : p))
    else setPhase((p) => (p === 'pair' || p === 'to-pair' ? 'to-moon' : p))
  }, [mode])

  const onPhase = useCallback((p: Phase) => setPhase(p), [])
  const inPair = phase !== 'moon'
  const shownSites = inPair ? sites.filter((s) => s.id === selectedId) : sites
  const active = analogs.find((a) => a.rank === activeRank) ?? null
  const moonNormal = useMemo(() => (selected ? surfacePoint(selected.lat, selected.lon, 1) : null), [selected])
  const earthNormal = useMemo(() => (active ? surfacePoint(active.lat, active.lon, 1) : null), [active])
  const noop = useCallback(() => {}, [])

  return (
    <>
      <ambientLight intensity={0.5} color="#6fa8ff" />
      <Sun />
      <Suspense fallback={null}>
        <group ref={moonGroup}>
          <MoonBody meshRef={moonRef} onReady={onReady} />
          <Graticule />
          {shownSites.map((site, i) => (
            <SiteMarker
              key={site.id}
              site={site}
              index={i}
              state={inPair || site.id === selectedId ? 'selected' : site.id === hoveredId ? 'hover' : 'idle'}
              moonRef={moonRef}
              onHover={inPair ? noop : onHover}
              onSelect={inPair ? noop : onSelect}
            />
          ))}
        </group>
        <group ref={earthGroup} scale={EARTH_R} visible={inPair}>
          <EarthBody meshRef={earthRef} active={inPair} />
          <Graticule />
          {inPair &&
            analogs.map((a) => (
              <EarthPin
                key={a.patch_id}
                analog={a}
                state={a.rank === activeRank ? 'selected' : a.rank === hoveredRank ? 'hover' : 'idle'}
                earthRef={earthRef}
                onHover={onHoverRank}
                onSelect={onSelectRank}
              />
            ))}
        </group>
      </Suspense>
      <TwinArc phase={phase} moonGroup={moonGroup} earthGroup={earthGroup} moonNormal={moonNormal} earthNormal={earthNormal} />
      <PairRig phase={phase} onPhase={onPhase} moonGroup={moonGroup} earthGroup={earthGroup} moonNormal={moonNormal} earthNormal={earthNormal} />
      {phase === 'moon' && (
        <CameraRig selected={selected} baseDistance={baseDistance} paused={selectedId !== null || hoveredId !== null} introDone={introDone} />
      )}
    </>
  )
}

export default function MoonScene(props: SceneProps) {
  const start = useMemo(() => surfacePoint(8, -14, 9).toArray() as [number, number, number], [])
  return (
    <Canvas flat dpr={[1, 2]} camera={{ fov: FOV, near: 0.1, far: 80, position: start }} aria-hidden="true">
      <Scene {...props} />
    </Canvas>
  )
}

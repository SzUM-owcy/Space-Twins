import { useEffect, useRef, useState } from 'react'
import { drawPatch, PATCH_KM, type Body } from '../imagery'
import PatchFrame from './PatchFrame'

const SIZE = 900

type Status = 'loading' | 'ready' | 'error'

export default function PatchImage({
  body,
  title,
  lat,
  lon,
  matchMoon = false,
}: {
  body: Body
  title: string
  lat: number
  lon: number
  matchMoon?: boolean
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [status, setStatus] = useState<Status>('loading')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctl = new AbortController()
    setStatus('loading')
    drawPatch(canvas, body, lat, lon, ctl.signal, matchMoon).then((ok) => {
      if (!ctl.signal.aborted) setStatus(ok ? 'ready' : 'error')
    })
    return () => ctl.abort()
  }, [body, lat, lon, attempt, matchMoon])

  return (
    <PatchFrame
      body={body}
      title={title}
      lat={lat}
      lon={lon}
      status={status}
      loadingText="Fetching imagery"
      errorText="Imagery is unavailable. Check your internet connection."
      onRetry={() => setAttempt((n) => n + 1)}
    >
      <canvas ref={canvasRef} width={SIZE} height={SIZE} role="img" aria-label={`${title}, ${PATCH_KM} by ${PATCH_KM} kilometres`} />
    </PatchFrame>
  )
}

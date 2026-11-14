import { useEffect, useRef, useState } from 'react'
import { drawPatch, PATCH_KM, type Body } from '../imagery'
import { formatCoords } from '../sites'

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
    <figure className="patch" data-body={body} data-status={status}>
      <canvas ref={canvasRef} width={SIZE} height={SIZE} role="img" aria-label={`${title}, ${PATCH_KM} by ${PATCH_KM} kilometres`} />
      <figcaption className="patch-label">
        <span className="patch-title">{title}</span>
        <span className="patch-coords">{formatCoords(lat, lon)}</span>
      </figcaption>
      <span className="corner tl" />
      <span className="corner tr" />
      <span className="corner bl" />
      <span className="corner br" />
      <span className="scale">
        <i />
        {PATCH_KM / 5} km
      </span>
      {status === 'loading' && <span className="patch-state">Fetching imagery</span>}
      {status === 'error' && (
        <span className="patch-state">
          Imagery is unavailable. Check your internet connection.
          <button type="button" className="back" onClick={() => setAttempt((n) => n + 1)}>
            Try again
          </button>
        </span>
      )}
    </figure>
  )
}

import type { PointerEventHandler, ReactNode } from 'react'
import { PATCH_KM } from '../imagery'
import { formatCoords } from '../sites'

export type FrameStatus = 'loading' | 'ready' | 'error'

/** The square 10 x 10 km frame shared by every comparison tab, so layout never shifts between them. */
export default function PatchFrame({
  body,
  title,
  lat,
  lon,
  status,
  loadingText,
  errorText,
  onRetry,
  showScale = true,
  onPointerMove,
  onPointerLeave,
  children,
}: {
  body: 'moon' | 'earth'
  title: string
  lat: number
  lon: number
  status: FrameStatus
  loadingText: string
  errorText: string
  onRetry: () => void
  showScale?: boolean
  onPointerMove?: PointerEventHandler<HTMLElement>
  onPointerLeave?: PointerEventHandler<HTMLElement>
  children: ReactNode
}) {
  return (
    <figure className="patch" data-body={body} data-status={status} onPointerMove={onPointerMove} onPointerLeave={onPointerLeave}>
      <div className="patch-content">{children}</div>
      <figcaption className="patch-label">
        <span className="patch-title">{title}</span>
        <span className="patch-coords">{formatCoords(lat, lon)}</span>
      </figcaption>
      <span className="corner tl" />
      <span className="corner tr" />
      <span className="corner bl" />
      <span className="corner br" />
      {showScale && (
        <span className="scale">
          <i />
          {PATCH_KM / 5} km
        </span>
      )}
      {status === 'loading' && <span className="patch-state">{loadingText}</span>}
      {status === 'error' && (
        <span className="patch-state">
          {errorText}
          <button type="button" className="back" onClick={onRetry}>
            Try again
          </button>
        </span>
      )}
    </figure>
  )
}

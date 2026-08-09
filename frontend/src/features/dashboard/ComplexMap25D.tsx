import { useRef, useState } from 'react'
import type { CSSProperties, PointerEvent as ReactPointerEvent } from 'react'
import { cn } from '../../lib/cn'
import type { MapPin, MapRobot, Tone } from '../../types/domain'
import {
  createIsometricProjection,
  mapPixelToIsometric,
  pointsAttribute,
  worldBoundsToIsometricPolygon,
  worldToIsometric,
} from '../onboarding/mapProjection25d'
import { complexMapCoordinateMetadata } from './mapCoordinateMetadata'
import type { ComplexMapProps } from './ComplexMap'

const MAX_ZOOM = 2.5

const pinColor: Record<Tone, string> = {
  danger: 'var(--urgent)',
  warning: 'var(--alert)',
  info: 'var(--patrol)',
  success: 'var(--charge)',
  neutral: 'var(--offline)',
}

function validWorldPoint(value: { worldX?: number; worldY?: number }) {
  return Number.isFinite(value.worldX) && Number.isFinite(value.worldY)
}

function headingOnScreen(
  metadata: NonNullable<ReturnType<typeof complexMapCoordinateMetadata>>,
  projection: ReturnType<typeof createIsometricProjection>,
  robot: MapRobot,
) {
  if (!validWorldPoint(robot) || robot.heading == null) return 0
  const radians = robot.heading * Math.PI / 180
  const origin = worldToIsometric(metadata, projection, {
    x: robot.worldX!,
    y: robot.worldY!,
  })
  const forward = worldToIsometric(metadata, projection, {
    x: robot.worldX! + Math.cos(radians) * 0.5,
    y: robot.worldY! + Math.sin(radians) * 0.5,
  })
  return Math.atan2(forward.y - origin.y, forward.x - origin.x) * 180 / Math.PI
}

function markerLabel(pin: MapPin) {
  return pin.detail ? `${pin.label} · ${pin.detail}` : pin.label
}

export function ComplexMap25D({
  map,
  robot,
  robots,
  pins = [],
  checkpoints = [],
  patrolling = true,
  bottomRight,
  className,
}: ComplexMapProps) {
  const [view, setView] = useState({ zoom: 1, panX: 0, panY: 0 })
  const svgRef = useRef<SVGSVGElement>(null)
  const drag = useRef<{ pointerId: number; clientX: number; clientY: number }>()
  const [panning, setPanning] = useState(false)
  const metadata = complexMapCoordinateMetadata(map)
  if (!metadata) return null

  const projection = createIsometricProjection(metadata, { tileX: 1, tileY: 0.48 })
  const floor = [
    { x: 0, y: 0 },
    { x: metadata.width, y: 0 },
    { x: metadata.width, y: metadata.height },
    { x: 0, y: metadata.height },
  ].map((point) => mapPixelToIsometric(projection, point))
  const imageTransform = [
    projection.tileX,
    projection.tileY,
    projection.tileX,
    -projection.tileY,
    projection.offsetX - metadata.height * projection.tileX,
    projection.offsetY + metadata.height * projection.tileY,
  ].join(' ')
  const displayedRobots = robots?.length ? robots : robot ? [robot] : []
  const plannedRoute = checkpoints.filter(validWorldPoint).map((point) =>
    worldToIsometric(metadata, projection, { x: point.worldX!, y: point.worldY! }))
  const actualRoutes = displayedRobots.map((item) => ({
    id: item.id,
    points: (item.routePoints ?? []).filter(validWorldPoint).map((point) =>
      worldToIsometric(metadata, projection, { x: point.worldX!, y: point.worldY! })),
  })).filter((route) => route.points.length > 1)

  const zoomBy = (factor: number) => setView((current) => ({
    ...current,
    zoom: Math.max(1, Math.min(MAX_ZOOM, current.zoom * factor)),
  }))
  const resetView = () => setView({ zoom: 1, panX: 0, panY: 0 })
  const onPointerDown = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (event.button !== 0 || view.zoom <= 1) return
    drag.current = { pointerId: event.pointerId, clientX: event.clientX, clientY: event.clientY }
    event.currentTarget.setPointerCapture(event.pointerId)
    setPanning(true)
  }
  const onPointerMove = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (!drag.current || drag.current.pointerId !== event.pointerId || !svgRef.current) return
    const rect = svgRef.current.getBoundingClientRect()
    if (!rect.width || !rect.height) return
    const dx = (event.clientX - drag.current.clientX) * projection.viewWidth / rect.width
    const dy = (event.clientY - drag.current.clientY) * projection.viewHeight / rect.height
    drag.current = { pointerId: event.pointerId, clientX: event.clientX, clientY: event.clientY }
    setView((current) => ({ ...current, panX: current.panX + dx, panY: current.panY + dy }))
  }
  const onPointerUp = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (drag.current?.pointerId !== event.pointerId) return
    drag.current = undefined
    setPanning(false)
    event.currentTarget.releasePointerCapture(event.pointerId)
  }

  return (
    <div className={cn('dm25-wrap', panning && 'pan', className)}>
      <svg
        ref={svgRef}
        className="dm25-map"
        viewBox={`0 0 ${projection.viewWidth} ${projection.viewHeight}`}
        role="img"
        aria-label="실시간 2.5D 관제 지도"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        <title>실시간 로봇 위치, 순찰 경로, 구역 및 이벤트를 표시하는 2.5D 지도</title>
        <g transform={`translate(${view.panX} ${view.panY}) scale(${view.zoom})`}>
          <polygon className="dm25-floor" points={pointsAttribute(floor)} />
          {map.mapImageUrl && (
            <image
              className="dm25-map-image"
              href={map.mapImageUrl}
              width={metadata.width}
              height={metadata.height}
              preserveAspectRatio="none"
              transform={`matrix(${imageTransform})`}
            />
          )}

          {map.zones.flatMap((zone) => {
            if (!zone.worldBounds) return []
            const polygon = worldBoundsToIsometricPolygon(metadata, projection, zone.worldBounds)
            const center = polygon.reduce(
              (sum, point) => ({ x: sum.x + point.x / polygon.length, y: sum.y + point.y / polygon.length }),
              { x: 0, y: 0 },
            )
            return [(
              <g className="dm25-zone" key={zone.id}>
                <polygon points={pointsAttribute(polygon)} />
                <text x={center.x} y={center.y}>{zone.label}</text>
              </g>
            )]
          })}

          {plannedRoute.length > 1 && (
            <polyline className="dm25-route planned" points={pointsAttribute(plannedRoute)} />
          )}
          {actualRoutes.map((route) => (
            <polyline className="dm25-route actual" key={route.id} points={pointsAttribute(route.points)} />
          ))}

          {checkpoints.flatMap((checkpoint, index) => {
            if (!validWorldPoint(checkpoint)) return []
            const point = worldToIsometric(metadata, projection, {
              x: checkpoint.worldX!, y: checkpoint.worldY!,
            })
            return [(
              <g className="dm25-waypoint" key={checkpoint.id} transform={`translate(${point.x} ${point.y})`}>
                <circle r="5" />
                <text y="-8">{index + 1}. {checkpoint.label}</text>
                <title>{checkpoint.note ? `${checkpoint.label} · ${checkpoint.note}` : checkpoint.label}</title>
              </g>
            )]
          })}

          {pins.flatMap((pin) => {
            if (!validWorldPoint(pin)) return []
            const point = worldToIsometric(metadata, projection, { x: pin.worldX!, y: pin.worldY! })
            return [(
              <g
                className="dm25-event"
                key={pin.id}
                transform={`translate(${point.x} ${point.y})`}
                style={{ '--dm25-pin': pinColor[pin.tone] } as CSSProperties}
              >
                <circle className="pulse" r="10" />
                <path d="M0 0 L-4 -8 A6 6 0 1 1 4 -8 Z" />
                <text y="-18">{markerLabel(pin)}</text>
                <title>{markerLabel(pin)}</title>
              </g>
            )]
          })}

          {displayedRobots.flatMap((item) => {
            if (!validWorldPoint(item)) return []
            const point = worldToIsometric(metadata, projection, { x: item.worldX!, y: item.worldY! })
            const heading = headingOnScreen(metadata, projection, item)
            return [(
              <g className="dm25-robot" key={item.id} transform={`translate(${point.x} ${point.y})`}>
                {patrolling && <circle className="pulse" r="13" />}
                <g transform={`rotate(${heading})`}>
                  <path d="M11 0 L-7 -7 L-3 0 L-7 7 Z" />
                </g>
                <text y="-17">{item.name ?? item.id}</text>
                <title>{`${item.name ?? item.id} · x ${item.worldX!.toFixed(2)}, y ${item.worldY!.toFixed(2)}, heading ${item.heading ?? 0}°`}</title>
              </g>
            )]
          })}
        </g>
      </svg>

      <div className="dm25-controls" aria-label="2.5D 지도 확대/축소">
        <button type="button" onClick={() => zoomBy(1.35)} disabled={view.zoom >= MAX_ZOOM} aria-label="확대">+</button>
        <button type="button" onClick={() => zoomBy(1 / 1.35)} disabled={view.zoom <= 1} aria-label="축소">−</button>
        <button type="button" onClick={resetView} disabled={view.zoom === 1} aria-label="전체 보기">◎</button>
      </div>
      {bottomRight && <div className="dm25-bottom-right">{bottomRight}</div>}
    </div>
  )
}

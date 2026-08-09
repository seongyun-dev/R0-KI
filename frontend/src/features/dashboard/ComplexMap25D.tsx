import { useEffect, useRef, useState } from 'react'
import type { CSSProperties, PointerEvent as ReactPointerEvent } from 'react'
import { cn } from '../../lib/cn'
import type { MapPin, MapRobot, Tone, ZoneType } from '../../types/domain'
import {
  applyIsometricScreenFit,
  createIsometricProjection,
  fitIsometricProjection,
  mapPixelToIsometric,
  pointsAttribute,
  worldBoundsToIsometricPolygon,
  worldToIsometric,
} from '../onboarding/mapProjection25d'
import { complexMapCoordinateMetadata } from './mapCoordinateMetadata'
import type { ComplexMapProps } from './ComplexMap'

const MAX_ZOOM = 2.5
const WALL_HEIGHT_PX = 10
const DEFAULT_VIEWPORT = { width: 960, height: 540 }

const pinColor: Record<Tone, string> = {
  danger: 'var(--urgent)',
  warning: 'var(--alert)',
  info: 'var(--patrol)',
  success: 'var(--charge)',
  neutral: 'var(--offline)',
}

const zonePrefix: Partial<Record<ZoneType, string>> = {
  주차장: 'P',
  분리수거장: 'R',
  출입구: 'S',
  도착지: 'D',
}

const labelOffsets = [
  { dx: -12, dy: -15, side: 'left' as const },
  { dx: 12, dy: -15, side: 'right' as const },
  { dx: 12, dy: 17, side: 'right' as const },
  { dx: -12, dy: 19, side: 'left' as const },
]

function validWorldPoint(value: { worldX?: number; worldY?: number }) {
  return Number.isFinite(value.worldX) && Number.isFinite(value.worldY)
}

function markerLabel(pin: MapPin) {
  return pin.detail ? `${pin.label} · ${pin.detail}` : pin.label
}

function DisplayLabel({
  x,
  y,
  text,
  viewportWidth,
  viewportHeight,
  className,
  side = 'center',
}: {
  x: number
  y: number
  text: string
  viewportWidth: number
  viewportHeight: number
  className: string
  side?: 'left' | 'right' | 'center'
}) {
  const width = Math.max(42, Math.min(164, text.length * 7 + 16))
  const desiredLeft = side === 'left' ? x - width : side === 'right' ? x : x - width / 2
  const left = Math.max(6, Math.min(viewportWidth - width - 6, desiredLeft))
  const top = Math.max(6, Math.min(viewportHeight - 28, y - 11))
  return (
    <g className={`dm25-label ${className}`} transform={`translate(${left} ${top})`}>
      <rect width={width} height="22" rx="11" />
      <text x={width / 2} y="14">{text}</text>
    </g>
  )
}

function headingOnScreen(
  metadata: NonNullable<ReturnType<typeof complexMapCoordinateMetadata>>,
  projection: ReturnType<typeof createIsometricProjection>,
  robot: MapRobot,
) {
  if (!validWorldPoint(robot) || robot.heading == null) return 0
  const radians = robot.heading * Math.PI / 180
  const origin = worldToIsometric(metadata, projection, { x: robot.worldX!, y: robot.worldY! })
  const forward = worldToIsometric(metadata, projection, {
    x: robot.worldX! + Math.cos(radians) * 0.5,
    y: robot.worldY! + Math.sin(radians) * 0.5,
  })
  return Math.atan2(forward.y - origin.y, forward.x - origin.x) * 180 / Math.PI
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
  const [viewport, setViewport] = useState(DEFAULT_VIEWPORT)
  const wrapperRef = useRef<HTMLDivElement>(null)
  const svgRef = useRef<SVGSVGElement>(null)
  const drag = useRef<{ pointerId: number; clientX: number; clientY: number }>()
  const [panning, setPanning] = useState(false)

  useEffect(() => {
    const element = wrapperRef.current
    if (!element || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(([entry]) => {
      const width = Math.max(320, Math.round(entry.contentRect.width))
      const height = Math.max(300, Math.round(entry.contentRect.height))
      setViewport((current) => current.width === width && current.height === height
        ? current
        : { width, height })
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  const metadata = complexMapCoordinateMetadata(map)
  if (!metadata) return null

  const projection = createIsometricProjection(metadata, { tileX: 1, tileY: 0.58, margin: 8 })
  const fit = fitIsometricProjection(projection, viewport, 0.065)
  const toScreen = (point: { x: number; y: number }) => applyIsometricScreenFit(point, fit)
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
    toScreen(worldToIsometric(metadata, projection, { x: point.worldX!, y: point.worldY! })))
  const actualRoutes = displayedRobots.map((item) => ({
    id: item.id,
    points: (item.routePoints ?? []).filter(validWorldPoint).map((point) =>
      toScreen(worldToIsometric(metadata, projection, { x: point.worldX!, y: point.worldY! }))),
  })).filter((route) => route.points.length > 1)
  const wallOffset = WALL_HEIGHT_PX / fit.scale

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
    const dx = (event.clientX - drag.current.clientX) * viewport.width / rect.width
    const dy = (event.clientY - drag.current.clientY) * viewport.height / rect.height
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
    <div ref={wrapperRef} className={cn('dm25-wrap polished', panning && 'pan', className)}>
      <svg
        ref={svgRef}
        className="dm25-map"
        viewBox={`0 0 ${viewport.width} ${viewport.height}`}
        role="img"
        aria-label="실시간 2.5D 관제 지도"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        <title>실시간 로봇 위치, 순찰 경로, 구역 및 이벤트를 표시하는 2.5D 지도</title>
        <defs>
          <filter id="dm25-wall-side-mask" colorInterpolationFilters="sRGB">
            <feColorMatrix
              type="matrix"
              values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  -0.333 -0.333 -0.333 0 1"
              result="occupied"
            />
            <feComponentTransfer in="occupied" result="threshold">
              <feFuncA type="discrete" tableValues="0 0 1 1" />
            </feComponentTransfer>
            <feFlood floodColor="var(--dm25-wall-side)" result="wallColor" />
            <feComposite in="wallColor" in2="threshold" operator="in" />
          </filter>
          <filter id="dm25-wall-top-mask" colorInterpolationFilters="sRGB">
            <feColorMatrix
              type="matrix"
              values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  -0.333 -0.333 -0.333 0 1"
              result="occupied"
            />
            <feComponentTransfer in="occupied" result="threshold">
              <feFuncA type="discrete" tableValues="0 0 1 1" />
            </feComponentTransfer>
            <feFlood floodColor="var(--dm25-wall-top)" result="wallColor" />
            <feComposite in="wallColor" in2="threshold" operator="in" />
          </filter>
        </defs>

        <g transform={`translate(${view.panX} ${view.panY}) scale(${view.zoom})`}>
          <g transform={`translate(${fit.translateX} ${fit.translateY}) scale(${fit.scale})`}>
            <polygon className="dm25-floor-shadow" points={pointsAttribute(floor)} transform={`translate(0 ${wallOffset + 5 / fit.scale})`} />
            <polygon className="dm25-floor" points={pointsAttribute(floor)} />
            {map.mapImageUrl && (
              <>
                <image
                  className="dm25-map-image"
                  href={map.mapImageUrl}
                  width={metadata.width}
                  height={metadata.height}
                  preserveAspectRatio="none"
                  transform={`matrix(${imageTransform})`}
                />
                <g className="dm25-wall-side" transform={`translate(0 ${wallOffset})`}>
                  <image href={map.mapImageUrl} width={metadata.width} height={metadata.height} preserveAspectRatio="none" transform={`matrix(${imageTransform})`} filter="url(#dm25-wall-side-mask)" />
                </g>
                <g className="dm25-wall-mid" transform={`translate(0 ${wallOffset * 0.48})`}>
                  <image href={map.mapImageUrl} width={metadata.width} height={metadata.height} preserveAspectRatio="none" transform={`matrix(${imageTransform})`} filter="url(#dm25-wall-side-mask)" />
                </g>
                <g className="dm25-wall-top">
                  <image href={map.mapImageUrl} width={metadata.width} height={metadata.height} preserveAspectRatio="none" transform={`matrix(${imageTransform})`} filter="url(#dm25-wall-top-mask)" />
                </g>
              </>
            )}
          </g>

          {map.zones.flatMap((zone) => {
            if (!zone.worldBounds) return []
            const polygon = worldBoundsToIsometricPolygon(metadata, projection, zone.worldBounds).map(toScreen)
            const center = polygon.reduce(
              (sum, point) => ({ x: sum.x + point.x / polygon.length, y: sum.y + point.y / polygon.length }),
              { x: 0, y: 0 },
            )
            const prefix = zonePrefix[zone.type]
            return [(
              <g className="dm25-zone" key={zone.id}>
                <polygon className="platform" points={pointsAttribute(polygon.map((point) => ({ x: point.x, y: point.y + 4 })))} />
                <polygon className="surface" points={pointsAttribute(polygon)} />
                <DisplayLabel x={center.x} y={center.y} viewportWidth={viewport.width} viewportHeight={viewport.height} text={prefix ? `[${prefix}] ${zone.label}` : zone.label} className="zone" />
              </g>
            )]
          })}

          {plannedRoute.length > 1 && <polyline className="dm25-route planned" points={pointsAttribute(plannedRoute)} />}
          {actualRoutes.map((route) => <polyline className="dm25-route actual" key={route.id} points={pointsAttribute(route.points)} />)}

          {checkpoints.flatMap((checkpoint, index) => {
            if (!validWorldPoint(checkpoint)) return []
            const point = toScreen(worldToIsometric(metadata, projection, { x: checkpoint.worldX!, y: checkpoint.worldY! }))
            const offset = labelOffsets[index % labelOffsets.length]
            return [(
              <g className="dm25-waypoint" key={checkpoint.id}>
                <circle cx={point.x} cy={point.y} r="7" />
                <circle className="core" cx={point.x} cy={point.y} r="2.4" />
                <DisplayLabel x={point.x + offset.dx} y={point.y + offset.dy} viewportWidth={viewport.width} viewportHeight={viewport.height} text={`${index + 1}번 · ${checkpoint.label}`} className="waypoint" side={offset.side} />
                <title>{checkpoint.note ? `${checkpoint.label} · ${checkpoint.note}` : checkpoint.label}</title>
              </g>
            )]
          })}

          {displayedRobots.flatMap((item) => {
            if (!validWorldPoint(item)) return []
            const point = toScreen(worldToIsometric(metadata, projection, { x: item.worldX!, y: item.worldY! }))
            const heading = headingOnScreen(metadata, projection, item)
            return [(
              <g className="dm25-robot" key={item.id}>
                {patrolling && <circle className="pulse" cx={point.x} cy={point.y} r="15" />}
                <circle className="ring" cx={point.x} cy={point.y} r="12" />
                <circle className="core" cx={point.x} cy={point.y} r="6" />
                <g className="heading" transform={`translate(${point.x} ${point.y}) rotate(${heading})`}>
                  <line x1="5" y1="0" x2="15" y2="0" />
                  <path d="M16 0 L11 -3.5 L11 3.5 Z" />
                </g>
                <DisplayLabel x={point.x} y={point.y - 25} viewportWidth={viewport.width} viewportHeight={viewport.height} text={item.name ?? item.id} className="robot" />
                <title>{`${item.name ?? item.id} · x ${item.worldX!.toFixed(2)}, y ${item.worldY!.toFixed(2)}, heading ${item.heading ?? 0}°`}</title>
              </g>
            )]
          })}

          {pins.flatMap((pin) => {
            if (!validWorldPoint(pin)) return []
            const point = toScreen(worldToIsometric(metadata, projection, { x: pin.worldX!, y: pin.worldY! }))
            return [(
              <g className="dm25-event" key={pin.id} style={{ '--dm25-pin': pinColor[pin.tone] } as CSSProperties}>
                <circle className="pulse" cx={point.x} cy={point.y} r="13" />
                <path transform={`translate(${point.x} ${point.y})`} d="M0 0 L-4 -8 A6 6 0 1 1 4 -8 Z" />
                <DisplayLabel x={point.x} y={point.y - 24} viewportWidth={viewport.width} viewportHeight={viewport.height} text={markerLabel(pin)} className="event" />
                <title>{markerLabel(pin)}</title>
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

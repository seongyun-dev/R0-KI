import { useEffect, useMemo, useRef, useState, type CSSProperties, type FormEvent } from 'react'
import type {
  Id,
  MapDetailResponse,
  ZoneCreateRequest,
  ZoneCreateResponse,
  ZoneTypeCode,
} from '../../api/contracts'
import { mapApi } from '../../api/services'
import { R0KiModal } from '../../components/layout/R0KiModal'
import type { Zone, ZoneType } from '../../types/domain'
import {
  assertSupportedMapCoordinates,
  gridRectToWorldBounds,
  mapPixelToWorld,
  numericMapMetadata,
  worldBoundsToGridRect,
  worldBoundsFromPoints,
  worldBoundsOverlap,
  zoneBounds,
  type GridRect,
  type MapPoint,
  type WorldBounds,
} from './mapCoordinates'
import {
  clientToSvgPoint,
  createIsometricProjection,
  invertViewTransform,
  isometricToMapPixel,
  MAP_25D_PROJECTION_OPTIONS,
  MAP_25D_WALL_HEIGHT_PX,
  mapPixelToIsometric,
  pointsAttribute,
  worldBoundsToIsometricPolygon,
  type IsometricPoint,
  type ViewTransform,
} from './mapProjection25d'
import { Map25DBase } from '../dashboard/Map25DBase'
import { StepWaypoints } from './StepWaypoints'

export type StepZonesProps = {
  mapId: string | number
  onPrev: () => void
  /** 등록한 구역 목록을 상위로 전달 (대시보드 지도에 반영) */
  onComplete: (zones: Zone[]) => void
}

const COLS = 14 // 열 A~N
const ROWS = 7 // 행 1~7
const colLabel = (i: number) => String.fromCharCode(65 + i)

const ZONE_TYPES: ZoneType[] = ['주차장', '분리수거장', '출입구', '도착지']

const zoneTypeCode: Record<string, ZoneTypeCode> = {
  주차장: 'PARKING',
  분리수거장: 'RECYCLING_AREA',
  출입구: 'START',
  도착지: 'DESTINATION',
}

const zoneTypeLabel: Record<ZoneTypeCode, ZoneType> = {
  START: '출입구',
  PARKING: '주차장',
  RECYCLING_AREA: '분리수거장',
  DESTINATION: '도착지',
}

/* 구역 색 — 상태 명도 램프 토큰. 색만으로 구분하지 않도록 이름을 함께 표기(3중 표기) */
const zoneTone: Record<ZoneType, string> = {
  주차장: 'patrol',
  분리수거장: 'charge',
  출입구: 'detect',
  도착지: 'offline',
  기타: 'offline',
}
const toneVar = (type: ZoneType) => ({ '--z': `var(--${zoneTone[type]})` }) as CSSProperties

type Rect = GridRect
type DraftZone = {
  id: string | number
  zoneId?: Id
  type: ZoneType
  label: string
  /** 화면 좌표가 아닌 Backend 계약과 동일한 ROS world bounds가 진실원천이다. */
  bounds: WorldBounds
}

const toRect = (a: { c: number; r: number }, b: { c: number; r: number }): Rect => ({
  x: Math.min(a.c, b.c),
  y: Math.min(a.r, b.r),
  w: Math.abs(a.c - b.c) + 1,
  h: Math.abs(a.r - b.r) + 1,
})

// 격자 좌표 → 사람이 읽는 이름 (A1–D3 · 4×3칸)
const rangeName = (r: Rect) =>
  `${colLabel(r.x)}${r.y + 1}–${colLabel(r.x + r.w - 1)}${r.y + r.h}`
const sizeName = (r: Rect) => `${r.w}×${r.h}칸`

const rectStyle = (r: Rect) => ({
  left: `${(r.x / COLS) * 100}%`,
  top: `${(r.y / ROWS) * 100}%`,
  width: `${(r.w / COLS) * 100}%`,
  height: `${(r.h / ROWS) * 100}%`,
})

const DEFAULT_ISO_VIEW: ViewTransform = { zoom: 1, panX: 0, panY: 0 }

/** Step 3/3 — 구역 지정 (IoT 수신 맵 위 드래그) (1y). R0Kiauth 시안 pMap 상태 C */
export function StepZones({ mapId, onPrev, onComplete }: StepZonesProps) {
  const gridRef = useRef<HTMLDivElement>(null)
  const isoSvgRef = useRef<SVGSVGElement>(null)
  const idRef = useRef(0)
  const [editorStage, setEditorStage] = useState<'zones' | 'waypoints'>('zones')
  const [viewMode, setViewMode] = useState<'2d' | '2.5d'>('2d')
  const [selectedType, setSelectedType] = useState<ZoneType>('주차장')
  const [zones, setZones] = useState<DraftZone[]>([])
  const [savedZones, setSavedZones] = useState<ZoneCreateResponse[]>([])
  const [isZoneDirty, setIsZoneDirty] = useState(false)
  // 드래그 상태는 ref가 진실원천(포인터 이벤트가 리렌더보다 빠를 수 있음), state는 프리뷰 렌더용
  const dragRef = useRef<{ start: { c: number; r: number }; cur: { c: number; r: number } } | null>(null)
  const [drag, setDrag] = useState<typeof dragRef.current>(null)
  const isoDragRef = useRef<{ pointerId: number; start: MapPoint; cur: MapPoint } | null>(null)
  const [isoDrag, setIsoDrag] = useState<typeof isoDragRef.current>(null)
  const isoPanRef = useRef<{ pointerId: number; client: IsometricPoint } | null>(null)
  const [isoView, setIsoView] = useState<ViewTransform>(DEFAULT_ISO_VIEW)
  // 구역 이름 입력/수정 모달 — 드래그로 그린 직후, 또는 기존 구역 클릭 시
  const [nameModalOpen, setNameModalOpen] = useState(false)
  const [nameInput, setNameInput] = useState('')
  const [draftBounds, setDraftBounds] = useState<WorldBounds | null>(null)
  const [draftType, setDraftType] = useState<ZoneType>('주차장')
  const [editingId, setEditingId] = useState<string | number | null>(null)
  const [map, setMap] = useState<MapDetailResponse>()
  const [mapImageUrl, setMapImageUrl] = useState<string>()
  const [loadError, setLoadError] = useState<string>()
  const [saveError, setSaveError] = useState<string>()
  const [isSaving, setIsSaving] = useState(false)
  const savingRef = useRef(false)
  const isoProjection = useMemo(
    () => map ? createIsometricProjection(map, MAP_25D_PROJECTION_OPTIONS) : undefined,
    [map],
  )
  // 겹침 등 경고 칩 (시안 .au-warn) — 잠시 떴다 사라진다
  const [warn, setWarn] = useState<string>()
  const warnTimer = useRef<number>()
  const showWarn = (message: string) => {
    setWarn(message)
    window.clearTimeout(warnTimer.current)
    warnTimer.current = window.setTimeout(() => setWarn(undefined), 2600)
  }
  useEffect(() => () => window.clearTimeout(warnTimer.current), [])

  useEffect(() => {
    const controller = new AbortController()
    let objectUrl: string | undefined
    const loadMap = async () => {
      try {
        const [detail, registeredZones] = await Promise.all([
          mapApi.detail(mapId),
          mapApi.zones(mapId),
        ])
        assertSupportedMapCoordinates(detail)
        const blob = await mapApi.file(detail.mapUrl, controller.signal)
        objectUrl = URL.createObjectURL(blob)
        setMap(detail)
        setMapImageUrl(objectUrl)
        setSavedZones(registeredZones)
        setIsZoneDirty(false)
        setZones(registeredZones.map((zone) => {
          const bounds = zoneBounds(zone)
          return {
            id: zone.zoneId,
            zoneId: zone.zoneId,
            type: zoneTypeLabel[zone.type],
            label: zone.name,
            bounds,
          }
        }))
      } catch (reason) {
        if (!controller.signal.aborted) {
          setLoadError(reason instanceof Error ? reason.message : '지도를 불러오지 못했습니다.')
        }
      }
    }
    void loadMap()
    return () => {
      controller.abort()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [mapId])

  const cellAt = (e: React.PointerEvent) => {
    const rect = gridRef.current!.getBoundingClientRect()
    const c = Math.max(0, Math.min(COLS - 1, Math.floor(((e.clientX - rect.left) / rect.width) * COLS)))
    const r = Math.max(0, Math.min(ROWS - 1, Math.floor(((e.clientY - rect.top) / rect.height) * ROWS)))
    return { c, r }
  }

  const onPointerDown = (e: React.PointerEvent) => {
    if (savingRef.current) return
    const cell = cellAt(e)
    try {
      gridRef.current!.setPointerCapture(e.pointerId)
    } catch {
      // 포인터 캡처 실패는 무시 — 드래그는 grid 내 move/up으로도 동작
    }
    dragRef.current = { start: cell, cur: cell }
    setDrag(dragRef.current)
  }
  const onPointerMove = (e: React.PointerEvent) => {
    if (savingRef.current || !dragRef.current) return
    dragRef.current = { ...dragRef.current, cur: cellAt(e) }
    setDrag(dragRef.current)
  }

  const beginCreateZone = (bounds: WorldBounds) => {
    if (zones.some((zone) => worldBoundsOverlap(zone.bounds, bounds))) {
      showWarn('다른 구역과 겹칠 수 없습니다')
      return
    }
    if (selectedType === '도착지' && zones.some((zone) => zone.type === '도착지')) {
      showWarn('도착지는 한 곳만 등록할 수 있습니다')
      return
    }
    const count = zones.filter((zone) => zone.type === selectedType).length
    setDraftBounds(bounds)
    setDraftType(selectedType)
    setEditingId(null)
    setNameInput(`${selectedType} ${count + 1}`)
    setNameModalOpen(true)
  }

  const onPointerUp = () => {
    const d = dragRef.current
    if (!d) return
    dragRef.current = null
    setDrag(null)
    if (savingRef.current || !map) return
    const rect = toRect(d.start, d.cur)
    beginCreateZone(gridRectToWorldBounds(map, rect, COLS, ROWS))
  }

  const clientToIsoRoot = (client: IsometricPoint) => {
    if (!isoSvgRef.current || !isoProjection) return null
    return clientToSvgPoint(
      client,
      isoSvgRef.current.getBoundingClientRect(),
      { x: 0, y: 0, width: isoProjection.viewWidth, height: isoProjection.viewHeight },
    )
  }

  const clientToIsoWorld = (client: IsometricPoint, clampToMap: boolean) => {
    if (!map || !isoProjection) return null
    const rootPoint = clientToIsoRoot(client)
    if (!rootPoint) return null
    const contentPoint = invertViewTransform(rootPoint, isoView)
    const pixel = isometricToMapPixel(isoProjection, contentPoint)
    const { width, height } = numericMapMetadata(map)
    if (!clampToMap && (pixel.x < 0 || pixel.x > width || pixel.y < 0 || pixel.y > height)) {
      return null
    }
    return mapPixelToWorld(map, {
      x: Math.max(0, Math.min(width, pixel.x)),
      y: Math.max(0, Math.min(height, pixel.y)),
    })
  }

  const onIsoPointerDown = (event: React.PointerEvent<SVGSVGElement>) => {
    if (savingRef.current) return
    if (event.button === 1 || event.button === 2) {
      isoPanRef.current = {
        pointerId: event.pointerId,
        client: { x: event.clientX, y: event.clientY },
      }
      event.currentTarget.setPointerCapture(event.pointerId)
      event.preventDefault()
      return
    }
    if (event.button !== 0) return
    const world = clientToIsoWorld({ x: event.clientX, y: event.clientY }, false)
    if (!world) return
    isoDragRef.current = { pointerId: event.pointerId, start: world, cur: world }
    setIsoDrag(isoDragRef.current)
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  const onIsoPointerMove = (event: React.PointerEvent<SVGSVGElement>) => {
    const pan = isoPanRef.current
    if (pan?.pointerId === event.pointerId) {
      const previous = clientToIsoRoot(pan.client)
      const currentClient = { x: event.clientX, y: event.clientY }
      const current = clientToIsoRoot(currentClient)
      isoPanRef.current = { ...pan, client: currentClient }
      if (previous && current) {
        setIsoView((view) => ({
          ...view,
          panX: view.panX + current.x - previous.x,
          panY: view.panY + current.y - previous.y,
        }))
      }
      return
    }
    const selection = isoDragRef.current
    if (!selection || selection.pointerId !== event.pointerId) return
    const world = clientToIsoWorld({ x: event.clientX, y: event.clientY }, true)
    if (!world) return
    isoDragRef.current = { ...selection, cur: world }
    setIsoDrag(isoDragRef.current)
  }

  const endIsoPointer = (event: React.PointerEvent<SVGSVGElement>) => {
    if (isoPanRef.current?.pointerId === event.pointerId) {
      isoPanRef.current = null
    } else if (isoDragRef.current?.pointerId === event.pointerId) {
      const selection = isoDragRef.current
      isoDragRef.current = null
      setIsoDrag(null)
      if (map && !savingRef.current) {
        const bounds = worldBoundsFromPoints(selection.start, selection.cur)
        const minimum = numericMapMetadata(map).resolution
        if (bounds.maxX - bounds.minX < minimum || bounds.maxY - bounds.minY < minimum) {
          showWarn('구역을 조금 더 크게 드래그해 주세요')
        } else {
          beginCreateZone(bounds)
        }
      }
    }
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId)
    }
  }

  const openEdit = (z: DraftZone) => {
    if (savingRef.current) return
    setEditingId(z.id)
    setDraftBounds(z.bounds)
    setDraftType(z.type)
    setNameInput(z.label)
    setNameModalOpen(true)
  }

  const closeNameModal = () => {
    setNameModalOpen(false)
    setDraftBounds(null)
    setEditingId(null)
    setNameInput('')
  }

  const confirmName = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (savingRef.current) return
    // 유형 변경으로 도착지가 둘이 되는 것도 막는다
    if (
      draftType === '도착지' &&
      zones.some((z) => z.type === '도착지' && z.id !== editingId)
    ) {
      showWarn('도착지는 한 곳만 등록할 수 있습니다')
      closeNameModal()
      return
    }
    const label = nameInput.trim() || draftType
    if (editingId != null) {
      setZones((zs) => zs.map((z) => (z.id === editingId ? { ...z, type: draftType, label } : z)))
    } else if (draftBounds) {
      setZones((zs) => [
        ...zs,
        { id: `draft-${++idRef.current}`, type: draftType, label, bounds: draftBounds },
      ])
    }
    setIsZoneDirty(true)
    closeNameModal()
  }

  const removeEditing = () => {
    if (savingRef.current) return
    if (editingId != null) {
      setZones((zs) => zs.filter((z) => z.id !== editingId))
      setIsZoneDirty(true)
    }
    closeNameModal()
  }

  const saveZones = async () => {
    if (!map || savingRef.current) return
    const requests: ZoneCreateRequest[] = zones.map((zone) => {
      return {
        name: zone.label,
        type: zoneTypeCode[zone.type],
        startX: zone.bounds.minX,
        startY: zone.bounds.minY,
        endX: zone.bounds.maxX,
        endY: zone.bounds.maxY,
      }
    })

    savingRef.current = true
    setIsSaving(true)
    setSaveError(undefined)
    try {
      const registeredZones = await mapApi.replaceZones(mapId, {
        mapVersion: map.mapVersion,
        zones: requests,
      })
      setSavedZones(registeredZones)
      setIsZoneDirty(false)
      setZones(registeredZones.map((zone) => {
        const bounds = zoneBounds(zone)
        return {
          id: zone.zoneId,
          zoneId: zone.zoneId,
          type: zoneTypeLabel[zone.type],
          label: zone.name,
          bounds,
        }
      }))
      setEditorStage('waypoints')
    } catch (reason) {
      setSaveError(reason instanceof Error ? reason.message : '구역 저장에 실패했습니다.')
    } finally {
      savingRef.current = false
      setIsSaving(false)
    }
  }

  const dragRect = drag ? toRect(drag.start, drag.cur) : null
  const dragBounds = map && dragRect
    ? gridRectToWorldBounds(map, dragRect, COLS, ROWS)
    : null
  const dragBad = dragBounds != null && zones.some((zone) => worldBoundsOverlap(zone.bounds, dragBounds))
  const isoDragBounds = isoDrag ? worldBoundsFromPoints(isoDrag.start, isoDrag.cur) : null
  const isoDragBad = isoDragBounds != null && zones.some((zone) => worldBoundsOverlap(zone.bounds, isoDragBounds))
  const modalRect = map && draftBounds
    ? worldBoundsToGridRect(map, draftBounds, COLS, ROWS)
    : null
  const isoBasePoints = isoProjection
    ? [
        { x: 0, y: 0 },
        { x: isoProjection.mapWidth, y: 0 },
        { x: isoProjection.mapWidth, y: isoProjection.mapHeight },
        { x: 0, y: isoProjection.mapHeight },
      ].map((point) => mapPixelToIsometric(isoProjection, point))
    : []

  if (editorStage === 'waypoints' && map && mapImageUrl) {
    return (
      <StepWaypoints
        map={map}
        mapImageUrl={mapImageUrl}
        zones={savedZones}
        onPrev={() => setEditorStage('zones')}
        onComplete={() => onComplete(savedZones.map((zone) => ({
          id: String(zone.zoneId),
          type: zoneTypeLabel[zone.type],
          label: zone.name,
          rect: worldBoundsToGridRect(map, zoneBounds(zone), COLS, ROWS),
        })))}
      />
    )
  }

  return (
    <div>
      <div className="au-editor-steps" aria-label="맵 등록 세부 단계">
        <span aria-current="step">1. 구역 설정</span>
        <span>2. 순찰 경로 설정</span>
      </div>
      <div className="au-map">
        {/* 좌: 구역 유형 팔레트 */}
        <div className="au-kinds">
          {ZONE_TYPES.map((t) => (
            <button
              key={t}
              type="button"
              className="au-kind"
              onClick={() => {
                if (!savingRef.current) setSelectedType(t)
              }}
              aria-pressed={selectedType === t}
              disabled={isSaving}
            >
              <span className="sw" style={toneVar(t)} />
              {t}
            </button>
          ))}
        </div>

        {/* 우: IoT 그리드 맵 */}
        <div>
          <div className="au-mhead">
            {warn && (
              <span className="au-warn" role="alert">
                <svg viewBox="0 0 24 24"><path d="M12 8v5M12 16.5h.01" /><circle cx="12" cy="12" r="9" /></svg>
                {warn}
              </span>
            )}
            <span className="hint">구역 유형 선택 후 맵 위를 드래그하세요 (구역을 누르면 이름 수정 · ✕로 삭제)</span>
          </div>

          <div className="au-map-view-tools" aria-label="지도 보기 방식">
            <button
              type="button"
              className="btn btn-s"
              aria-pressed={viewMode === '2d'}
              onClick={() => setViewMode('2d')}
              disabled={isSaving}
            >
              2D
            </button>
            <button
              type="button"
              className="btn btn-s"
              aria-pressed={viewMode === '2.5d'}
              onClick={() => setViewMode('2.5d')}
              disabled={isSaving || !isoProjection}
            >
              2.5D
            </button>
            {viewMode === '2.5d' && (
              <span className="au-iso-controls">
                <button
                  type="button"
                  className="btn btn-s"
                  aria-label="2.5D 지도 축소"
                  onClick={() => setIsoView((view) => ({ ...view, zoom: Math.max(0.75, view.zoom / 1.2) }))}
                >−</button>
                <button
                  type="button"
                  className="btn btn-s"
                  aria-label="2.5D 지도 확대"
                  onClick={() => setIsoView((view) => ({ ...view, zoom: Math.min(3, view.zoom * 1.2) }))}
                >+</button>
                <button
                  type="button"
                  className="btn btn-s"
                  onClick={() => setIsoView(DEFAULT_ISO_VIEW)}
                >초기화</button>
                <span className="hint">오른쪽 버튼 드래그로 이동</span>
              </span>
            )}
          </div>

          {viewMode === '2d' ? (
            <div className="au-canvas">
              <div className="au-colh" style={{ gridTemplateColumns: `repeat(${COLS}, 1fr)` }}>
                {Array.from({ length: COLS }, (_, i) => (
                  <span key={i}>{colLabel(i)}</span>
                ))}
              </div>
              <div className="au-rowh" style={{ gridTemplateRows: `repeat(${ROWS}, 1fr)` }}>
                {Array.from({ length: ROWS }, (_, i) => (
                  <span key={i}>{i + 1}</span>
                ))}
              </div>
              <div
                ref={gridRef}
                role="application"
                aria-label="IoT 맵 — 드래그하여 구역 지정"
                aria-disabled={isSaving}
                className="au-cells"
                style={{
                  gridTemplateColumns: `repeat(${COLS}, 1fr)`,
                  gridTemplateRows: `repeat(${ROWS}, 1fr)`,
                  aspectRatio: map ? `${map.width} / ${map.height}` : '2 / 1',
                }}
                onPointerDown={onPointerDown}
                onPointerMove={onPointerMove}
                onPointerUp={onPointerUp}
              >
                {mapImageUrl && (
                  <img src={mapImageUrl} alt={map?.mapName ?? '완성된 지도'} draggable={false} />
                )}
                {Array.from({ length: COLS * ROWS }, (_, i) => (
                  <div key={i} className="cell" aria-hidden />
                ))}

                {map && zones.map((zone) => {
                  const rect = worldBoundsToGridRect(map, zone.bounds, COLS, ROWS)
                  return (
                    <div
                      key={zone.id}
                      className="au-zone"
                      style={{ ...rectStyle(rect), ...toneVar(zone.type) }}
                      title={`${zone.label} · ${rangeName(rect)}`}
                      onPointerDown={(event) => event.stopPropagation()}
                      onClick={() => openEdit(zone)}
                      aria-disabled={isSaving}
                    >
                      <span className="zl">{zone.label}</span>
                      <button
                        type="button"
                        className="zx"
                        aria-label={`${zone.label} 삭제`}
                        disabled={isSaving}
                        onClick={(event) => {
                          event.stopPropagation()
                          if (savingRef.current) return
                          setZones((current) => current.filter((item) => item.id !== zone.id))
                          setIsZoneDirty(true)
                        }}
                      >
                        <svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18" /></svg>
                      </button>
                    </div>
                  )
                })}

                {dragRect && (
                  <div
                    aria-hidden
                    className={dragBad ? 'au-draft bad' : 'au-draft'}
                    style={rectStyle(dragRect)}
                  />
                )}
              </div>
            </div>
          ) : (
            <div className="au-iso-canvas" aria-disabled={isSaving}>
              {map && isoProjection && (
                <svg
                  ref={isoSvgRef}
                  role="application"
                  aria-label="2.5D IoT 맵 — 왼쪽 버튼으로 드래그하여 구역 지정"
                  viewBox={`0 0 ${isoProjection.viewWidth} ${isoProjection.viewHeight}`}
                  preserveAspectRatio="xMidYMid meet"
                  onPointerDown={onIsoPointerDown}
                  onPointerMove={onIsoPointerMove}
                  onPointerUp={endIsoPointer}
                  onPointerCancel={endIsoPointer}
                  onContextMenu={(event) => event.preventDefault()}
                >
                  <g transform={`translate(${isoView.panX} ${isoView.panY}) scale(${isoView.zoom})`}>
                    <Map25DBase
                      metadata={map}
                      projection={isoProjection}
                      mapImageUrl={mapImageUrl}
                      wallOffset={MAP_25D_WALL_HEIGHT_PX}
                    />
                    <g className="au-iso-grid" aria-hidden>
                      {Array.from({ length: COLS + 1 }, (_, index) => {
                        const x = (index / COLS) * isoProjection.mapWidth
                        const start = mapPixelToIsometric(isoProjection, { x, y: 0 })
                        const end = mapPixelToIsometric(isoProjection, { x, y: isoProjection.mapHeight })
                        return <line key={`c-${index}`} x1={start.x} y1={start.y} x2={end.x} y2={end.y} />
                      })}
                      {Array.from({ length: ROWS + 1 }, (_, index) => {
                        const y = (index / ROWS) * isoProjection.mapHeight
                        const start = mapPixelToIsometric(isoProjection, { x: 0, y })
                        const end = mapPixelToIsometric(isoProjection, { x: isoProjection.mapWidth, y })
                        return <line key={`r-${index}`} x1={start.x} y1={start.y} x2={end.x} y2={end.y} />
                      })}
                    </g>
                    <polygon className="au-iso-hit" points={pointsAttribute(isoBasePoints)} />

                    {zones.map((zone) => {
                      const points = worldBoundsToIsometricPolygon(map, isoProjection, zone.bounds)
                      const center = points.reduce(
                        (sum, point) => ({ x: sum.x + point.x / points.length, y: sum.y + point.y / points.length }),
                        { x: 0, y: 0 },
                      )
                      const labelWidth = Math.max(42, Math.min(128, zone.label.length * 7 + 18))
                      return (
                        <g
                          key={zone.id}
                          className="au-iso-zone"
                          style={toneVar(zone.type)}
                          onPointerDown={(event) => event.stopPropagation()}
                          onClick={() => openEdit(zone)}
                        >
                          <polygon points={pointsAttribute(points)} />
                          <g className="au-iso-zone-label" transform={`translate(${center.x - labelWidth / 2} ${center.y - 23})`}>
                            <rect width={labelWidth} height="20" rx="10" />
                            <text x={labelWidth / 2} y="13">{zone.label}</text>
                          </g>
                        </g>
                      )
                    })}

                    {isoDragBounds && (
                      <polygon
                        aria-hidden
                        className={isoDragBad ? 'au-iso-draft bad' : 'au-iso-draft'}
                        points={pointsAttribute(worldBoundsToIsometricPolygon(map, isoProjection, isoDragBounds))}
                      />
                    )}
                  </g>
                </svg>
              )}
            </div>
          )}
        </div>
      </div>

      {zones.length > 0 && (
        <div className="au-mfoot">
          <span className="au-note">
            <svg viewBox="0 0 24 24"><path d="m5 13 4.5 4.5L19 7" /></svg>
            <span>
              {savedZones.length > 0 && !isZoneDirty
                ? <>저장된 구역 <b className="num">{zones.length}</b>곳을 유지하면 기존 경로만 바로 편집할 수 있습니다.</>
                : <>구역 <b className="num">{zones.length}</b>곳을 저장한 뒤 순찰 지점을 순서대로 설정합니다.</>}
            </span>
          </span>
        </div>
      )}
      {loadError && <p role="alert" className="au-err">{loadError}</p>}
      {saveError && <p role="alert" className="au-err">{saveError}</p>}

      <div className="au-act au-editor-actions">
        <button
          type="button"
          className="btn btn-s btn-add"
          onClick={() => {
            if (!savingRef.current) onPrev()
          }}
          disabled={isSaving}
        >
          <svg viewBox="0 0 24 24"><path d="M19 12H6M13 5l-7 7 7 7" /></svg>
          이전
        </button>
        <span className="grow" />
        {savedZones.length > 0 && !isZoneDirty && (
          <button
            type="button"
            className="btn btn-s"
            onClick={() => {
              if (!savingRef.current) setEditorStage('waypoints')
            }}
            disabled={isSaving}
          >
            기존 구역 유지 · 경로만 편집
          </button>
        )}
        <button
          type="button"
          className="btn btn-p btn-add"
          onClick={saveZones}
          disabled={zones.length === 0 || !map || isSaving}
        >
          {isSaving ? '저장 중…' : '구역 저장 후 경로 설정'}
          <svg viewBox="0 0 24 24"><path d="M5 12h13M12 5l7 7-7 7" /></svg>
        </button>
      </div>

      {/* 구역 이름 지정/수정 모달 */}
      <R0KiModal
        open={nameModalOpen}
        onClose={() => {
          if (!savingRef.current) closeNameModal()
        }}
        title={editingId != null ? '구역 정보 수정' : '구역 이름 지정'}
      >
        <form onSubmit={confirmName}>
          {modalRect && (
            <p className="mdsub">
              선택 영역 <b>{rangeName(modalRect)}</b> · <b>{sizeName(modalRect)}</b>
            </p>
          )}

          <span className="mdlabel">구역 유형</span>
          <div className="zkinds">
            {ZONE_TYPES.map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setDraftType(t)}
                aria-pressed={draftType === t}
                disabled={isSaving}
              >
                <span className="sw" style={toneVar(t)} />
                {t}
              </button>
            ))}
          </div>

          <span className="mdlabel" style={{ marginTop: 'var(--s5)' }}>구역 이름</span>
          <input
            className="mdin"
            value={nameInput}
            onChange={(e) => setNameInput(e.target.value)}
            maxLength={20}
            placeholder="예: 지하 1층 주차장"
            autoFocus
            disabled={isSaving}
          />
          <p className="mdhelp">경비원이 알림에서 보게 될 이름입니다. 비워두면 유형 이름으로 저장됩니다.</p>

          <div className="mdact split">
            {editingId != null ? (
              <button type="button" className="mddel" onClick={removeEditing} disabled={isSaving}>구역 삭제</button>
            ) : (
              <span />
            )}
            <span className="right">
              <button type="button" className="btn btn-s" onClick={closeNameModal} disabled={isSaving}>취소</button>
              <button type="submit" className="btn btn-p" disabled={isSaving}>{editingId != null ? '저장' : '등록'}</button>
            </span>
          </div>
        </form>
      </R0KiModal>
    </div>
  )
}

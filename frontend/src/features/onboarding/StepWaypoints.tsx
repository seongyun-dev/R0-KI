import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import type {
  MapDetailResponse,
  WaypointActionCode,
  ZoneCreateResponse,
  ZoneTypeCode,
} from '../../api/contracts'
import { mapApi } from '../../api/services'
import {
  isWorldPointInBounds,
  mapRatiosToWorld,
  worldToMapRatios,
  zoneBounds,
} from './mapCoordinates'
import {
  DEFAULT_ACCEPTANCE_RADIUS,
  toWaypointRequests,
  validateNavigationWaypoints,
  type EditableWaypoint,
} from './navigationEditor'

export type StepWaypointsProps = {
  map: MapDetailResponse
  mapImageUrl: string
  zones: ZoneCreateResponse[]
  onPrev: () => void
  onComplete: () => void
}

const COLS = 14
const ROWS = 7
const colLabel = (index: number) => String.fromCharCode(65 + index)
const KEYBOARD_MOVES: Record<string, { column: number; row: number }> = {
  ArrowLeft: { column: -1, row: 0 },
  ArrowRight: { column: 1, row: 0 },
  ArrowUp: { column: 0, row: -1 },
  ArrowDown: { column: 0, row: 1 },
}

const ACTIONS: { value: WaypointActionCode; label: string }[] = [
  { value: 'PASS', label: '그대로 통과' },
  { value: 'SCAN', label: '촬영·탐지' },
  { value: 'DESTINATION', label: '순찰 종료' },
]

const zoneTone: Record<ZoneTypeCode, string> = {
  START: 'detect',
  PARKING: 'patrol',
  RECYCLING_AREA: 'charge',
  DANGER_ZONE: 'alert',
  DESTINATION: 'offline',
}

const toneVar = (type: ZoneTypeCode) =>
  ({ '--z': `var(--${zoneTone[type]})` }) as CSSProperties

function zoneStyle(map: MapDetailResponse, zone: ZoneCreateResponse) {
  const bounds = zoneBounds(zone)
  const topLeft = worldToMapRatios(map, { x: bounds.minX, y: bounds.maxY })
  const bottomRight = worldToMapRatios(map, { x: bounds.maxX, y: bounds.minY })
  return {
    left: `${topLeft.xRatio * 100}%`,
    top: `${topLeft.yRatio * 100}%`,
    width: `${(bottomRight.xRatio - topLeft.xRatio) * 100}%`,
    height: `${(bottomRight.yRatio - topLeft.yRatio) * 100}%`,
  }
}

function markerStyle(map: MapDetailResponse, waypoint: EditableWaypoint) {
  const ratios = worldToMapRatios(map, waypoint)
  return {
    left: `${ratios.xRatio * 100}%`,
    top: `${ratios.yRatio * 100}%`,
  }
}

function mapGridPosition(map: MapDetailResponse, waypoint: EditableWaypoint) {
  const ratios = worldToMapRatios(map, waypoint)
  const column = Math.max(0, Math.min(COLS - 1, Math.floor(ratios.xRatio * COLS)))
  const row = Math.max(0, Math.min(ROWS - 1, Math.floor(ratios.yRatio * ROWS)))
  return `${colLabel(column)}${row + 1}`
}

function defaultAction(zone: ZoneCreateResponse | undefined): WaypointActionCode {
  if (zone?.type === 'PARKING') return 'SCAN'
  if (zone?.type === 'DESTINATION') return 'DESTINATION'
  return 'PASS'
}

/** 구역과 독립된 순서형 Nav2 경로 편집기. 구역 중심점으로 자동 변환하지 않는다. */
export function StepWaypoints({
  map,
  mapImageUrl,
  zones,
  onPrev,
  onComplete,
}: StepWaypointsProps) {
  const idRef = useRef(0)
  const [waypoints, setWaypoints] = useState<EditableWaypoint[]>([])
  const [selectedKey, setSelectedKey] = useState<string>()
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const savingRef = useRef(false)
  const [loadError, setLoadError] = useState<string>()
  const [saveError, setSaveError] = useState<string>()
  const [reloadKey, setReloadKey] = useState(0)
  const [keyboardCell, setKeyboardCell] = useState({
    column: Math.floor(COLS / 2),
    row: Math.floor(ROWS / 2),
  })

  useEffect(() => {
    let active = true
    setIsLoading(true)
    setLoadError(undefined)
    void mapApi.waypoints(map.mapId)
      .then((response) => {
        if (!active) return
        if (
          String(response.mapId) !== String(map.mapId) ||
          Number(response.mapVersion) !== Number(map.mapVersion)
        ) {
          throw new Error('현재 지도 버전과 저장된 순찰 경로 버전이 일치하지 않습니다.')
        }
        const loaded = [...response.waypoints]
          .sort((left, right) => left.sequence - right.sequence)
        if (!loaded.every((waypoint, index) => waypoint.sequence === index + 1)) {
          throw new Error('저장된 순찰 지점 순서가 1부터 연속되지 않습니다.')
        }
        setWaypoints(loaded.map<EditableWaypoint>((waypoint) => ({
            key: `saved-${String(waypoint.waypointId)}`,
            waypointId: waypoint.waypointId,
            x: Number(waypoint.x),
            y: Number(waypoint.y),
            action: waypoint.action,
            yaw: waypoint.yaw == null ? null : Number(waypoint.yaw),
            acceptanceRadius:
              waypoint.acceptanceRadius == null
                ? DEFAULT_ACCEPTANCE_RADIUS
                : Number(waypoint.acceptanceRadius),
            zoneId: waypoint.zoneId ?? null,
          })))
      })
      .catch((reason) => {
        if (active) {
          setLoadError(
            reason instanceof Error ? reason.message : '저장된 순찰 경로를 불러오지 못했습니다.',
          )
        }
      })
      .finally(() => {
        if (active) setIsLoading(false)
      })
    return () => {
      active = false
    }
  }, [map.mapId, map.mapVersion, reloadKey])

  const validationErrors = useMemo(
    () => validateNavigationWaypoints(map, waypoints, zones),
    [map, waypoints, zones],
  )

  const routePoints = waypoints.map((waypoint) => {
    const ratios = worldToMapRatios(map, waypoint)
    return `${ratios.xRatio * 100},${ratios.yRatio * 100}`
  }).join(' ')

  const patchWaypoint = (key: string, patch: Partial<EditableWaypoint>) => {
    if (savingRef.current) return
    setWaypoints((current) =>
      current.map((waypoint) => waypoint.key === key ? { ...waypoint, ...patch } : waypoint),
    )
    setSaveError(undefined)
  }

  const moveWaypoint = (index: number, offset: -1 | 1) => {
    if (savingRef.current) return
    const target = index + offset
    if (target < 0 || target >= waypoints.length) return
    setWaypoints((current) => {
      const next = [...current]
      const [moved] = next.splice(index, 1)
      next.splice(target, 0, moved)
      return next
    })
    setSaveError(undefined)
  }

  const addWaypointAt = (point: { x: number; y: number }) => {
    if (isLoading || loadError || savingRef.current) return
    const zone = zones.find((candidate) =>
      isWorldPointInBounds(point, zoneBounds(candidate)),
    )
    const key = `draft-${++idRef.current}`
    setWaypoints((current) => [
      ...current,
      {
        key,
        x: point.x,
        y: point.y,
        action: defaultAction(zone),
        yaw: null,
        acceptanceRadius: DEFAULT_ACCEPTANCE_RADIUS,
        zoneId: zone?.zoneId ?? null,
      },
    ])
    setSelectedKey(key)
    setSaveError(undefined)
  }

  const addWaypoint = (event: React.MouseEvent<HTMLDivElement>) => {
    const rect = event.currentTarget.getBoundingClientRect()
    addWaypointAt(mapRatiosToWorld(map, {
      xRatio: (event.clientX - rect.left) / rect.width,
      yRatio: (event.clientY - rect.top) / rect.height,
    }))
  }

  const handleMapKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (
      event.target !== event.currentTarget ||
      isLoading || loadError || savingRef.current
    ) return

    const movement = KEYBOARD_MOVES[event.key]
    if (movement) {
      event.preventDefault()
      setKeyboardCell((current) => ({
        column: Math.max(0, Math.min(COLS - 1, current.column + movement.column)),
        row: Math.max(0, Math.min(ROWS - 1, current.row + movement.row)),
      }))
      return
    }
    if (event.key !== 'Enter' && event.key !== ' ') return

    event.preventDefault()
    addWaypointAt(mapRatiosToWorld(map, {
      xRatio: (keyboardCell.column + 0.5) / COLS,
      yRatio: (keyboardCell.row + 0.5) / ROWS,
    }))
  }

  const saveWaypoints = async () => {
    if (validationErrors.length > 0 || loadError || savingRef.current) return
    const requestWaypoints = toWaypointRequests(waypoints)
    savingRef.current = true
    setIsSaving(true)
    setSaveError(undefined)
    try {
      await mapApi.replaceWaypoints(map.mapId, {
        mapVersion: map.mapVersion,
        waypoints: requestWaypoints,
      })
      onComplete()
    } catch (reason) {
      setSaveError(reason instanceof Error ? reason.message : '순찰 경로 저장에 실패했습니다.')
    } finally {
      savingRef.current = false
      setIsSaving(false)
    }
  }

  return (
    <div>
      <div className="au-editor-steps" aria-label="맵 등록 세부 단계">
        <span className="done">1. 구역 설정</span>
        <span aria-current="step">2. 순찰 경로 설정</span>
      </div>

      <div className="au-route-editor">
        <div>
          <div className="au-mhead">
            <span className="hint">
              지도 위를 눌러 실제 경유 지점을 추가하세요.
            </span>
          </div>
          <div className="au-canvas au-route-canvas">
            <div className="au-colh" style={{ gridTemplateColumns: `repeat(${COLS}, 1fr)` }}>
              {Array.from({ length: COLS }, (_, index) => (
                <span key={index}>{colLabel(index)}</span>
              ))}
            </div>
            <div className="au-rowh" style={{ gridTemplateRows: `repeat(${ROWS}, 1fr)` }}>
              {Array.from({ length: ROWS }, (_, index) => (
                <span key={index}>{index + 1}</span>
              ))}
            </div>
            <div
              role="application"
              aria-label="순찰 지점 추가 지도"
              aria-disabled={isLoading || Boolean(loadError) || isSaving}
              tabIndex={isLoading || loadError || isSaving ? -1 : 0}
              className="au-cells"
              style={{
                gridTemplateColumns: `repeat(${COLS}, 1fr)`,
                gridTemplateRows: `repeat(${ROWS}, 1fr)`,
                aspectRatio: `${map.width} / ${map.height}`,
              }}
              onClick={addWaypoint}
              onKeyDown={handleMapKeyDown}
            >
              <img src={mapImageUrl} alt={map.mapName} draggable={false} />
              {Array.from({ length: COLS * ROWS }, (_, index) => (
                <div key={index} className="cell" aria-hidden />
              ))}
              {zones.map((zone) => (
                <div
                  key={String(zone.zoneId)}
                  className="au-route-zone"
                  style={{ ...zoneStyle(map, zone), ...toneVar(zone.type) }}
                  aria-hidden
                >
                  {zone.name}
                </div>
              ))}
              {waypoints.length > 1 && (
                <svg
                  className="au-route-line"
                  viewBox="0 0 100 100"
                  preserveAspectRatio="none"
                  aria-hidden
                >
                  <polyline points={routePoints} />
                </svg>
              )}
              <span
                className="au-keyboard-cursor"
                style={{
                  left: `${((keyboardCell.column + 0.5) / COLS) * 100}%`,
                  top: `${((keyboardCell.row + 0.5) / ROWS) * 100}%`,
                }}
                aria-hidden
              />
              {waypoints.map((waypoint, index) => (
                <button
                  key={waypoint.key}
                  type="button"
                  className={`au-waypoint ${waypoint.action.toLowerCase()}${selectedKey === waypoint.key ? ' selected' : ''}`}
                  style={markerStyle(map, waypoint)}
                  aria-label={`${index + 1}번 지점 설정 선택`}
                  disabled={isSaving}
                  onPointerDown={(event) => event.stopPropagation()}
                  onClick={(event) => {
                    event.stopPropagation()
                    if (savingRef.current) return
                    setSelectedKey(waypoint.key)
                    document.getElementById(`waypoint-${waypoint.key}`)?.scrollIntoView({ block: 'nearest' })
                  }}
                >
                  {index + 1}
                </button>
              ))}
              {(isLoading || loadError || isSaving) && <span className="au-route-mask" aria-hidden />}
            </div>
          </div>
        </div>

        <aside className="au-route-side" aria-label="순찰 경로 순서">
          <div className="au-route-side-head">
            <span>순찰 지점</span>
            <b className="num">{waypoints.length}</b>
          </div>

          {isLoading ? (
            <div className="au-route-empty"><span className="au-spin" />저장된 경로 확인 중…</div>
          ) : loadError ? (
            <div className="au-route-empty bad" role="alert">
              <span>{loadError}</span>
              <button type="button" className="btn btn-s" onClick={() => setReloadKey((value) => value + 1)}>
                다시 시도
              </button>
            </div>
          ) : waypoints.length === 0 ? (
            <div className="au-route-empty">지도 위를 눌러 첫 지점을 추가해 주세요.</div>
          ) : (
            <ol className="au-route-list">
              {waypoints.map((waypoint, index) => (
                <li
                  id={`waypoint-${waypoint.key}`}
                  key={waypoint.key}
                  className={selectedKey === waypoint.key ? 'selected' : ''}
                >
                  <div className="au-route-item-head">
                    <button
                      type="button"
                      className="au-route-number"
                      onClick={() => {
                        if (!savingRef.current) setSelectedKey(waypoint.key)
                      }}
                      aria-label={`${index + 1}번 지점 선택`}
                      disabled={isSaving}
                    >
                      {index + 1}
                    </button>
                    <span
                      className="au-route-position"
                      title={`정밀 좌표 x ${waypoint.x.toFixed(2)}, y ${waypoint.y.toFixed(2)}`}
                    >
                      <span>지도 위치</span>
                      <b>{mapGridPosition(map, waypoint)}</b>
                    </span>
                    <span className="au-route-move">
                      <button
                        type="button"
                        onClick={() => moveWaypoint(index, -1)}
                        disabled={isSaving || index === 0}
                        aria-label={`${index + 1}번 지점을 앞으로 이동`}
                      >↑</button>
                      <button
                        type="button"
                        onClick={() => moveWaypoint(index, 1)}
                        disabled={isSaving || index === waypoints.length - 1}
                        aria-label={`${index + 1}번 지점을 뒤로 이동`}
                      >↓</button>
                      <button
                        type="button"
                        className="del"
                        onClick={() => {
                          if (savingRef.current) return
                          setWaypoints((current) => current.filter((item) => item.key !== waypoint.key))
                          if (selectedKey === waypoint.key) setSelectedKey(undefined)
                        }}
                        aria-label={`${index + 1}번 지점 삭제`}
                        disabled={isSaving}
                      >×</button>
                    </span>
                  </div>

                  <div className="au-route-fields">
                    <label>
                      <span>이 지점에서 할 일</span>
                      <select
                        value={waypoint.action}
                        disabled={isSaving}
                        onChange={(event) =>
                          patchWaypoint(waypoint.key, { action: event.target.value as WaypointActionCode })
                        }
                      >
                        {ACTIONS.map((action) => (
                          <option key={action.value} value={action.value}>{action.label}</option>
                        ))}
                      </select>
                    </label>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </aside>
      </div>

      {!isLoading && !loadError && validationErrors.length > 0 && (
        <div className="au-route-errors" role="alert">
          <b>저장 전 확인</b>
          <ul>{validationErrors.map((message) => <li key={message}>{message}</li>)}</ul>
        </div>
      )}
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
          구역 설정
        </button>
        <span className="grow" />
        <button
          type="button"
          className="btn btn-p btn-add"
          onClick={saveWaypoints}
          disabled={isLoading || Boolean(loadError) || validationErrors.length > 0 || isSaving}
        >
          {isSaving ? '저장 중…' : '경로 저장 후 가입 완료'}
          <svg viewBox="0 0 24 24"><path d="M5 12h13M12 5l7 7-7 7" /></svg>
        </button>
      </div>
    </div>
  )
}

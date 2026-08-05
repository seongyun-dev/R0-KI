import { useEffect, useRef, useState, type CSSProperties, type FormEvent } from 'react'
import type { MapDetailResponse, ZoneCreateRequest, ZoneTypeCode } from '../../api/contracts'
import { mapApi } from '../../api/services'
import { R0KiModal } from '../../components/layout/R0KiModal'
import type { Zone, ZoneType } from '../../types/domain'

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

/* 구역 색 — 상태 명도 램프 토큰. 색만으로 구분하지 않도록 이름을 함께 표기(3중 표기) */
const zoneTone: Record<ZoneType, string> = {
  주차장: 'patrol',
  분리수거장: 'charge',
  출입구: 'detect',
  도착지: 'offline',
  기타: 'offline',
}
const toneVar = (type: ZoneType) => ({ '--z': `var(--${zoneTone[type]})` }) as CSSProperties

type Rect = { x: number; y: number; w: number; h: number }
type DraftZone = { id: number; type: ZoneType; label: string; rect: Rect }

const toRect = (a: { c: number; r: number }, b: { c: number; r: number }): Rect => ({
  x: Math.min(a.c, b.c),
  y: Math.min(a.r, b.r),
  w: Math.abs(a.c - b.c) + 1,
  h: Math.abs(a.r - b.r) + 1,
})

// 두 사각형이 한 칸이라도 겹치는지 (겹침 방지용)
const overlaps = (a: Rect, b: Rect) =>
  a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y

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

/** Step 3/3 — 구역 지정 (IoT 수신 맵 위 드래그) (1y). R0Kiauth 시안 pMap 상태 C */
export function StepZones({ mapId, onPrev, onComplete }: StepZonesProps) {
  const gridRef = useRef<HTMLDivElement>(null)
  const idRef = useRef(0)
  const [selectedType, setSelectedType] = useState<ZoneType>('주차장')
  const [zones, setZones] = useState<DraftZone[]>([])
  // 드래그 상태는 ref가 진실원천(포인터 이벤트가 리렌더보다 빠를 수 있음), state는 프리뷰 렌더용
  const dragRef = useRef<{ start: { c: number; r: number }; cur: { c: number; r: number } } | null>(null)
  const [drag, setDrag] = useState<typeof dragRef.current>(null)
  // 구역 이름 입력/수정 모달 — 드래그로 그린 직후, 또는 기존 구역 클릭 시
  const [nameModalOpen, setNameModalOpen] = useState(false)
  const [nameInput, setNameInput] = useState('')
  const [draftRect, setDraftRect] = useState<Rect | null>(null)
  const [draftType, setDraftType] = useState<ZoneType>('주차장')
  const [editingId, setEditingId] = useState<number | null>(null)
  const [map, setMap] = useState<MapDetailResponse>()
  const [mapImageUrl, setMapImageUrl] = useState<string>()
  const [loadError, setLoadError] = useState<string>()
  const [saveError, setSaveError] = useState<string>()
  const [isSaving, setIsSaving] = useState(false)
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
        const detail = await mapApi.detail(mapId)
        const blob = await mapApi.file(detail.mapUrl, controller.signal)
        objectUrl = URL.createObjectURL(blob)
        setMap(detail)
        setMapImageUrl(objectUrl)
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
    if (!dragRef.current) return
    dragRef.current = { ...dragRef.current, cur: cellAt(e) }
    setDrag(dragRef.current)
  }
  const onPointerUp = () => {
    const d = dragRef.current
    if (!d) return
    dragRef.current = null
    setDrag(null)
    const rect = toRect(d.start, d.cur)

    // 겹침 방지: 기존 구역과 겹치면 등록 취소
    if (zones.some((z) => overlaps(z.rect, rect))) {
      showWarn('다른 구역과 겹칠 수 없습니다')
      return
    }
    // 도착지는 맵당 한 곳만
    if (selectedType === '도착지' && zones.some((z) => z.type === '도착지')) {
      showWarn('도착지는 한 곳만 등록할 수 있습니다')
      return
    }

    // 이름 지정 모달 오픈
    const count = zones.filter((z) => z.type === selectedType).length
    setDraftRect(rect)
    setDraftType(selectedType)
    setEditingId(null)
    setNameInput(`${selectedType} ${count + 1}`)
    setNameModalOpen(true)
  }

  const openEdit = (z: DraftZone) => {
    setEditingId(z.id)
    setDraftRect(z.rect)
    setDraftType(z.type)
    setNameInput(z.label)
    setNameModalOpen(true)
  }

  const closeNameModal = () => {
    setNameModalOpen(false)
    setDraftRect(null)
    setEditingId(null)
    setNameInput('')
  }

  const confirmName = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
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
    } else if (draftRect) {
      setZones((zs) => [...zs, { id: ++idRef.current, type: draftType, label, rect: draftRect }])
    }
    closeNameModal()
  }

  const removeEditing = () => {
    if (editingId != null) {
      setZones((zs) => zs.filter((z) => z.id !== editingId))
    }
    closeNameModal()
  }

  const saveZones = async () => {
    if (!map) return
    const resolution = Number(map.resolution)
    const originX = Number(map.originX)
    const originY = Number(map.originY)
    const requests: ZoneCreateRequest[] = zones.map((zone) => {
      const leftPixel = (zone.rect.x / COLS) * map.width
      const rightPixel = ((zone.rect.x + zone.rect.w) / COLS) * map.width
      const topPixel = (zone.rect.y / ROWS) * map.height
      const bottomPixel = ((zone.rect.y + zone.rect.h) / ROWS) * map.height
      return {
        name: zone.label,
        type: zoneTypeCode[zone.type],
        startX: originX + leftPixel * resolution,
        startY: originY + (map.height - bottomPixel) * resolution,
        endX: originX + rightPixel * resolution,
        endY: originY + (map.height - topPixel) * resolution,
      }
    })

    setIsSaving(true)
    setSaveError(undefined)
    try {
      await mapApi.registerZones(mapId, requests)
      onComplete(zones.map((z) => ({ id: `Z-${z.id}`, type: z.type, label: z.label, rect: z.rect })))
    } catch (reason) {
      setSaveError(reason instanceof Error ? reason.message : '구역 저장에 실패했습니다.')
    } finally {
      setIsSaving(false)
    }
  }

  const dragRect = drag ? toRect(drag.start, drag.cur) : null
  const dragBad = dragRect != null && zones.some((z) => overlaps(z.rect, dragRect))

  return (
    <div>
      <div className="au-map">
        {/* 좌: 구역 유형 팔레트 */}
        <div className="au-kinds">
          {ZONE_TYPES.map((t) => (
            <button
              key={t}
              type="button"
              className="au-kind"
              onClick={() => setSelectedType(t)}
              aria-pressed={selectedType === t}
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
              {/* 그리드 셀 */}
              {Array.from({ length: COLS * ROWS }, (_, i) => (
                <div key={i} className="cell" aria-hidden />
              ))}

              {/* 등록된 구역 */}
              {zones.map((z) => (
                <div
                  key={z.id}
                  className="au-zone"
                  style={{ ...rectStyle(z.rect), ...toneVar(z.type) }}
                  title={`${z.label} · ${rangeName(z.rect)}`}
                  onPointerDown={(e) => e.stopPropagation()}
                  onClick={() => openEdit(z)}
                >
                  <span className="zl">{z.label}</span>
                  <button
                    type="button"
                    className="zx"
                    aria-label={`${z.label} 삭제`}
                    onClick={(e) => {
                      e.stopPropagation()
                      setZones((zs) => zs.filter((x) => x.id !== z.id))
                    }}
                  >
                    <svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18" /></svg>
                  </button>
                </div>
              ))}

              {/* 드래그 프리뷰 — 겹치면 즉시 경고 색 */}
              {dragRect && (
                <div
                  aria-hidden
                  className={dragBad ? 'au-draft bad' : 'au-draft'}
                  style={rectStyle(dragRect)}
                />
              )}
            </div>
          </div>
        </div>
      </div>

      {zones.length > 0 && (
        <div className="au-mfoot">
          <span className="au-note">
            <svg viewBox="0 0 24 24"><path d="m5 13 4.5 4.5L19 7" /></svg>
            <span><b>맵 등록 완료!</b> 드래그한 구역 <b className="num">{zones.length}</b>곳이 저장됩니다.</span>
          </span>
        </div>
      )}
      {loadError && <p role="alert" className="au-err">{loadError}</p>}
      {saveError && <p role="alert" className="au-err">{saveError}</p>}

      <div className="au-act">
        <button type="button" className="btn btn-s btn-add" onClick={onPrev}>
          <svg viewBox="0 0 24 24"><path d="M19 12H6M13 5l-7 7 7 7" /></svg>
          이전
        </button>
        <span className="grow" />
        <button
          type="button"
          className="btn btn-p btn-add"
          onClick={saveZones}
          disabled={zones.length === 0 || !map || isSaving}
        >
          {isSaving ? '저장 중…' : '가입 완료'}
          <svg viewBox="0 0 24 24"><path d="M5 12h13M12 5l7 7-7 7" /></svg>
        </button>
      </div>

      {/* 구역 이름 지정/수정 모달 */}
      <R0KiModal
        open={nameModalOpen}
        onClose={closeNameModal}
        title={editingId != null ? '구역 정보 수정' : '구역 이름 지정'}
      >
        <form onSubmit={confirmName}>
          {draftRect && (
            <p className="mdsub">
              선택 영역 <b>{rangeName(draftRect)}</b> · <b>{sizeName(draftRect)}</b>
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
          />
          <p className="mdhelp">경비원이 알림에서 보게 될 이름입니다. 비워두면 유형 이름으로 저장됩니다.</p>

          <div className="mdact split">
            {editingId != null ? (
              <button type="button" className="mddel" onClick={removeEditing}>구역 삭제</button>
            ) : (
              <span />
            )}
            <span className="right">
              <button type="button" className="btn btn-s" onClick={closeNameModal}>취소</button>
              <button type="submit" className="btn btn-p">{editingId != null ? '저장' : '등록'}</button>
            </span>
          </div>
        </form>
      </R0KiModal>
    </div>
  )
}

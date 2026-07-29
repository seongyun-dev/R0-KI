import { useEffect, useRef, useState, type FormEvent } from 'react'
import type { MapDetailResponse, ZoneCreateRequest, ZoneTypeCode } from '../../api/contracts'
import { mapApi } from '../../api/services'
import { CloseIcon } from '../../components/icons'
import { Button, Field, Input, Modal, StatusBadge, useToast } from '../../components/ui'
import { cn } from '../../lib/cn'
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

// 위험구역 제거 · 도착지(순찰 복귀 종료 지점) 추가
const ZONE_TYPES: ZoneType[] = ['주차장', '분리수거장', '위험구역', '출입구', '도착지']

const zoneTypeCode: Record<string, ZoneTypeCode> = {
  주차장: 'PARKING',
  분리수거장: 'RECYCLING_AREA',
  위험구역: 'DANGER_ZONE',
  출입구: 'START',
  도착지: 'DESTINATION',
}

const zoneStyle: Record<ZoneType, string> = {
  주차장: 'bg-info-soft/80 ring-info text-info',
  분리수거장: 'bg-success-soft/80 ring-success text-success',
  위험구역: 'bg-danger-soft/80 ring-danger text-danger',
  출입구: 'bg-warning-soft/80 ring-warning text-warning',
  도착지: 'bg-accent/10 ring-accent text-accent',
  기타: 'bg-surface-2/80 ring-muted text-muted',
}

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

/** Step 3/3 — 구역 지정 (IoT 수신 맵 위 드래그) (1y) */
export function StepZones({ mapId, onPrev, onComplete }: StepZonesProps) {
  const toast = useToast()
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
      toast('다른 구역과 겹칩니다 · 빈 곳에 그려주세요')
      return
    }
    // 도착지는 맵당 한 곳만
    if (selectedType === '도착지' && zones.some((z) => z.type === '도착지')) {
      toast('도착지는 한 곳만 등록할 수 있습니다')
      return
    }

    // 이름 입력 모달 오픈 (기본값을 미리 채워 수정 가능하게)
    const count = zones.filter((z) => z.type === selectedType).length
    setDraftRect(rect)
    setDraftType(selectedType)
    setEditingId(null)
    setNameInput(`${selectedType} ${count + 1}`)
    setNameModalOpen(true)
  }

  const openEdit = (z: DraftZone) => {
    setEditingId(z.id)
    setDraftRect(null)
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
    const label = nameInput.trim() || draftType
    if (editingId != null) {
      setZones((zs) => zs.map((z) => (z.id === editingId ? { ...z, label } : z)))
    } else if (draftRect) {
      setZones((zs) => [...zs, { id: ++idRef.current, type: draftType, label, rect: draftRect }])
      toast(`✓ ${label} 구역이 등록되었습니다`)
    }
    closeNameModal()
  }

  const rectStyle = (r: Rect) => ({
    left: `${(r.x / COLS) * 100}%`,
    top: `${(r.y / ROWS) * 100}%`,
    width: `${(r.w / COLS) * 100}%`,
    height: `${(r.h / ROWS) * 100}%`,
  })

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

  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-6 lg:grid-cols-[12rem_1fr]">
        {/* 좌: 구역 유형 팔레트 */}
        <div className="flex flex-row flex-wrap gap-2 lg:flex-col">
          {ZONE_TYPES.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setSelectedType(t)}
              aria-pressed={selectedType === t}
              className={cn(
                'rounded-control px-4 py-2.5 text-left text-sm font-semibold ring-1 transition-colors',
                selectedType === t ? 'bg-ink text-white ring-ink' : 'bg-bg text-muted ring-line hover:bg-surface',
              )}
            >
              {t}
            </button>
          ))}
        </div>

        {/* 우: IoT 그리드 맵 */}
        <div>
          <div className="mb-2 flex items-center justify-between">
            <span className="font-mono text-xs font-bold tracking-wider text-muted">[ IoT MAP · <StatusBadge label="수신됨" className="px-1.5 py-0" /> ]</span>
            <span className="text-xs text-muted">구역 유형 선택 후 맵 위를 드래그하세요 (✕로 삭제 · 이름 클릭 시 수정)</span>
          </div>
          {/* 열 라벨 A~N */}
          <div className="ml-6 grid font-mono text-center text-xs text-subtle" style={{ gridTemplateColumns: `repeat(${COLS}, 1fr)` }}>
            {Array.from({ length: COLS }, (_, i) => (
              <span key={i}>{colLabel(i)}</span>
            ))}
          </div>
          <div className="flex">
            {/* 행 라벨 1~7 */}
            <div className="grid w-6 font-mono text-center text-xs text-subtle" style={{ gridTemplateRows: `repeat(${ROWS}, 1fr)` }}>
              {Array.from({ length: ROWS }, (_, i) => (
                <span key={i} className="self-center">{i + 1}</span>
              ))}
            </div>
            <div
              ref={gridRef}
              role="application"
              aria-label="IoT 맵 — 드래그하여 구역 지정"
              className="relative w-full cursor-crosshair touch-none select-none overflow-hidden rounded-card-sm bg-surface ring-1 ring-line"
              style={{ aspectRatio: map ? `${map.width} / ${map.height}` : '2 / 1' }}
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
            >
              {mapImageUrl && (
                <img
                  src={mapImageUrl}
                  alt={map?.mapName ?? '완성된 지도'}
                  className="pointer-events-none absolute inset-0 h-full w-full object-fill"
                  draggable={false}
                />
              )}
              {/* 그리드 셀 */}
              <div className="absolute inset-0 grid" style={{ gridTemplateColumns: `repeat(${COLS}, 1fr)`, gridTemplateRows: `repeat(${ROWS}, 1fr)` }} aria-hidden>
                {Array.from({ length: COLS * ROWS }, (_, i) => (
                  <div key={i} className="border-b border-r border-line/60" />
                ))}
              </div>

              {/* 등록된 구역 */}
              {zones.map((z) => (
                <div
                  key={z.id}
                  className={cn('absolute flex items-start justify-between gap-1 rounded-md p-1.5 ring-2 ring-inset', zoneStyle[z.type])}
                  style={rectStyle(z.rect)}
                >
                  <button
                    type="button"
                    aria-label={`${z.label} 이름 수정`}
                    onPointerDown={(e) => e.stopPropagation()}
                    onClick={() => openEdit(z)}
                    className="truncate text-left text-xs font-bold underline-offset-2 hover:underline"
                  >
                    {z.label}
                  </button>
                  <button
                    type="button"
                    aria-label={`${z.label} 삭제`}
                    onPointerDown={(e) => e.stopPropagation()}
                    onClick={() => setZones((zs) => zs.filter((x) => x.id !== z.id))}
                    className="grid h-5 w-5 flex-none place-items-center rounded-pill bg-bg/80 text-fg hover:bg-bg"
                  >
                    <CloseIcon className="text-xs" />
                  </button>
                </div>
              ))}

              {/* 드래그 프리뷰 */}
              {drag && (
                <div
                  aria-hidden
                  className={cn('pointer-events-none absolute rounded-md ring-2 ring-inset', zoneStyle[selectedType])}
                  style={rectStyle(toRect(drag.start, drag.cur))}
                />
              )}
            </div>
          </div>
        </div>
      </div>

      {zones.length > 0 && (
        <div className="flex items-center justify-center gap-3 rounded-card-sm bg-success-soft px-6 py-4">
          <StatusBadge label="맵 등록 완료!" bracket />
          <p className="text-sm text-muted">드래그한 구역 {zones.length}곳이 저장되었습니다</p>
        </div>
      )}
      {loadError && <p role="alert" className="text-sm font-semibold text-danger">{loadError}</p>}
      {saveError && <p role="alert" className="text-sm font-semibold text-danger">{saveError}</p>}

      <div className="flex justify-between">
        <Button variant="outline" onClick={onPrev}>← 이전</Button>
        <Button
          variant="accent"
          withArrow="right"
          onClick={saveZones}
          disabled={zones.length === 0 || !map || isSaving}
        >
          가입 완료
        </Button>
      </div>

      {/* 구역 이름 입력/수정 모달 */}
      <Modal open={nameModalOpen} onClose={closeNameModal} title={editingId != null ? '구역 이름 수정' : '구역 이름 입력'}>
        <form className="flex flex-col gap-4" onSubmit={confirmName}>
          <Field label="구역 이름" htmlFor="zone-name" hint="1~20자 · 직접 입력할 수 있어요">
            <Input
              id="zone-name"
              value={nameInput}
              onChange={(e) => setNameInput(e.target.value)}
              maxLength={20}
              autoFocus
              required
            />
          </Field>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={closeNameModal}>취소</Button>
            <Button type="submit" variant="dark">{editingId != null ? '수정' : '등록'}</Button>
          </div>
        </form>
      </Modal>
    </div>
  )
}

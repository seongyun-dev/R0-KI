import { useRef, useState } from 'react'
import { CloseIcon } from '../../components/icons'
import { Button, StatusBadge, useToast } from '../../components/ui'
import { cn } from '../../lib/cn'
import type { ZoneType } from '../../types/domain'

export type StepZonesProps = {
  onPrev: () => void
  onComplete: (zoneCount: number) => void
}

const COLS = 14 // 열 A~N
const ROWS = 7 // 행 1~7
const colLabel = (i: number) => String.fromCharCode(65 + i)

const ZONE_TYPES: ZoneType[] = ['주차장', '분리수거장', '위험구역', '출입구', '기타']

const zoneStyle: Record<ZoneType, string> = {
  주차장: 'bg-info-soft/80 ring-info text-info',
  분리수거장: 'bg-success-soft/80 ring-success text-success',
  위험구역: 'bg-danger-soft/80 ring-danger text-danger',
  출입구: 'bg-warning-soft/80 ring-warning text-warning',
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

/** Step 3/3 — 구역 지정 (IoT 수신 맵 위 드래그) (1y) */
export function StepZones({ onPrev, onComplete }: StepZonesProps) {
  const toast = useToast()
  const gridRef = useRef<HTMLDivElement>(null)
  const idRef = useRef(0)
  const [selectedType, setSelectedType] = useState<ZoneType>('주차장')
  const [zones, setZones] = useState<DraftZone[]>([])
  // 드래그 상태는 ref가 진실원천(포인터 이벤트가 리렌더보다 빠를 수 있음), state는 프리뷰 렌더용
  const dragRef = useRef<{ start: { c: number; r: number }; cur: { c: number; r: number } } | null>(null)
  const [drag, setDrag] = useState<typeof dragRef.current>(null)

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
    setZones((zs) => {
      const count = zs.filter((z) => z.type === selectedType).length
      return [...zs, { id: ++idRef.current, type: selectedType, label: `${selectedType} ${count + 1}`, rect }]
    })
    toast(`✓ ${selectedType} 구역이 등록되었습니다`)
  }

  const rectStyle = (r: Rect) => ({
    left: `${(r.x / COLS) * 100}%`,
    top: `${(r.y / ROWS) * 100}%`,
    width: `${(r.w / COLS) * 100}%`,
    height: `${(r.h / ROWS) * 100}%`,
  })

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
            <span className="text-xs text-muted">구역 유형 선택 후 맵 위를 드래그하세요 (✕로 삭제)</span>
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
              className="relative aspect-[2/1] w-full cursor-crosshair touch-none select-none overflow-hidden rounded-card-sm bg-surface ring-1 ring-line"
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
            >
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
                  <span className="truncate text-xs font-bold">{z.label}</span>
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

      <div className="flex justify-between">
        <Button variant="outline" onClick={onPrev}>← 이전</Button>
        <Button variant="accent" withArrow="right" onClick={() => onComplete(zones.length)} disabled={zones.length === 0}>
          가입 완료
        </Button>
      </div>
    </div>
  )
}

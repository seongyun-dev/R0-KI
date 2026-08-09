import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import type { MapDetailResponse, ZoneCreateResponse } from '../api/contracts'
import { mapApi, patrolsApi } from '../api/services'
import { R0KiShell } from '../components/layout/R0KiShell'
import { useToast } from '../components/ui'
import { usePatrol } from '../features/patrol/usePatrols'
import { useAuthStore } from '../features/auth/useAuthStore'
import { ZoneDetail } from '../features/dashboard/ComplexMap'
import { pinPath, zoneVar } from '../features/dashboard/mapStyle'
import type { Patrol, PatrolPoint, ZoneType } from '../types/domain'

/* R0-Ki 순찰 상세 — 시안 R0Kipatrol 그대로.
   이동 경로 지도(구역 웨이포인트 동적 배치) + 순찰 지점 기록(타임라인) + AI 요약.
   한 화면 고정 — 타임라인만 내부 스크롤. 데이터는 기존 usePatrol 그대로. */

/* 순찰 상태 배지 색 — 명도 램프 (시안: 완료=offline 톤) */
const PATROL_ST: Record<string, string> = {
  완료: 'var(--offline)',
  진행중: 'var(--patrol)',
  중단: 'var(--charge)',
  실패: 'var(--alert)',
}

/* 타임라인 점·배지 색 — 명도 램프 (시안 매핑) */
const POINT_ST: Record<string, string> = {
  이상무: 'var(--patrol)',
  처리완료: 'var(--charge)',
  탐지: 'var(--detect)',
  처리중: 'var(--detect)',
}
const pointColor = (s: string) => POINT_ST[s] ?? 'var(--patrol)'

/** "09:12" → 분 (정렬용) */
function timeMin(t: string) {
  const [h = 0, m = 0] = t.split(':').map(Number)
  return h * 60 + m
}

/* ── 이동 경로 지도 ──
   스캔 맵 좌표(resolution·origin·width·height)가 오면 그 맵을 실제 비율 그대로 그리고,
   좌표가 없는 단지에서는 routeZones 를 지그재그로 늘어놓는 도식으로 대체한다.

   ⚠️ <image> 를 meet 으로 넣으면 안 된다. 스캔 맵의 실제 비율(대개 1.3:1 안팎)이
      뷰박스와 다르면 그 안에서 한 번 더 레터박스돼 좌우에 회색 띠가 남는다.
      대시보드 ComplexMap 과 같은 방식으로 — 뷰박스를 패널에 가까운 가로비로 잡고
      맵을 거기에 늘여 채운다(preserveAspectRatio="none").
      좌표 변환도 X·Y 배율을 따로 써야 늘어난 도면과 구역·경로가 어긋나지 않는다. */

const SCHEMATIC_W = 900
const SCHEMATIC_H = 480
/* 맵 영역 — 패널 가로비(약 2:1)에 맞춘 고정 비율. 대시보드 그리드 14×7 과 같은 결이다 */
const MAP_W = 900
const MAP_H = 450
const MAP_PAD = 24 // 구역명·시각 라벨이 잘리지 않을 여백

/* 구역은 대시보드 ComplexMap 과 같은 디자인을 쓴다.
   대시보드 좌표계는 셀 30px × 14칸 = 420 폭이고 .cmz CSS 크기도 거기에 맞춰져 있다.
   여기 좌표계(MAP_W)는 그보다 크므로 그 배율만큼 되돌려 그린다. */
const CMAP_CELL = 30
const CMAP_W = CMAP_CELL * 14
const ZONE_S = MAP_W / CMAP_W

/* 대시보드와 같은 유형 매핑 — 출발지(START)·위험 구역(DANGER_ZONE)은 대시보드에서도 '기타'로 떨어진다 */
const ZONE_TYPE: Record<string, ZoneType> = {
  PARKING: '주차장',
  RECYCLING_AREA: '분리수거장',
  DESTINATION: '도착지',
}
const zoneTypeOf = (code: string): ZoneType => ZONE_TYPE[code] ?? '기타'

/* 라벨 글자 크기 — r0ki.css 의 `.rmap .cmz` / `.rmap text` 와 반드시 같은 값이어야 한다.
   겹침 판정을 여기서 계산하므로 한쪽만 바꾸면 판정이 어긋난다. */
const ZONE_FS = 7 // .cmz text (불릿형 구역명)
const ZONE_FS_MID = 7.5 // .cmz text.mid (넓은 구역명)
const ZONE_FS_SUB = 6 // .cmz text.sub (통과 시각)
const EVENT_FS = 12 // .rmap .evlbl text (이벤트명)

/* 이벤트 핀 — 대시보드 .cmmark 과 같은 치수(대시보드 좌표계 기준). scale(ZONE_S) 로 얹는다 */
const PIN_R = 6.2
const PIN_H = 15
/* 이벤트 이름표 칩 안쪽 여백 */
const CHIP_PAD_X = 8
const CHIP_PAD_Y = 5
/** 베이스라인이 글자 시각 중심에서 아래로 떨어진 비율 (대문자/한글 높이의 절반) */
const BASELINE_MID = 0.35

/** 라벨 폭 추정 — 한글은 폰트 크기만큼, 라틴·숫자는 약 0.56배 */
const textWidth = (s: string, size: number) =>
  [...s].reduce((w, ch) => w + (ch.charCodeAt(0) < 128 ? size * 0.56 : size * 1.02), 0)

type LabelBox = { x1: number; y1: number; x2: number; y2: number }
const box = (x: number, y: number, w: number, h: number): LabelBox => ({
  x1: x, y1: y, x2: x + w, y2: y + h,
})
const overlaps = (a: LabelBox, b: LabelBox) =>
  a.x1 < b.x2 && a.x2 > b.x1 && a.y1 < b.y2 && a.y2 > b.y1

/* 좌표 없는 단지용 도식 — 구역을 균등 간격 지그재그로 늘어놓는다 */
function SchematicRouteSvg({
  patrol,
  zones,
  mapImageUrl,
}: {
  patrol: Patrol
  zones: string[]
  mapImageUrl?: string
}) {
  // 중간 지점 시각 — 순찰 지점 기록에서 같은 구역명을 찾아 매칭
  const timeAt = (zone: string, index: number) => {
    if (index === 0) return patrol.start
    if (index === zones.length - 1) return patrol.end ?? ''
    const hit = (patrol.points ?? []).find(
      (p) => p.location.includes(zone) || zone.includes(p.location),
    )
    return hit?.time ?? ''
  }

  const n = Math.max(zones.length, 2)
  const pts = zones.map((zone, i) => {
    const x = 110 + (i * 730) / (n - 1)
    const isEnd = i === 0 || i === n - 1
    const y = isEnd ? 340 : i % 2 === 1 ? 170 : 330
    return { zone, x, y, isEnd, time: timeAt(zone, i) }
  })
  const path = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x} ${p.y}`).join(' ')

  const routePoints = patrol.routePoints ?? []
  const xValues = routePoints.map((point) => point.x)
  const yValues = routePoints.map((point) => point.y)
  const minX = Math.min(...xValues)
  const maxX = Math.max(...xValues)
  const minY = Math.min(...yValues)
  const maxY = Math.max(...yValues)
  const routePadding = 36
  const actualPoints = routePoints.map((point) => ({
    x: minX === maxX
      ? SCHEMATIC_W / 2
      : routePadding + ((point.x - minX) / (maxX - minX)) * (SCHEMATIC_W - routePadding * 2),
    y: minY === maxY
      ? SCHEMATIC_H / 2
      : routePadding + ((maxY - point.y) / (maxY - minY)) * (SCHEMATIC_H - routePadding * 2),
  }))
  const actualPath = actualPoints
    .map((point, index) => `${index === 0 ? 'M' : 'L'}${point.x} ${point.y}`)
    .join(' ')

  return (
    <svg
      viewBox={`0 0 ${SCHEMATIC_W} ${SCHEMATIC_H}`}
      preserveAspectRatio="xMidYMid meet"
      aria-label="순찰 이동 경로"
    >
      {mapImageUrl && (
        <image
          href={mapImageUrl}
          x="0"
          y="0"
          width={SCHEMATIC_W}
          height={SCHEMATIC_H}
          preserveAspectRatio="xMidYMid meet"
        />
      )}
      <g stroke="currentColor" opacity=".09" strokeWidth="1">
        <path d="M0 60H900M0 120H900M0 180H900M0 240H900M0 300H900M0 360H900M0 420H900" />
        <path d="M75 0V480M150 0V480M225 0V480M300 0V480M375 0V480M450 0V480M525 0V480M600 0V480M675 0V480M750 0V480M825 0V480" />
      </g>
      <path
        d={path}
        fill="none" stroke="var(--graphic)" strokeWidth="3.4" strokeLinecap="round"
        strokeLinejoin="round" strokeDasharray="11 9" opacity=".75"
      />
      {actualPoints.length >= 2 && (
        <>
          <path
            d={actualPath}
            fill="none"
            stroke="var(--graphic)"
            strokeWidth="5"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeDasharray="10 8"
          />
          <circle cx={actualPoints[0].x} cy={actualPoints[0].y} r="8" fill="var(--patrol)" />
          <circle
            cx={actualPoints[actualPoints.length - 1].x}
            cy={actualPoints[actualPoints.length - 1].y}
            r="8"
            fill="var(--detect)"
          />
        </>
      )}
      {pts.map((p, i) => {
        const below = p.y >= 300
        const labelY = below ? p.y + 42 : p.y - 34
        const timeY = below ? p.y + 62 : p.y - 54
        return (
          <g key={`${p.zone}-${i}`}>
            {p.isEnd ? (
              <>
                <circle cx={p.x} cy={p.y} r="13" fill="var(--graphic)" />
                <circle cx={p.x} cy={p.y} r="13" fill="none" stroke="#fff" strokeOpacity=".9" strokeWidth="3" />
              </>
            ) : (
              <>
                <circle cx={p.x} cy={p.y} r="11" fill="none" stroke="var(--graphic)" strokeWidth="3.4" />
                <circle cx={p.x} cy={p.y} r="4" fill="var(--graphic)" />
              </>
            )}
            <text x={p.x} y={labelY}>{p.zone}</text>
            {p.time && <text className="rt" x={p.x} y={timeY}>{p.time}</text>}
          </g>
        )
      })}
    </svg>
  )
}

function RouteMapSvg({
  patrol,
  mapImageUrl,
  mapDetail,
  checkpointZones,
}: {
  patrol: Patrol
  mapImageUrl?: string
  mapDetail?: MapDetailResponse
  checkpointZones: ZoneCreateResponse[]
}) {
  const zones = patrol.routeZones.filter((z) => z !== '경로 정보 없음')
  const eventPoints = (patrol.points ?? []).filter(
    (point) =>
      point.eventId != null &&
      point.x != null && Number.isFinite(point.x) &&
      point.y != null && Number.isFinite(point.y),
  )

  if (
    zones.length < 2 &&
    (patrol.routePoints?.length ?? 0) < 2 &&
    checkpointZones.length === 0 &&
    eventPoints.length === 0
  ) {
    return (
      <svg
        viewBox={`0 0 ${SCHEMATIC_W} ${SCHEMATIC_H}`}
        preserveAspectRatio="xMidYMid meet"
        aria-label="순찰 이동 경로"
      >
        {mapImageUrl && (
          <image
            href={mapImageUrl}
            x="0"
            y="0"
            width={SCHEMATIC_W}
            height={SCHEMATIC_H}
            preserveAspectRatio="xMidYMid meet"
          />
        )}
        <text x={SCHEMATIC_W / 2} y={SCHEMATIC_H / 2}>경로 정보 없음</text>
      </svg>
    )
  }

  const resolution = Number(mapDetail?.resolution)
  const originX = Number(mapDetail?.originX)
  const originY = Number(mapDetail?.originY)
  const mapWidth = Number(mapDetail?.width)
  const mapHeight = Number(mapDetail?.height)
  const hasMapCoordinates =
    Number.isFinite(resolution) && resolution > 0 &&
    Number.isFinite(originX) && Number.isFinite(originY) &&
    Number.isFinite(mapWidth) && mapWidth > 0 &&
    Number.isFinite(mapHeight) && mapHeight > 0

  if (!hasMapCoordinates) {
    return <SchematicRouteSvg patrol={patrol} zones={zones} mapImageUrl={mapImageUrl} />
  }

  /* 맵을 MAP_W×MAP_H 에 늘여 채운다. X·Y 배율이 달라지므로 좌표 변환도 따로 건다 */
  const viewW = MAP_W + MAP_PAD * 2
  const viewH = MAP_H + MAP_PAD * 2
  const scaleX = MAP_W / mapWidth
  const scaleY = MAP_H / mapHeight

  const toScreenPoint = (x: number, y: number) => ({
    x: MAP_PAD + ((x - originX) / resolution) * scaleX,
    y: MAP_PAD + (mapHeight - (y - originY) / resolution) * scaleY,
  })

  /* 구역 통과 시각 — 도식 웨이포인트에 붙어 있던 표기를 실제 구역으로 옮겼다.
     첫/마지막 구역은 순찰 시작·종료 시각, 중간은 순찰 지점 기록에서 구역명으로 찾는다. */
  const zoneTime = (name: string) => {
    const index = zones.findIndex((z) => z === name || z.includes(name) || name.includes(z))
    if (index === 0) return patrol.start
    if (index >= 0 && index === zones.length - 1) return patrol.end ?? ''
    const hit = (patrol.points ?? []).find(
      (p) => p.location.includes(name) || name.includes(p.location),
    )
    return hit?.time ?? ''
  }

  const actualPoints = (patrol.routePoints ?? []).map((point) => toScreenPoint(point.x, point.y))
  const actualPath = actualPoints
    .map((point, index) => `${index === 0 ? 'M' : 'L'}${point.x} ${point.y}`)
    .join(' ')

  const gridCols = 12
  const gridRows = 6

  /* ── 라벨 자리 잡기 ──
     이벤트는 구역 안에서 탐지되므로 구역명과 이벤트명은 그냥 두면 서로 겹친다.
     구역명을 먼저 놓고, 이벤트명은 그 자리를 피해 위/아래로 밀어낸다.
     구역 라벨은 scale(ZONE_S) 안에서 그려지므로 판정 좌표에 배율을 곱해 맞춘다. */
  const placed: LabelBox[] = []

  const zoneItems = checkpointZones.map((zone) => {
    const topLeft = toScreenPoint(Number(zone.minX), Number(zone.maxY))
    const bottomRight = toScreenPoint(Number(zone.maxX), Number(zone.minY))
    const type = zoneTypeOf(zone.type)
    const x = topLeft.x / ZONE_S
    const y = topLeft.y / ZONE_S
    const w = Math.max(4, bottomRight.x - topLeft.x) / ZONE_S
    const h = Math.max(4, bottomRight.y - topLeft.y) / ZONE_S
    const time = zoneTime(zone.name)
    // 대시보드와 같은 판정 — 셀(30px) 넓이 6칸 이상이면 상자 안 가운데, 아니면 불릿 + 옆
    const big = (w / CMAP_CELL) * (h / CMAP_CELL) >= 6
    const nameY = big ? (type === '기타' ? y + h / 2 + 3.4 : y + 15) : y + 14.5
    const fs = big ? ZONE_FS_MID : ZONE_FS
    const nameW = textWidth(zone.name, fs)
    const nameX = big ? x + w / 2 - nameW / 2 : x + 16
    placed.push(box(nameX * ZONE_S, (nameY - fs) * ZONE_S, nameW * ZONE_S, (fs + 3) * ZONE_S))
    const timeY = nameY + 9
    if (time) {
      const timeW = textWidth(time, ZONE_FS_SUB)
      const timeX = big ? x + w / 2 - timeW / 2 : x + 16
      placed.push(
        box(timeX * ZONE_S, (timeY - ZONE_FS_SUB) * ZONE_S, timeW * ZONE_S, (ZONE_FS_SUB + 3) * ZONE_S),
      )
    }
    return { zone, type, x, y, w, h, time, big, nameY, timeY }
  })

  /* 이벤트 — 물방울 핀(대시보드 .cmmark 과 같은 마커). 팁이 발생 좌표에 꽂힌다.
     핀 몸통도 자리로 잡아 둬야 라벨이 다른 핀 위에 얹히지 않는다. */
  const pinR = PIN_R * ZONE_S
  const pinH = PIN_H * ZONE_S
  const eventMarks = eventPoints.map((point) => ({
    point,
    position: toScreenPoint(point.x!, point.y!),
    urgent: point.type === '응급상황',
  }))
  eventMarks.forEach(({ position }) => {
    placed.push(box(position.x - pinR, position.y - pinH - pinR, pinR * 2, pinH + pinR))
  })

  /* 이름표는 칩(둥근 카드)으로 띄운다 — 구역명은 도면 위 평서 글씨라 구조부터 달라진다.
     핀 머리 위가 기본, 겹치면 아래·더 위·더 아래 순으로 비켜난다 */
  const eventDy = [-(pinH + pinR + 10), 34, -(pinH + pinR + 32), 56, -(pinH + pinR + 54), 78]
  const eventItems = eventMarks.map((mark) => {
    const { position } = mark
    const chipW = textWidth(mark.point.type, EVENT_FS) + CHIP_PAD_X * 2
    const chipH = EVENT_FS + CHIP_PAD_Y * 2
    /* 글자를 칩 정중앙에 놓는다 — 베이스라인은 글자 시각 중심보다 약 0.35em 아래라
       그만큼 올려 잡아야 아래로 쏠려 보이지 않는다 */
    const chipTop = (dy: number) => dy - EVENT_FS * BASELINE_MID - chipH / 2
    const at = (dy: number) => box(position.x - chipW / 2, position.y + chipTop(dy), chipW, chipH)
    const dy = eventDy.find((candidate) => !placed.some((p) => overlaps(p, at(candidate)))) ?? eventDy[0]
    placed.push(at(dy))
    return { ...mark, dy, chipW, chipH, chipTop: chipTop(dy) }
  })

  return (
    <svg
      viewBox={`0 0 ${viewW} ${viewH}`}
      preserveAspectRatio="xMidYMid meet"
      aria-label="순찰 이동 경로"
    >
      {mapImageUrl && (
        <image
          className="mapbase"
          href={mapImageUrl}
          x={MAP_PAD}
          y={MAP_PAD}
          width={MAP_W}
          height={MAP_H}
          preserveAspectRatio="none"
        />
      )}
      <g stroke="currentColor" opacity=".09" strokeWidth="1">
        {Array.from({ length: gridRows + 1 }, (_, i) => (
          <line
            key={`h${i}`}
            x1={MAP_PAD}
            y1={MAP_PAD + (MAP_H * i) / gridRows}
            x2={MAP_PAD + MAP_W}
            y2={MAP_PAD + (MAP_H * i) / gridRows}
          />
        ))}
        {Array.from({ length: gridCols + 1 }, (_, i) => (
          <line
            key={`v${i}`}
            x1={MAP_PAD + (MAP_W * i) / gridCols}
            y1={MAP_PAD}
            x2={MAP_PAD + (MAP_W * i) / gridCols}
            y2={MAP_PAD + MAP_H}
          />
        ))}
      </g>
      {/* 구역 — 대시보드 ComplexMap 과 같은 디자인(.cmz + ZoneDetail).
          .cmz CSS 는 대시보드 좌표계(셀 30px) 기준 크기라, 여기 좌표를 배율로
          나눠 그린 뒤 그룹을 scale(ZONE_S) 해서 같은 비율로 보이게 한다. */}
      {zoneItems.map(({ zone, type, x, y, w, h, time, big, nameY, timeY }) => (
        <g key={String(zone.zoneId)} className="cmz" style={zoneVar(type)} transform={`scale(${ZONE_S})`}>
          <rect x={x + 2} y={y + 2} width={w - 4} height={h - 4} rx="7" />
          <ZoneDetail type={type} x={x + 2} y={y + 2} w={w - 4} h={h - 4} />
          {big ? (
            <>
              <text className="mid" x={x + w / 2} y={nameY} textAnchor="middle">{zone.name}</text>
              {time && (
                <text className="sub" x={x + w / 2} y={timeY} textAnchor="middle">{time}</text>
              )}
            </>
          ) : (
            <>
              <rect
                className="bul"
                x={x + 8}
                y={y + 9}
                width="4"
                height="4"
                transform={`rotate(45 ${x + 10} ${y + 11})`}
              />
              <text className="lft" x={x + 16} y={nameY}>{zone.name}</text>
              {time && <text className="sub lft" x={x + 16} y={timeY}>{time}</text>}
            </>
          )}
        </g>
      ))}
      {actualPoints.length >= 2 && (
        <>
          <path className="rroute" d={actualPath} />
          <circle className="rrend start" cx={actualPoints[0].x} cy={actualPoints[0].y} r="8" />
          <circle
            className="rrend"
            cx={actualPoints[actualPoints.length - 1].x}
            cy={actualPoints[actualPoints.length - 1].y}
            r="8"
          />
        </>
      )}
      {eventItems.map(({ point, position, dy, urgent, chipW, chipH, chipTop }) => (
        <g key={`event-${point.eventId}`}>
          <g
            className={urgent ? 'cmmark urg' : 'cmmark'}
            transform={`translate(${position.x},${position.y}) scale(${ZONE_S})`}
          >
            <path d={pinPath(PIN_R, PIN_H)} />
            <circle className="core" cy={-PIN_H} r="2.4" />
          </g>
          <g className={urgent ? 'evlbl urg' : 'evlbl'}>
            <rect
              x={position.x - chipW / 2}
              y={position.y + chipTop}
              width={chipW}
              height={chipH}
              rx={chipH / 2}
            />
            <text x={position.x} y={position.y + dy}>{point.type}</text>
          </g>
          <title>{`${point.time} · ${point.type} · ${point.location}`}</title>
        </g>
      ))}
    </svg>
  )
}

/* ── 타임라인 행 ── */
function TimelineRow({ point, onGo }: { point: PatrolPoint; onGo?: () => void }) {
  const color = pointColor(point.status)
  const content = (
    <>
      <span className="d" style={{ background: color }} />
      <span className="t">{point.time}</span>
      <span className="c">
        <span className="n">
          {point.type}
          <em>{point.location}</em>
        </span>
        {point.note && <span className="m">{point.note}</span>}
      </span>
      <span className="a">
        <span className="st"><i style={{ background: color }} />{point.status}</span>
      </span>
    </>
  )

  // 화살표 대신 이벤트가 있는 기록 행 전체를 클릭 영역으로 제공한다.
  return onGo ? (
    <button type="button" className="tl tl-clickable" onClick={onGo} aria-label={`${point.type} 이벤트 상세로`}>
      {content}
    </button>
  ) : (
    <div className="tl">{content}</div>
  )
}

export default function PatrolDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const { data: patrol, isLoading, error, refetch } = usePatrol(id)
  const mapId = useAuthStore((state) => state.mapId)
  const [mapImageUrl, setMapImageUrl] = useState<string>()
  const [mapDetail, setMapDetail] = useState<MapDetailResponse>()
  const [checkpointZones, setCheckpointZones] = useState<ZoneCreateResponse[]>([])
  const [isDownloadingPdf, setIsDownloadingPdf] = useState(false)

  const handlePdfDownload = async () => {
    if (!id || isDownloadingPdf) return

    setIsDownloadingPdf(true)
    try {
      const pdf = await patrolsApi.downloadPdf(id)
      const objectUrl = URL.createObjectURL(pdf)
      const link = document.createElement('a')
      link.href = objectUrl
      link.download = `patrol-report-${id}.pdf`
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(objectUrl)
      toast('PDF 보고서를 다운로드했습니다.')
    } catch (reason) {
      console.error('PDF 보고서 다운로드에 실패했습니다.', reason)
      toast('PDF 보고서 다운로드에 실패했습니다.')
    } finally {
      setIsDownloadingPdf(false)
    }
  }

  useEffect(() => {
    if (!mapId && !patrol?.mapUrl) {
      setMapImageUrl(undefined)
      setMapDetail(undefined)
      setCheckpointZones([])
      return
    }

    const controller = new AbortController()
    let objectUrl: string | undefined

    const detailPromise = mapId
      ? Promise.all([mapApi.detail(mapId), mapApi.zones(mapId)])
          .then(([detail, zones]) => {
            setCheckpointZones(zones)
            return detail
          })
      : Promise.resolve(undefined)

    detailPromise
      .then(async (detail) => {
        setMapDetail(detail)
        const mapUrl = detail?.mapUrl ?? patrol?.mapUrl
        if (!mapUrl) return undefined
        return mapApi.file(mapUrl, controller.signal)
      })
      .then((blob) => {
        if (!blob) return
        objectUrl = URL.createObjectURL(blob)
        setMapImageUrl(objectUrl)
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          console.error('순찰 지도를 불러오지 못했습니다.', reason)
        }
      })

    return () => {
      controller.abort()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [mapId, patrol?.mapUrl])

  // 시안은 최신순 (복귀가 맨 위)
  const points = [...(patrol?.points ?? [])].sort((a, b) => timeMin(b.time) - timeMin(a.time))
  const anomalies = points.filter((p) => p.eventId).length

  return (
    <R0KiShell active="patrol">
      <div className="pcol">
        <div className="pagehead">
          <div>
            <div className="crumb">
              <Link to="/app">대시보드</Link><i>›</i>
              <Link to="/app/patrol">순찰 관리</Link><i>›</i>
              <b>{patrol?.id ?? id}</b>
            </div>
            <div className="ptitle">
              순찰 상세
              {patrol && (
                <>
                  <span className="sub">{patrol.id} · {patrol.robotName ?? patrol.robotId}</span>
                  <span className="st" style={{ marginLeft: 12, verticalAlign: 4 }}>
                    <i style={{ background: PATROL_ST[patrol.status] ?? 'var(--patrol)' }} />
                    {patrol.status}
                  </span>
                </>
              )}
            </div>
          </div>
          <div className="headtools">
            <Link to="/app/patrol" className="btn btn-s">
              순찰 목록
            </Link>
            <button type="button" className="btn btn-s" onClick={() => toast('✓ 재순찰이 요청되었습니다')}>
              재순찰 요청
            </button>
            <button
              type="button"
              className="btn btn-p"
              disabled={!patrol || isDownloadingPdf}
              onClick={handlePdfDownload}
            >
              {isDownloadingPdf ? 'PDF 생성 중...' : 'PDF 다운로드'}
            </button>
          </div>
        </div>

        {error ? (
          <div className="glass g2 aisum">
            <div className="zh2"><span className="zn">순찰 이력을 불러오지 못했습니다</span></div>
            <button type="button" className="btn btn-s" onClick={refetch}>다시 시도</button>
          </div>
        ) : !patrol ? (
          <div className="glass g2 aisum">
            <div className="zh2">
              <span className="zn">{isLoading ? '불러오는 중…' : `순찰 이력(${id})을 찾을 수 없습니다`}</span>
            </div>
            {!isLoading && (
              <Link to="/app/patrol" className="btn btn-s">목록으로</Link>
            )}
          </div>
        ) : (
          <>
            <div className="dgrid">
              {/* 이동 경로 지도 */}
              <div className="glass g2 dcol" style={{ padding: 'var(--s5)' }}>
                <div className="zh2">
                  <span className="zn">이동 경로 지도</span>
                  <span className="zsub">{patrol.routeSummary ?? patrol.routeZones.join(' → ')}</span>
                </div>
                <div className="rmap">
                  <RouteMapSvg
                    patrol={patrol}
                    mapImageUrl={mapImageUrl}
                    mapDetail={mapDetail}
                    checkpointZones={checkpointZones}
                  />
                </div>
              </div>

              {/* 순찰 지점 기록 */}
              <div className="glass g2 dcol" style={{ padding: 'var(--s5)' }}>
                <div className="zh2">
                  <span className="zn">순찰 지점 기록</span>
                  <span className="zsub">
                    최신순 · 전체 경유지 {points.length}곳{anomalies > 0 ? ` · 이상 ${anomalies}건` : ''}
                  </span>
                </div>
                <div className="tline">
                  {points.length === 0 ? (
                    <div className="tfoot" style={{ paddingTop: 'var(--s5)' }}>
                      <span>기록된 타임라인이 없습니다</span>
                    </div>
                  ) : (
                    points.map((point, i) => (
                      <TimelineRow
                        key={`${point.time}-${i}`}
                        point={point}
                        onGo={point.eventId ? () => navigate(`/app/events/${point.eventId}`) : undefined}
                      />
                    ))
                  )}
                </div>
              </div>
            </div>

            {/* AI 요약 */}
            <div className="glass g2 aisum">
              <div className="zh2"><span className="zn">AI 요약</span></div>
              <p className="q">
                {patrol.report?.aiSummary ?? '보고서가 아직 생성되지 않았습니다. 순찰이 완료되면 AI 보고서가 자동 생성됩니다.'}
              </p>
            </div>
          </>
        )}
      </div>
    </R0KiShell>
  )
}

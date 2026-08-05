import { useRef, useState } from 'react'
import type { CSSProperties, PointerEvent as ReactPointerEvent, ReactNode } from 'react'
import { useClockText } from '../../components/layout/R0KiShell'
import { cn } from '../../lib/cn'
import type { ComplexMapData, MapCheckpoint, MapPin, MapRobot, Tone, Zone, ZoneType } from '../../types/domain'

/* 단지 실시간 지도 (1c) — 백엔드(IoT 스캔 맵) 데이터를 받아 그리는 순수 렌더러.
   좌표는 온보딩(1y)과 같은 그리드 단위(cols×rows)로 들어오고,
   여기서 SVG viewBox 좌표로 변환만 한다.

   R0-Ki 톤 — 색은 하드코딩하지 않고 전부 r0ki 토큰을 쓴다.
   · 구역: 상태 명도 램프(--patrol/--charge/--alert/--detect/--offline).
     온보딩 구역 편집기(.au-zone)와 같은 반투명 레시피(채움 13% · 테두리 62%)라
     등록 화면에서 그린 구역이 대시보드에서 같은 색으로 이어진다.
   · 위험구역은 색에만 기대지 않고 해칭을 겹친다(색맹 대응 · 이중 표기).
   · 구조물(격자·외곽): currentColor + 낮은 불투명도.
   · 로봇/경로: --graphic. 긴급 핀만 --urgent (모노크롬 규칙의 유일한 예외).

   관제 지도 문법 —
   · 순찰 경로는 체크포인트를 직교(맨해튼) 동선으로 잇고 꺾임을 둥글게 만다.
     로봇 위치를 경로에 사영해 완료 구간(굵은 실선)과 예정 구간(점선)을 가른다.
   · 체크포인트: 통과(채운 점) / 대기(빈 점). 부가 설명(note)이 있으면
     물방울 마커 + 콜아웃 카드로 띄운다. 없는 데이터는 지어내지 않는다.
   · 오버레이(줌·실시간 시각·범례·화면별 조작키)는 SVG 밖 HTML — 지도를 확대해도 크기가 고정된다. */

const CELL = 30 // 그리드 1칸 → SVG 30px
const SUB = 2 // 셀당 잔격자 분할 수 — 격자를 잘게 보이게 한다(좌표계는 셀 기준 그대로)
const PAD = { l: 11, t: 11, r: 11, b: 11 } // 외곽 라벨·마커가 잘리지 않을 만큼의 여백
const ZOOM_MAX = 3
const CORNER = 9 // 순찰 경로 꺾임 반경

/** 이벤트 핀 색 — 긴급만 --urgent, 나머지는 명도 램프 */
const toneVar: Record<Tone, string> = {
  danger: 'var(--urgent)',
  warning: 'var(--alert)',
  info: 'var(--patrol)',
  success: 'var(--charge)',
  neutral: 'var(--offline)',
}

/** 구역 색 — 온보딩 StepZones 와 동일 매핑 */
const zoneTone: Record<ZoneType, string> = {
  주차장: 'patrol',
  분리수거장: 'charge',
  출입구: 'detect',
  도착지: 'offline',
  기타: 'offline',
}
const zoneVar = (type: ZoneType) => ({ '--z': `var(--${zoneTone[type]})` }) as CSSProperties

type Pt = { x: number; y: number }

const dist = (a: Pt, b: Pt) => Math.hypot(b.x - a.x, b.y - a.y)

/** 꺾이는 지점을 둥글게 이은 경로 — 관제 지도의 순찰 동선 문법 */
function roundedPath(pts: Pt[], r: number) {
  if (pts.length < 2) return ''
  let d = `M${pts[0].x} ${pts[0].y}`
  for (let i = 1; i < pts.length - 1; i++) {
    const p = pts[i]
    const a = pts[i - 1]
    const b = pts[i + 1]
    const da = dist(a, p)
    const db = dist(p, b)
    if (da < 0.01 || db < 0.01) continue
    const cut = Math.min(r, da / 2, db / 2)
    const s = { x: p.x + ((a.x - p.x) / da) * cut, y: p.y + ((a.y - p.y) / da) * cut }
    const e = { x: p.x + ((b.x - p.x) / db) * cut, y: p.y + ((b.y - p.y) / db) * cut }
    d += ` L${s.x.toFixed(2)} ${s.y.toFixed(2)} Q${p.x} ${p.y} ${e.x.toFixed(2)} ${e.y.toFixed(2)}`
  }
  const last = pts[pts.length - 1]
  return `${d} L${last.x} ${last.y}`
}

/** 지도 마커(물방울) — 팁이 원점, 위로 부풀어 오르는 풍선. 접선점을 계산해 꼬리를 잇는다 */
function pinPath(r: number, h: number) {
  const len = Math.sqrt(h * h - r * r)
  const a = Math.asin(r / h)
  const tx = len * Math.sin(a)
  const ty = -len * Math.cos(a)
  return `M0 0 L${tx.toFixed(2)} ${ty.toFixed(2)} A${r} ${r} 0 1 0 ${(-tx).toFixed(2)} ${ty.toFixed(2)} Z`
}

/** 라벨 폭 추정 — 한글은 폰트 크기만큼, 라틴·숫자는 약 0.56배. 카드 크기 계산용 */
const textW = (s: string, size: number) =>
  [...s].reduce((w, ch) => w + (ch.charCodeAt(0) < 128 ? size * 0.56 : size * 1.02), 0)

const CARD_T = 7.2
const CARD_S = 6.2

/** 콜아웃 카드 — 마커 옆에 붙는 제목 + 부가 설명. 지도 밖으로 나가면 반대편으로 접는다 */
function Callout({
  x,
  y,
  title,
  sub,
  below,
  urgent,
  W,
  H,
}: {
  x: number
  y: number
  title: string
  sub?: string
  below?: boolean
  urgent?: boolean
  W: number
  H: number
}) {
  const w = Math.max(textW(title, CARD_T), sub ? textW(sub, CARD_S) : 0) + 13
  const h = sub ? 21 : 14
  let gx = x + 9
  if (gx + w > W - 2) gx = x - 9 - w
  gx = Math.max(2, Math.min(gx, W - w - 2))
  const gy = Math.max(2, Math.min(below ? y + 9 : y - 23, H - h - 2))
  return (
    <g className={cn('cmcard', urgent && 'urg')} aria-hidden>
      <rect x={gx} y={gy} width={w} height={h} rx="5.5" />
      <text className="t" x={gx + 6.5} y={gy + 9}>
        {title}
      </text>
      {sub && (
        <text className="s" x={gx + 6.5} y={gy + 17.2}>
          {sub}
        </text>
      )}
    </g>
  )
}

/** 구역 내부 설비 묘사 — 유형에서 유도되는 것만 그린다(없는 데이터를 지어내지 않는다).
    구역이 작으면 생략해 뭉개짐을 피한다. */
function ZoneDetail({ type, x, y, w, h }: { type: ZoneType; x: number; y: number; w: number; h: number }) {
  const inset = 7
  const ix = x + inset
  const iy = y + inset
  const iw = w - inset * 2
  const ih = h - inset * 2
  if (iw < 24 || ih < 20) return null

  if (type === '주차장') {
    // 주차면 — 가로 구획선 + 중앙 통로. 칸 수는 구역 크기에서 계산
    const lanes = Math.max(2, Math.min(5, Math.floor(ih / 14)))
    const gap = ih / lanes
    const midX = ix + iw / 2
    return (
      <g className="cmfx">
        {Array.from({ length: lanes + 1 }, (_, i) => (
          <line key={i} x1={ix} y1={iy + gap * i} x2={ix + iw} y2={iy + gap * i} />
        ))}
        <line x1={midX} y1={iy} x2={midX} y2={iy + ih} />
        {/* 주차된 차량 몇 대 — 채워진 면 */}
        {Array.from({ length: Math.min(3, lanes) }, (_, i) => (
          <rect
            key={`c${i}`}
            className="fill"
            x={i % 2 ? midX + 3 : ix + 3}
            y={iy + gap * i + gap * 0.22}
            width={iw / 2 - 6}
            height={gap * 0.56}
            rx="1.6"
          />
        ))}
      </g>
    )
  }

  if (type === '분리수거장') {
    // 수거함 — 균등 배치
    const bins = Math.max(2, Math.min(4, Math.floor(iw / 12)))
    const bw = (iw - (bins - 1) * 3) / bins
    const bh = Math.min(ih - 2, 16)
    return (
      <g className="cmfx">
        {Array.from({ length: bins }, (_, i) => (
          <rect key={i} className="fill" x={ix + i * (bw + 3)} y={iy + ih - bh} width={bw} height={bh} rx="2.4" />
        ))}
      </g>
    )
  }

  if (type === '도착지') {
    // 복귀 지점 — 깃대
    const fx = ix + iw / 2
    const fy = iy + ih / 2
    return (
      <g className="cmfx">
        <line x1={fx} y1={fy - 8} x2={fx} y2={fy + 8} />
        <path className="fill" d={`M${fx} ${fy - 8} L${fx + 10} ${fy - 4.5} L${fx} ${fy - 1} Z`} />
      </g>
    )
  }

  if (type === '기타') {
    // 동 건물 — 안쪽 윤곽선 한 겹 (도면 블록처럼 읽히게)
    return (
      <g className="cmfx">
        <rect x={x + 4} y={y + 4} width={w - 8} height={h - 8} rx="5" />
      </g>
    )
  }

  return null
}

type Gate = { zone: Zone; edge: 'l' | 'r' | 't' | 'b'; gx: number; gy: number }

export type ComplexMapProps = {
  map: ComplexMapData
  robot?: MapRobot
  /** 여러 대를 한 번에 볼 때(순찰 중 로봇 전체 보기). 있으면 robot 대신 이 목록을 그린다 */
  robots?: MapRobot[]
  pins?: MapPin[]
  /** 순찰 체크포인트 — 배열 순서가 곧 순찰 경로 */
  checkpoints?: MapCheckpoint[]
  /** 로봇이 순찰 중인가. false 면 완료 구간 없이 예정 경로와 마지막 위치만 찍는다 */
  patrolling?: boolean
  /** 지도 우측 하단에 얹을 화면별 조작키 */
  bottomRight?: ReactNode
  className?: string
}

export function ComplexMap({
  map,
  robot,
  robots,
  pins = [],
  checkpoints = [],
  patrolling = true,
  bottomRight,
  className,
}: ComplexMapProps) {
  const clock = useClockText()
  const W = map.cols * CELL
  const H = map.rows * CELL
  const VW = W + PAD.l + PAD.r
  const VH = H + PAD.t + PAD.b
  const px = (gx: number) => gx * CELL
  const py = (gy: number) => gy * CELL

  /* ── 확대·이동 ──
     content 좌표 (cx,cy) 가 화면 중앙에 오도록 배율 k 로 확대한다.
     k=1 이면 항등 변환이라 기본 화면은 지금까지와 같다. */
  const [view, setView] = useState({ k: 1, cx: VW / 2, cy: VH / 2 })
  const [panning, setPanning] = useState(false)
  const svgRef = useRef<SVGSVGElement>(null)
  const drag = useRef<{ id: number; x: number; y: number } | null>(null)

  // 확대해도 지도 밖 여백이 보이지 않도록 중심을 가둔다
  const clampView = (k: number, cx: number, cy: number) => {
    const hw = VW / (2 * k)
    const hh = VH / (2 * k)
    return { k, cx: Math.min(Math.max(cx, hw), VW - hw), cy: Math.min(Math.max(cy, hh), VH - hh) }
  }
  const zoomBy = (mul: number) =>
    setView((v) => clampView(Math.min(ZOOM_MAX, Math.max(1, v.k * mul)), v.cx, v.cy))
  const resetView = () => setView({ k: 1, cx: VW / 2, cy: VH / 2 })

  // client px → content 단위 (svg 는 xMidYMid meet 이라 짧은 축 기준으로 맞춰진다)
  const unitScale = () => {
    const r = svgRef.current?.getBoundingClientRect()
    if (!r || !r.width || !r.height) return 1
    return Math.min(r.width / VW, r.height / VH)
  }
  const onPointerDown = (e: ReactPointerEvent<SVGSVGElement>) => {
    if (view.k <= 1) return
    drag.current = { id: e.pointerId, x: e.clientX, y: e.clientY }
    setPanning(true)
    e.currentTarget.setPointerCapture(e.pointerId)
  }
  const onPointerMove = (e: ReactPointerEvent<SVGSVGElement>) => {
    const d = drag.current
    if (!d || d.id !== e.pointerId) return
    const s = unitScale()
    const dx = (e.clientX - d.x) / (s * view.k)
    const dy = (e.clientY - d.y) / (s * view.k)
    drag.current = { id: e.pointerId, x: e.clientX, y: e.clientY }
    setView((v) => clampView(v.k, v.cx - dx, v.cy - dy))
  }
  const endPan = (e: ReactPointerEvent<SVGSVGElement>) => {
    if (!drag.current) return
    drag.current = null
    setPanning(false)
    if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId)
  }

  /* ── 출입구 게이트 — 단지 경계에 붙은 구역은 구역 상자 대신 경계 바로 그린다 ── */
  const gates: Gate[] = []
  map.zones.forEach((z) => {
    if (z.type !== '출입구' || !z.rect) return
    const { x, y, w, h } = z.rect
    const near = (
      [
        { edge: 'l', gap: x },
        { edge: 'r', gap: map.cols - (x + w) },
        { edge: 't', gap: y },
        { edge: 'b', gap: map.rows - (y + h) },
      ] as { edge: Gate['edge']; gap: number }[]
    ).sort((a, b) => a.gap - b.gap)[0]
    if (near.gap > 1.2) return // 경계에서 멀면 게이트로 보지 않는다
    gates.push({
      zone: z,
      edge: near.edge,
      gx: near.edge === 'l' ? 1 : near.edge === 'r' ? W - 1 : px(x + w / 2),
      gy: near.edge === 't' ? 1 : near.edge === 'b' ? H - 1 : py(y + h / 2),
    })
  })
  const gateIds = new Set(gates.map((g) => g.zone.id))

  /* 지도에 그릴 로봇 — 여러 대(robots)가 오면 그쪽이 우선 */
  const shownRobots = robots && robots.length > 0 ? robots : robot ? [robot] : []
  /* 진행률·스캔 콘은 한 대만 볼 때 계산한다 (여러 대는 누구 기준인지 정해지지 않는다) */
  const soloRobot = shownRobots.length === 1 ? shownRobots[0] : undefined
  /* 저장된 웨이포인트 순서가 예정 경로다. 위치 이력(routePoints)은 실제 이동
     기록이므로 아직 지나지 않은 구간을 표현할 수 없어 계획 경로로 사용하지 않는다. */
  const routePts: Pt[] = checkpoints.map((checkpoint) => ({
    x: px(checkpoint.x),
    y: py(checkpoint.y),
  }))
  const cpIdx = checkpoints.map((checkpoint) => {
    let nearest = -1
    let nearestDistance = Infinity
    routePts.forEach((point, index) => {
      const distance = (point.x - px(checkpoint.x)) ** 2 + (point.y - py(checkpoint.y)) ** 2
      if (distance < nearestDistance) {
        nearest = index
        nearestDistance = distance
      }
    })
    return nearest
  })

  /* 예정 경로는 대기 상태에도 표시하고, 완료 구간만 순찰 중에 계산한다. */
  const showRoute = routePts.length > 1

  /* 진행률 — 로봇 위치를 경로에 사영해 완료 구간과 예정 구간을 가른다 */
  let prog: { seg: number; p: Pt } | null = null
  if (patrolling && showRoute && soloRobot) {
    const r = { x: px(soloRobot.x), y: py(soloRobot.y) }
    let bestD = Infinity
    for (let i = 0; i < routePts.length - 1; i++) {
      const a = routePts[i]
      const b = routePts[i + 1]
      const dx = b.x - a.x
      const dy = b.y - a.y
      const t = Math.max(0, Math.min(1, ((r.x - a.x) * dx + (r.y - a.y) * dy) / (dx * dx + dy * dy || 1)))
      const p = { x: a.x + dx * t, y: a.y + dy * t }
      const d = (r.x - p.x) ** 2 + (r.y - p.y) ** 2
      if (d < bestD) {
        bestD = d
        prog = { seg: i, p }
      }
    }
  }
  const donePts = prog ? [...routePts.slice(0, prog.seg + 1), prog.p] : []
  const visited = (i: number) => (prog ? cpIdx[i] <= prog.seg : false)
  // 스캔 콘이 진행 방향을 향하도록 — 현재 구간의 방향각
  const routeHeading = prog
    ? (Math.atan2(routePts[prog.seg + 1].y - routePts[prog.seg].y, routePts[prog.seg + 1].x - routePts[prog.seg].x) *
        180) /
      Math.PI
    : 0
  const cpLabel = (c: MapCheckpoint, i: number) => (c.label ? `${i + 1}번 · ${c.label}` : `${i + 1}번`)
  const hasUrgentPin = pins.some((p) => p.tone === 'danger')
  const scaleLen = px(2) * view.k
  /* 우측 하단에 조작키를 얹으면 축척을 그만큼 왼쪽으로 비켜 그린다.
     조작키도 지도 폭에 비례(cqw)해 커지므로 viewBox 기준 고정값으로 맞아떨어진다 */
  const scaleShift = bottomRight ? 118 : 0

  return (
    <div className={cn('cmwrap', view.k > 1 && 'zoomed', panning && 'pan', className)}>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${VW} ${VH}`}
        role="img"
        aria-label={`단지 실시간 지도 — 구역 ${map.zones.length}곳${
          shownRobots.length === 1
            ? `, 로봇 ${shownRobots[0].name ?? shownRobots[0].id} ${patrolling ? '순찰 중' : '정지 · 마지막 위치'}`
            : shownRobots.length > 1
              ? `, 순찰 중 로봇 ${shownRobots.length}대`
              : ''
        }, 체크포인트 ${checkpoints.length}곳, 이벤트 ${pins.length}건`}
        className="cmap"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endPan}
        onPointerCancel={endPan}
      >
        <defs>
          <radialGradient id="cmapHalo">
            <stop offset="0" stopColor="var(--graphic)" stopOpacity=".34" />
            <stop offset="1" stopColor="var(--graphic)" stopOpacity="0" />
          </radialGradient>
          <linearGradient id="cmapCone" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stopColor="var(--graphic)" stopOpacity=".34" />
            <stop offset="1" stopColor="var(--graphic)" stopOpacity="0" />
          </linearGradient>
          <radialGradient id="cmapUrgentHalo">
            <stop offset="0" stopColor="var(--urgent)" stopOpacity=".3" />
            <stop offset="1" stopColor="var(--urgent)" stopOpacity="0" />
          </radialGradient>
          {/* 무대 광원 — 유리 패널과 같은 방향(좌상단)에서 들어오는 면광 */}
          <radialGradient id="cmapLight" cx="18%" cy="0%" r="90%">
            <stop offset="0" stopColor="#fff" stopOpacity=".5" />
            <stop offset="1" stopColor="#fff" stopOpacity="0" />
          </radialGradient>
          {/* 위험구역 해칭 — 색 외 이중 표기 */}
          <pattern id="cmapHatch" width="6" height="6" patternTransform="rotate(45)" patternUnits="userSpaceOnUse">
            <line x1="0" y1="0" x2="0" y2="6" stroke="var(--alert)" strokeOpacity=".28" strokeWidth="1.6" />
          </pattern>
        </defs>

        <g
          className="cmview"
          transform={`translate(${VW / 2} ${VH / 2}) scale(${view.k}) translate(${-view.cx} ${-view.cy})`}
        >
          <g transform={`translate(${PAD.l},${PAD.t})`}>
            {/* 백엔드가 스캔한 단지 도면 — 회색조로 눌러 무대 톤과 맞춘다(.mapbase) */}
            {map.mapImageUrl && (
              <image
                className="mapbase"
                href={map.mapImageUrl}
                x="0"
                y="0"
                width={W}
                height={H}
                preserveAspectRatio="none"
              />
            )}

            {/* 격자 — 셀을 SUB 등분한 잔격자(옅게) + 셀 경계(진하게) 2단 */}
            <g stroke="currentColor" strokeWidth="0.6" opacity=".05" aria-hidden>
              {Array.from({ length: map.cols * SUB + 1 }, (_, i) => (
                <line key={`sv${i}`} x1={px(i) / SUB} y1="0" x2={px(i) / SUB} y2={H} />
              ))}
              {Array.from({ length: map.rows * SUB + 1 }, (_, i) => (
                <line key={`sh${i}`} x1="0" y1={py(i) / SUB} x2={W} y2={py(i) / SUB} />
              ))}
            </g>
            <g stroke="currentColor" strokeWidth="0.8" opacity=".08" aria-hidden>
              {Array.from({ length: map.cols + 1 }, (_, i) => (
                <line key={`v${i}`} x1={px(i)} y1="0" x2={px(i)} y2={H} />
              ))}
              {Array.from({ length: map.rows + 1 }, (_, i) => (
                <line key={`h${i}`} x1="0" y1={py(i)} x2={W} y2={py(i)} />
              ))}
            </g>

            {/* 단지 외곽 — 순찰 경계 */}
            <rect
              x="1"
              y="1"
              width={W - 2}
              height={H - 2}
              rx="10"
              fill="none"
              stroke="currentColor"
              strokeOpacity=".2"
              strokeWidth="1.2"
              strokeDasharray="7 6"
              aria-hidden
            />
            <text className="cmedge" x={W / 2} y={H + 8} textAnchor="middle" aria-hidden>
              단지 외곽 · 순찰 경계
            </text>

            {/* ── 등록 구역 (온보딩 1y에서 저장된 Zone 그대로) ── */}
            {map.zones.map((z) =>
              z.rect && !gateIds.has(z.id) ? (
                <g key={z.id} className="cmz" style={zoneVar(z.type)}>
                  <rect
                    x={px(z.rect.x) + 2}
                    y={py(z.rect.y) + 2}
                    width={px(z.rect.w) - 4}
                    height={py(z.rect.h) - 4}
                    rx="7"
                  />
                  {/* 유형에서 유도되는 설비 묘사 (주차면·수거함·복귀 깃발·건물 윤곽) */}
                  <ZoneDetail
                    type={z.type}
                    x={px(z.rect.x) + 2}
                    y={py(z.rect.y) + 2}
                    w={px(z.rect.w) - 4}
                    h={py(z.rect.h) - 4}
                  />
                  {/* 건물(기타)은 블록 정중앙, 설비 구역은 묘사를 가리지 않게 상단 */}
                  {z.rect.w * z.rect.h >= 6 ? (
                    <text
                      className="mid"
                      x={px(z.rect.x) + px(z.rect.w) / 2}
                      y={z.type === '기타' ? py(z.rect.y) + py(z.rect.h) / 2 + 3.4 : py(z.rect.y) + 15}
                      textAnchor="middle"
                    >
                      {z.label}
                    </text>
                  ) : (
                    <>
                      <rect
                        className="bul"
                        x={px(z.rect.x) + 8}
                        y={py(z.rect.y) + 9}
                        width="4"
                        height="4"
                        transform={`rotate(45 ${px(z.rect.x) + 10} ${py(z.rect.y) + 11})`}
                      />
                      <text x={px(z.rect.x) + 16} y={py(z.rect.y) + 14.5}>
                        {z.label}
                      </text>
                    </>
                  )}
                </g>
              ) : null,
            )}

            {/* 출입구 — 경계 안쪽 라벨로만 표기 */}
            {gates.map((g) => {
              const lx = g.edge === 'l' ? g.gx + 8 : g.edge === 'r' ? g.gx - 8 : g.gx
              const ly = g.edge === 't' ? g.gy + 14 : g.edge === 'b' ? g.gy - 9 : g.gy + 2.6
              return (
                <g key={`gate-${g.zone.id}`} className="cmgate">
                  <text x={lx} y={ly} textAnchor={g.edge === 'l' ? 'start' : g.edge === 'r' ? 'end' : 'middle'}>
                    {g.zone.label}
                  </text>
                  <title>{g.zone.label}</title>
                </g>
              )
            })}

            {/* ── 순찰 경로 — 예정 점선은 항상, 완료 실선은 순찰 중에만 표시 ── */}
            {showRoute && (
              <g aria-hidden>
                <path className="cmroute" d={roundedPath(routePts, CORNER)} />
                {donePts.length > 1 && (
                  <>
                    <path className="cmdoneglow" d={roundedPath(donePts, CORNER)} />
                    <path className="cmdone" d={roundedPath(donePts, CORNER)} />
                  </>
                )}
              </g>
            )}

            {/* 체크포인트 — 통과(채운 점)/대기(빈 점). 통과 기록(note)은 툴팁으로만 */}
            {checkpoints.map((c, i) => {
              const on = visited(i)
              const x = px(c.x)
              const y = py(c.y)
              const title = cpLabel(c, i)
              const flip = y < 24 // 상단 가장자리에 붙으면 라벨을 아래로
              return (
                <g key={c.id} className={cn('cmwp', !on && 'pend')}>
                  <circle cx={x} cy={y} r="4.4" />
                  <text x={x} y={y + (flip ? 16 : -10)} textAnchor="middle">
                    {title}
                  </text>
                  <title>{`${title}${c.note ? ` — ${c.note}` : on ? ' — 순찰 완료' : ' — 대기'}`}</title>
                </g>
              )
            })}

            {/* ── 이벤트 핀 — 긴급은 물방울 마커 + 확산 링 + 카드 ── */}
            {pins.map((p) => {
              const x = px(p.x)
              const y = py(p.y)
              if (p.tone === 'danger') {
                return (
                  <g key={p.id}>
                    <circle cx={x} cy={y - 9} r="26" fill="url(#cmapUrgentHalo)" aria-hidden />
                    <circle cx={x} cy={y} r="4" fill="none" stroke="var(--urgent)" strokeWidth="1.4" aria-hidden>
                      <animate attributeName="r" values="4;15;4" dur="2.6s" repeatCount="indefinite" />
                      <animate attributeName="opacity" values=".8;0;.8" dur="2.6s" repeatCount="indefinite" />
                    </circle>
                    <g className="cmmark urg" transform={`translate(${x},${y})`}>
                      <path d={pinPath(6.2, 15)} />
                      <circle className="core" cy="-15" r="2.4" />
                    </g>
                    <Callout x={x} y={y} title={p.label} sub={p.detail} below urgent W={W} H={H} />
                    <title>{`${p.label}${p.detail ? ` — ${p.detail}` : ''}`}</title>
                  </g>
                )
              }
              const color = toneVar[p.tone]
              return (
                <g key={p.id}>
                  <circle cx={x} cy={y} r="7" fill={color} fillOpacity=".18" />
                  <circle cx={x} cy={y} r="3.4" fill={color} />
                  <circle cx={x} cy={y} r="3.4" fill="none" stroke="#fff" strokeOpacity=".9" strokeWidth="1.2" />
                  <title>{p.label}</title>
                </g>
              )
            })}

            {/* ── 로봇 위치 — 헤일로 + (한 대만 볼 때) 진행 방향 스캔 콘 ── */}
            {shownRobots.map((r) => {
              const rx = px(r.x)
              const ry = py(r.y)
              const solo = shownRobots.length === 1
              const heading = r.heading ?? (solo ? routeHeading : 0)
              return (
                <g key={`bot-${r.id}`}>
                  <g className="bot" transform={`translate(${rx},${ry}) rotate(${heading})`}>
                    <circle r="30" fill="url(#cmapHalo)" />
                    {/* 진행 방향 스캔 콘 — 한 대를 이동 중으로 볼 때만 */}
                    {solo && patrolling && showRoute && (
                      <path d="M0 0 L40 -19 A44 44 0 0 1 40 19 Z" fill="url(#cmapCone)" />
                    )}
                    <circle r="7" fill="none" stroke="var(--graphic)" strokeWidth="1.5">
                      <animate attributeName="r" values="7;20;7" dur="2.8s" repeatCount="indefinite" />
                      <animate attributeName="opacity" values=".8;0;.8" dur="2.8s" repeatCount="indefinite" />
                    </circle>
                  </g>
                  <g className="cmbotdot" transform={`translate(${rx},${ry})`}>
                    <circle r="6.4" />
                    <circle className="core" r="2.6" />
                  </g>
                  {/* 라벨 — 오른쪽 끝에 붙으면 왼쪽으로 (시안과 같은 읽기 방식).
                      위/아래는 체크포인트 라벨(점 기준 -10)과 겹치지 않게 24 만큼 띄운다 */}
                  {rx > W * 0.72 ? (
                    <text className="cmbot" x={rx - 13} y={ry + 2.8} textAnchor="end">
                      {r.name ?? r.id}
                    </text>
                  ) : (
                    <text className="cmbot" x={rx} y={ry < 34 ? ry + 26 : ry - 24} textAnchor="middle">
                      {r.name ?? r.id}
                    </text>
                  )}
                  <title>{`${r.name ?? r.id} ${patrolling ? '현재 위치' : '마지막 위치'}`}</title>
                </g>
              )
            })}

            {/* 무대 광원 — 유리와 같은 방향의 면광. 클릭을 막지 않도록 마지막에 얹는다 */}
            <rect className="cmlight" x="0" y="0" width={W} height={H} rx="10" fill="url(#cmapLight)" aria-hidden />
          </g>
        </g>

        {/* 축척 — 확대해도 실제 거리를 유지하도록 배율만큼 늘린다.
           백엔드 resolution 이 있을 때만 그린다(지어내지 않음) */}
        {map.metersPerCell != null && (
          <g
            className="cmscale"
            transform={`translate(${VW - PAD.r - scaleLen - scaleShift},${VH - 12})`}
            aria-hidden
          >
            <line x1="0" y1="0" x2={scaleLen} y2="0" />
            <line x1="0" y1="-3" x2="0" y2="3" />
            <line x1={scaleLen} y1="-3" x2={scaleLen} y2="3" />
            <text x={scaleLen / 2} y="-6" textAnchor="middle">
              {Math.round(map.metersPerCell * 2)}미터
            </text>
          </g>
        )}
      </svg>

      {/* ── 오버레이 — 확대해도 크기가 고정돼야 하는 조작·표기 ── */}
      <div className="cmovl tl">
        <button type="button" className="cmbtn" onClick={() => zoomBy(1.5)} disabled={view.k >= ZOOM_MAX} aria-label="지도 확대">
          <svg viewBox="0 0 16 16" aria-hidden>
            <path d="M8 3.4V12.6M3.4 8H12.6" />
          </svg>
        </button>
        <button type="button" className="cmbtn" onClick={() => zoomBy(1 / 1.5)} disabled={view.k <= 1} aria-label="지도 축소">
          <svg viewBox="0 0 16 16" aria-hidden>
            <path d="M3.4 8H12.6" />
          </svg>
        </button>
        <button type="button" className="cmbtn" onClick={resetView} disabled={view.k === 1} aria-label="지도 전체 보기">
          <svg viewBox="0 0 16 16" aria-hidden>
            <circle cx="8" cy="8" r="5.4" />
            <circle cx="8" cy="8" r="1.8" />
          </svg>
        </button>
      </div>

      <div className="cmovl tr">
        <span className="cmclock">
          실시간 · <b className="num">{clock}</b>
        </span>
        <span className="cmnorth" aria-hidden>
          <svg viewBox="0 0 24 24">
            <path className="n" d="M12 5.6 L15.4 15.2 L12 13.1 L8.6 15.2 Z" />
          </svg>
        </span>
      </div>

      <div className="cmovl bl">
        <div className="cmlegend">
          {showRoute && prog ? (
            <>
              <span className="lg">
                <i className="d on" />
                완료 구간 · 통과 지점
              </span>
              <span className="lg">
                <i className="d" />
                예정 구간 · 대기 지점
              </span>
            </>
          ) : showRoute ? (
            <span className="lg">
              <i className="d" />
              예정 순찰 경로 · 지점 {checkpoints.length}곳
            </span>
          ) : (
            <span className="lg">
              <i className="d" />
              순찰 지점 · 경로 미표시
            </span>
          )}
          {hasUrgentPin && (
            <span className="lg">
              <i className="d u" />
              긴급 이벤트
            </span>
          )}
        </div>
      </div>

      {bottomRight && <div className="cmovl br">{bottomRight}</div>}
    </div>
  )
}

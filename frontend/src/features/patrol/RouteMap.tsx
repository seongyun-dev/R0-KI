import { cn } from '../../lib/cn'

export type RouteMapProps = {
  /** 경유 구역 순서 (예: 출발지 → 주차장 A → …) */
  zones: string[]
  className?: string
}

const W = 400
const H = 210
const PAD = 36

/** 이동 경로 지도 (1e) — 그리드 맵 위 경유지 폴리라인 (SVG) */
export function RouteMap({ zones, className }: RouteMapProps) {
  // 경유지를 좌→우 지그재그로 배치
  const n = Math.max(zones.length, 2)
  const points = zones.map((_, i) => {
    const x = PAD + ((W - PAD * 2) * i) / (n - 1)
    const y = H / 2 + (i % 2 === 0 ? 1 : -1) * (H / 4.5) * (i === 0 || i === n - 1 ? 0.6 : 1)
    return { x, y }
  })
  const path = points.map((p) => `${p.x},${p.y}`).join(' ')

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label={`이동 경로: ${zones.join(' → ')}`}
      className={cn('w-full rounded-card-sm bg-surface ring-1 ring-line', className)}
    >
      {/* 그리드 */}
      {Array.from({ length: 9 }, (_, i) => (
        <line key={`v${i}`} x1={(W / 9) * (i + 0.5)} y1="0" x2={(W / 9) * (i + 0.5)} y2={H} className="stroke-line" strokeWidth="1" />
      ))}
      {Array.from({ length: 5 }, (_, i) => (
        <line key={`h${i}`} x1="0" y1={(H / 5) * (i + 0.5)} x2={W} y2={(H / 5) * (i + 0.5)} className="stroke-line" strokeWidth="1" />
      ))}

      {/* 경로 */}
      <polyline points={path} fill="none" className="stroke-info" strokeWidth="2.5" strokeDasharray="6 5" strokeLinecap="round" strokeLinejoin="round" />

      {points.map((p, i) => {
        const isEnd = i === 0 || i === zones.length - 1
        return (
          <g key={i}>
            <circle cx={p.x} cy={p.y} r={isEnd ? 7 : 5.5} className={isEnd ? 'fill-accent' : 'fill-info'} />
            <circle cx={p.x} cy={p.y} r={2.2} className="fill-white" />
            <text
              x={p.x}
              y={p.y + (points[i].y < H / 2 ? -14 : 22)}
              textAnchor="middle"
              className="fill-muted font-sans"
              fontSize="10"
              fontWeight="600"
            >
              {zones[i]}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

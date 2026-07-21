import { cn } from '../../lib/cn'
import type { ComplexMapData, MapPin, MapRobot, Tone } from '../../types/domain'

/* 단지 실시간 지도 (1c) — 백엔드(IoT 스캔 맵) 데이터를 받아 그리는 순수 렌더러.
   좌표는 온보딩(1y)과 같은 그리드 단위(cols×rows)로 들어오고,
   여기서 SVG viewBox 좌표로 변환만 한다. */

const CELL = 30 // 그리드 1칸 → SVG 30px

const toneFill: Record<Tone, string> = {
  success: 'fill-success',
  info: 'fill-info',
  warning: 'fill-warning',
  danger: 'fill-danger',
  neutral: 'fill-muted',
}

export type ComplexMapProps = {
  map: ComplexMapData
  robot?: MapRobot
  pins?: MapPin[]
  className?: string
}

export function ComplexMap({ map, robot, pins = [], className }: ComplexMapProps) {
  const W = map.cols * CELL
  const H = map.rows * CELL
  const px = (gx: number) => gx * CELL
  const py = (gy: number) => gy * CELL

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label={`단지 실시간 지도 — 구역 ${map.zones.length}곳${robot ? `, 로봇 ${robot.id} 순찰 중` : ''}, 이벤트 ${pins.length}건`}
      className={cn('w-full rounded-card-sm bg-surface ring-1 ring-line', className)}
    >
      {/* 그리드 */}
      <g aria-hidden>
        {Array.from({ length: map.cols + 1 }, (_, i) => (
          <line key={`v${i}`} x1={px(i)} y1="0" x2={px(i)} y2={H} className="stroke-line" strokeWidth="1" />
        ))}
        {Array.from({ length: map.rows + 1 }, (_, i) => (
          <line key={`h${i}`} x1="0" y1={py(i)} x2={W} y2={py(i)} className="stroke-line" strokeWidth="1" />
        ))}
      </g>

      {/* 등록 구역 (온보딩 1y에서 저장된 Zone 그대로) */}
      {map.zones.map((z) =>
        z.rect ? (
          <g key={z.id}>
            <rect
              x={px(z.rect.x) + 2}
              y={py(z.rect.y) + 2}
              width={px(z.rect.w) - 4}
              height={py(z.rect.h) - 4}
              rx="6"
              className="fill-surface-2/70 stroke-line"
              strokeWidth="1.5"
            />
            <text x={px(z.rect.x) + 8} y={py(z.rect.y) + 15} className="fill-muted font-sans" fontSize="8.5" fontWeight="600">
              {z.label}
            </text>
          </g>
        ) : null,
      )}

      {/* 이벤트 핀 */}
      {pins.map((p) => (
        <g key={p.id}>
          <circle cx={px(p.x)} cy={py(p.y)} r="8" className={cn(toneFill[p.tone], 'opacity-20')}>
            <animate attributeName="r" values="6;12;6" dur="2.4s" repeatCount="indefinite" />
            <animate attributeName="opacity" values="0.28;0;0.28" dur="2.4s" repeatCount="indefinite" />
          </circle>
          <circle cx={px(p.x)} cy={py(p.y)} r="4" className={toneFill[p.tone]} />
          <title>{p.label}</title>
        </g>
      ))}

      {/* 로봇 현재 위치 */}
      {robot && (
        <g>
          <circle cx={px(robot.x)} cy={py(robot.y)} r="12" className="fill-accent opacity-15">
            <animate attributeName="r" values="10;16;10" dur="2s" repeatCount="indefinite" />
          </circle>
          <circle cx={px(robot.x)} cy={py(robot.y)} r="6.5" className="fill-accent" />
          <circle cx={px(robot.x)} cy={py(robot.y)} r="2.4" className="fill-white" />
          <text x={px(robot.x)} y={py(robot.y) - 14} textAnchor="middle" className="fill-fg font-mono" fontSize="8.5" fontWeight="700">
            {robot.id}
          </text>
          <title>{robot.id} 현재 위치</title>
        </g>
      )}
    </svg>
  )
}

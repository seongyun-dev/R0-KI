import type { HandlingStat } from '../../types/domain'
import { ChartFrame } from './ChartFrame'

/* 처리 현황 (100% 기준) (1m) — 항목별 처리/미처리 100% 누적 바.
   두 계열이므로 색 + 직접 라벨(퍼센트·건수)로 이중 부호화한다. */
const LEGEND = [
  { label: '처리', color: 'var(--success)' },
  { label: '미처리', color: 'var(--warning)' },
]

export function HandlingChart({ data }: { data: HandlingStat[] }) {
  return (
    <ChartFrame
      title="처리 현황 (100% 기준)"
      legend={LEGEND}
      table={{
        caption: '항목별 처리/미처리 건수 및 비율',
        head: ['항목', '처리(건)', '미처리(건)', '처리율(%)'],
        rows: data.map((d) => [d.label, d.handled, d.pending, d.handledPct]),
      }}
    >
      <ul className="flex flex-col gap-4">
        {data.map((d) => (
          <li key={d.label} className="flex flex-col gap-1.5">
            <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
              <span className="text-sm font-semibold">{d.label}</span>
              <span className="font-mono text-xs tabular text-muted">
                처리 {d.handledPct}% · 미처리 {d.pendingPct}%
              </span>
            </div>
            <div className="flex h-7 w-full overflow-hidden rounded-control bg-surface" role="img"
              aria-label={`${d.label} 처리 ${d.handled}건(${d.handledPct}%), 미처리 ${d.pending}건(${d.pendingPct}%)`}>
              <div
                className="flex items-center justify-end bg-success pr-2"
                style={{ width: `${d.handledPct}%` }}
              >
                <span className="font-mono text-xs font-bold tabular text-white">{d.handled}건</span>
              </div>
              <div
                className="flex items-center justify-end bg-warning pr-2"
                style={{ width: `${d.pendingPct}%` }}
              >
                <span className="font-mono text-xs font-bold tabular text-white">{d.pending}건</span>
              </div>
            </div>
          </li>
        ))}
      </ul>
    </ChartFrame>
  )
}

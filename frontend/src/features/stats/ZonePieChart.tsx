import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import type { ZoneShareStat } from '../../types/domain'
import { ChartFrame } from './ChartFrame'
import { ChartTooltip } from './ChartTooltip'

const COLORS = ['var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)', 'var(--chart-4)']

/** 구역별 이벤트 비율 (파이차트) (1m) — 도넛 중앙에 총 건수 */
export function ZonePieChart({ data }: { data: ZoneShareStat[] }) {
  const total = data.reduce((s, d) => s + d.count, 0)

  return (
    <ChartFrame
      title="구역별 이벤트 비율"
      table={{
        caption: '구역별 이벤트 건수 및 비율',
        head: ['구역', '건수', '비율(%)'],
        rows: data.map((d) => [d.zone, d.count, d.pct]),
      }}
    >
      <div className="flex flex-col items-center gap-5 sm:flex-row">
        <div className="relative h-48 w-48 flex-none">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={data}
                dataKey="count"
                nameKey="zone"
                innerRadius="58%"
                outerRadius="90%"
                paddingAngle={2}
                stroke="var(--bg)"
                strokeWidth={2}
                isAnimationActive={false}
              >
                {data.map((d, i) => (
                  <Cell key={d.zone} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip content={<ChartTooltip />} />
            </PieChart>
          </ResponsiveContainer>
          {/* 도넛 중앙 총계 */}
          <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
            <span className="font-mono text-2xl font-bold tabular">{total}건</span>
            <span className="text-xs text-muted">전체</span>
          </div>
        </div>

        {/* 범례 = 직접 라벨 (건수 · 비율) */}
        <ul className="flex w-full flex-col gap-2.5">
          {data.map((d, i) => (
            <li key={d.zone} className="flex items-center gap-2.5 text-sm">
              <span
                aria-hidden
                className="h-2.5 w-2.5 flex-none rounded-sm"
                style={{ background: COLORS[i % COLORS.length] }}
              />
              <span className="min-w-0 flex-1 truncate">{d.zone}</span>
              <span className="font-mono text-xs tabular text-muted">
                {d.count}건 · {d.pct}%
              </span>
            </li>
          ))}
        </ul>
      </div>
    </ChartFrame>
  )
}

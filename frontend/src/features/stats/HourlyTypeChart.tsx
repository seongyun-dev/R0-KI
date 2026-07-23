import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { HourlyEventStat } from '../../types/domain'
import { ChartFrame } from './ChartFrame'
import { ChartTooltip } from './ChartTooltip'

/* 유형 → 차트 카테고리 색. 상태색(success/warning/danger)은 "상태"를 뜻하므로
   카테고리 구분에는 쓰지 않는다. 누적 순서는 인접 색이 가장 잘 구분되도록
   쓰레기(틸) → 주차(블루) → 위험구역(오렌지). 범례는 와이어프레임 순서 유지. */
const SERIES = [
  { key: '쓰레기', color: 'var(--chart-2)' },
  { key: '주차', color: 'var(--chart-1)' },
  { key: '위험구역', color: 'var(--chart-3)' },
] as const

const LEGEND = [
  { label: '주차', color: 'var(--chart-1)' },
  { label: '쓰레기', color: 'var(--chart-2)' },
  { label: '위험구역', color: 'var(--chart-3)' },
]

/** 시간대별 이벤트 발생(유형별) (1m) — 누적 막대 */
export function HourlyTypeChart({ data }: { data: HourlyEventStat[] }) {
  const withTotal = data.map((d) => ({ ...d, total: d.주차 + d.쓰레기 + d.위험구역 }))
  const peak = withTotal.reduce((a, b) => (b.total > a.total ? b : a), withTotal[0])

  return (
    <ChartFrame
      title="시간대별 이벤트 발생 (유형별)"
      caption={peak ? `${peak.slot} ${peak.total}건` : undefined}
      legend={LEGEND}
      table={{
        caption: '시간대별 유형별 이벤트 발생 건수',
        head: ['시간대', '주차', '쓰레기', '위험구역', '합계'],
        rows: withTotal.map((d) => [d.slot, d.주차, d.쓰레기, d.위험구역, d.total]),
      }}
    >
      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={withTotal} margin={{ top: 20, right: 12, bottom: 0, left: -18 }} barCategoryGap="22%">
            <CartesianGrid vertical={false} stroke="var(--line)" />
            <XAxis
              dataKey="slot"
              tick={{ fill: 'var(--muted)', fontSize: 10.5 }}
              interval={0}
              tickLine={false}
              axisLine={{ stroke: 'var(--line)' }}
            />
            <YAxis
              tick={{ fill: 'var(--muted)', fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              allowDecimals={false}
              width={40}
            />
            <Tooltip content={<ChartTooltip />} cursor={{ fill: 'var(--surface)' }} />
            {SERIES.map((s, i) => (
              <Bar
                key={s.key}
                dataKey={s.key}
                name={s.key}
                stackId="hour"
                fill={s.color}
                /* 세그먼트 사이 2px 표면 간격 */
                stroke="var(--bg)"
                strokeWidth={2}
                isAnimationActive={false}
                radius={i === SERIES.length - 1 ? [4, 4, 0, 0] : undefined}
              >
                {i === SERIES.length - 1 && (
                  <LabelList
                    dataKey="total"
                    position="top"
                    offset={8}
                    fill="var(--fg)"
                    fontSize={11}
                    fontWeight={700}
                  />
                )}
              </Bar>
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </ChartFrame>
  )
}

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { DailyEventStat } from '../../types/domain'
import { ChartFrame } from './ChartFrame'
import { ChartTooltip } from './ChartTooltip'

/** 일자별 이벤트 추이 (1m) — 단일 시리즈 꺾은선 */
export function EventTrendChart({ data }: { data: DailyEventStat[] }) {
  const last = data[data.length - 1]
  const prev = data[data.length - 2]
  const diff = last && prev ? last.count - prev.count : 0

  return (
    <ChartFrame
      title="일자별 이벤트 추이"
      caption={
        last ? (
          <>
            {last.date} {last.count}건 · 전일 {diff > 0 ? `+${diff}` : diff}건 {diff > 0 ? '▲' : diff < 0 ? '▼' : ''}
          </>
        ) : undefined
      }
      table={{
        caption: '일자별 이벤트 발생 건수',
        head: ['일자', '건수'],
        rows: data.map((d) => [d.date, d.count]),
      }}
    >
      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
            <CartesianGrid vertical={false} stroke="var(--line)" />
            <XAxis
              dataKey="date"
              tick={{ fill: 'var(--muted)', fontSize: 11 }}
              tickLine={false}
              axisLine={{ stroke: 'var(--line)' }}
              interval="preserveStartEnd"
              minTickGap={16}
            />
            <YAxis
              tick={{ fill: 'var(--muted)', fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              allowDecimals={false}
              width={40}
            />
            <Tooltip
              content={<ChartTooltip />}
              cursor={{ stroke: 'var(--subtle)', strokeWidth: 1, strokeDasharray: '4 4' }}
            />
            <Line
              type="monotone"
              dataKey="count"
              name="이벤트"
              stroke="var(--accent)"
              strokeWidth={2}
              /* 데이터 표시가 진입 애니메이션에 의존하지 않도록(리듀스드모션·백그라운드 탭) */
              isAnimationActive={false}
              dot={{ r: 3, fill: 'var(--accent)', strokeWidth: 0 }}
              activeDot={{ r: 5, fill: 'var(--accent)', stroke: 'var(--bg)', strokeWidth: 2 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </ChartFrame>
  )
}

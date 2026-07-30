import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { DailyEventStat } from '../../types/domain'
import { AXIS_TICK_NUM } from './chartTheme'
import { ChartTooltip } from './ChartTooltip'

/* 일자별 이벤트 추이 — 시안 R0Ki-stats cTrend 그대로.
   --graphic 단일 꺾은선 + 아래로 사라지는 면 채움. 패널 헤더/메타는 Stats.tsx 가 담당. */
export function EventTrendChart({ data }: { data: DailyEventStat[] }) {
  return (
    <div className="st-chart">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 16, right: 16, bottom: 0, left: -22 }}>
          <defs>
            <linearGradient id="stTrendFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--graphic)" stopOpacity={0.26} />
              <stop offset="100%" stopColor="var(--graphic)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid vertical={false} stroke="var(--hair)" strokeDasharray="4 4" />
          <XAxis
            dataKey="date"
            tick={AXIS_TICK_NUM}
            tickLine={false}
            axisLine={{ stroke: 'var(--hair)' }}
            interval={1}
          />
          <YAxis
            tick={AXIS_TICK_NUM}
            tickLine={false}
            axisLine={false}
            allowDecimals={false}
            width={40}
          />
          <Tooltip
            content={<ChartTooltip />}
            cursor={{ stroke: 'var(--hair)', strokeWidth: 1, strokeDasharray: '4 4' }}
          />
          <Area
            type="monotone"
            dataKey="count"
            name="이벤트"
            stroke="var(--graphic)"
            strokeWidth={2.6}
            fill="url(#stTrendFill)"
            /* 데이터 표시가 진입 애니메이션에 의존하지 않도록(리듀스드모션·백그라운드 탭) */
            isAnimationActive={false}
            dot={false}
            activeDot={{ r: 5, fill: 'var(--graphic)', stroke: 'var(--page)', strokeWidth: 2 }}
          />
        </AreaChart>
      </ResponsiveContainer>

      {/* 스크린리더용 데이터 테이블 — 색만으로 정보를 전달하지 않기 위함 */}
      <table className="sr-only">
        <caption>일자별 이벤트 발생 건수</caption>
        <thead>
          <tr><th scope="col">일자</th><th scope="col">건수</th></tr>
        </thead>
        <tbody>
          {data.map((d) => (
            <tr key={d.date}><th scope="row">{d.date}</th><td>{d.count}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

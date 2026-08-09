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
import { AXIS_TICK, AXIS_TICK_NUM, RAMP } from './chartTheme'
import { ChartTooltip } from './ChartTooltip'

/* 시간대별 이벤트 발생(유형별 누적) — 시안 R0Ki-stats cHour 레이아웃 유지.
   데이터만 백엔드 trend?bucket=hour3 (3시간×8칸) + 주차/쓰레기 묶음에 맞춤.
   --graphic 단일 계열 명도 램프 — 램프 순서 = 주의도(진할수록 주의).
   아래(진함)→위(옅음) 누적, 스택 꼭대기에 합계 라벨.
   위험(EMERGENCY) 유형은 시안과 같이 이 차트에서 제외. */
export const HOURLY_SERIES = [
  { key: '주차', opacity: RAMP[1] },
  { key: '쓰레기', opacity: RAMP[2] },
] as const

/** 시리즈명 → 명도 (툴팁 마커 공유용) */
export const HOURLY_OPACITIES = Object.fromEntries(HOURLY_SERIES.map((s) => [s.key, s.opacity]))

export function HourlyTypeChart({
  data,
  includeA11yTable = true,
}: {
  data: HourlyEventStat[]
  includeA11yTable?: boolean
}) {
  const withTotal = data.map((d) => ({ ...d, total: d.주차 + d.쓰레기 }))

  return (
    <div className="st-chart">
      <ResponsiveContainer width="100%" height="100%">
        {/* 8칸 기준: 막대 간격만 소폭 조정(높이·패널 크기는 CSS 그대로) */}
        <BarChart data={withTotal} margin={{ top: 22, right: 12, bottom: 8, left: 0 }} barCategoryGap="18%">
          <CartesianGrid vertical={false} stroke="var(--hair)" strokeDasharray="4 4" />
          <XAxis
            dataKey="slot"
            tick={AXIS_TICK}
            interval={0}
            tickLine={false}
            axisLine={{ stroke: 'var(--hair)' }}
          />
          <YAxis
            tick={AXIS_TICK_NUM}
            tickLine={false}
            axisLine={false}
            allowDecimals={false}
            width={40}
          />
          <Tooltip
            content={<ChartTooltip opacities={HOURLY_OPACITIES} />}
            cursor={{ fill: 'var(--graphic)', fillOpacity: 0.07 }}
          />
          {HOURLY_SERIES.map((s, i) => (
            <Bar
              key={s.key}
              dataKey={s.key}
              name={s.key}
              stackId="hour"
              maxBarSize={34}
              fill="var(--graphic)"
              fillOpacity={s.opacity}
              isAnimationActive={false}
              radius={i === HOURLY_SERIES.length - 1 ? [6, 6, 0, 0] : undefined}
            >
              {/* 스택 꼭대기(마지막 시리즈) 위에 합계 */}
              {i === HOURLY_SERIES.length - 1 && (
                <LabelList
                  dataKey="total"
                  position="top"
                  offset={7}
                  fill="var(--text-1)"
                  fontFamily="var(--mono)"
                  fontSize={12.5}
                  fontWeight={700}
                />
              )}
            </Bar>
          ))}
        </BarChart>
      </ResponsiveContainer>

      {includeA11yTable && (
        <table className="sr-only">
          <caption>시간대별 유형별 이벤트 발생 건수</caption>
          <thead>
            <tr>
              <th scope="col">시간대</th>
              <th scope="col">주차</th><th scope="col">쓰레기</th><th scope="col">합계</th>
            </tr>
          </thead>
          <tbody>
            {withTotal.map((d) => (
              <tr key={d.slot}>
                <th scope="row">{d.slot}</th>
                <td>{d.주차}</td><td>{d.쓰레기}</td><td>{d.total}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

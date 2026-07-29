import {
  Bar,
  BarChart,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { HandlingStat } from '../../types/domain'
import { ChartTooltip } from './ChartTooltip'

/* 처리 현황 (100% 기준) — 시안 R0Ki-stats cDone 그대로.
   가로 100% 누적 바 — 처리(옅음) + 미처리(진함, 주의 항목이라 더 진하다).
   세그먼트 안에 "N건 · P%" 직접 라벨로 이중 부호화. */
export const HANDLING_OPACITIES: Record<string, number> = { 처리: 0.28, 미처리: 1 }

type SegLabelProps = {
  x?: number | string
  y?: number | string
  width?: number | string
  height?: number | string
  index?: number
}

/** 세그먼트 중앙 라벨 — "N건 · P%" */
function segLabel(data: HandlingStat[], key: 'handled' | 'pending', color: string) {
  return function SegLabel({ x, y, width, height, index }: SegLabelProps) {
    if (index == null) return null
    const d = data[index]
    const cx = Number(x) + Number(width) / 2
    const cy = Number(y) + Number(height) / 2
    const text =
      key === 'handled' ? `${d.handled}건 · ${d.handledPct}%` : `${d.pending}건 · ${d.pendingPct}%`
    // 세그먼트가 극단적으로 좁을 때만 생략 — 시안(ECharts)은 항상 표시한다
    if (Number(width) < 36) return null
    return (
      <text
        x={cx}
        y={cy}
        fill={color}
        textAnchor="middle"
        dominantBaseline="central"
        fontFamily="var(--mono)"
        fontSize={12}
        fontWeight={700}
      >
        {text}
      </text>
    )
  }
}

export function HandlingChart({ data }: { data: HandlingStat[] }) {
  return (
    <div className="st-chart">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart layout="vertical" data={data} margin={{ top: 6, right: 10, bottom: 6, left: -6 }}>
          <XAxis type="number" domain={[0, 100]} hide />
          <YAxis
            type="category"
            dataKey="label"
            width={70}
            tick={{ fill: 'var(--text-2)', fontSize: 13.5, fontWeight: 700 }}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip
            content={<ChartTooltip unit="%" opacities={HANDLING_OPACITIES} />}
            cursor={{ fill: 'var(--graphic)', fillOpacity: 0.07 }}
          />
          <Bar
            dataKey="handledPct"
            name="처리"
            stackId="d"
            maxBarSize={26}
            fill="var(--graphic)"
            fillOpacity={HANDLING_OPACITIES.처리}
            radius={[7, 0, 0, 7]}
            isAnimationActive={false}
          >
            <LabelList content={segLabel(data, 'handled', 'var(--text-1)')} />
          </Bar>
          <Bar
            dataKey="pendingPct"
            name="미처리"
            stackId="d"
            maxBarSize={26}
            fill="var(--graphic)"
            radius={[0, 7, 7, 0]}
            isAnimationActive={false}
          >
            <LabelList content={segLabel(data, 'pending', 'var(--accent-ink)')} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      <table className="sr-only">
        <caption>항목별 처리/미처리 건수 및 비율</caption>
        <thead>
          <tr>
            <th scope="col">항목</th><th scope="col">처리(건)</th>
            <th scope="col">미처리(건)</th><th scope="col">처리율(%)</th>
          </tr>
        </thead>
        <tbody>
          {data.map((d) => (
            <tr key={d.label}>
              <th scope="row">{d.label}</th>
              <td>{d.handled}</td><td>{d.pending}</td><td>{d.handledPct}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

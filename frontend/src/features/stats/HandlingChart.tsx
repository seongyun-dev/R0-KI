import {
  Bar,
  BarChart,
  LabelList,
  Rectangle,
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

/** "N건 · P%" 가 세그먼트 안에 들어가려면 대략 이 정도 폭이 필요하다 */
const MIN_LABEL_WIDTH = 80
const BAR_RADIUS = 7

type SegLabelProps = {
  x?: number | string
  y?: number | string
  width?: number | string
  height?: number | string
  index?: number
}

type BarShapeProps = {
  x?: number
  y?: number
  width?: number
  height?: number
  index?: number
  fill?: string
  fillOpacity?: number
}

type CornerRadius = [number, number, number, number]

/** 세그먼트 중앙 라벨 — 폭이 좁으면 생략하고 툴팁으로만 본다 */
function segLabel(data: HandlingStat[], key: 'handled' | 'pending', color: string) {
  return function SegLabel({ x, y, width, height, index }: SegLabelProps) {
    if (index == null) return null
    const d = data[index]
    const segmentWidth = Number(width)
    if (segmentWidth < MIN_LABEL_WIDTH) return null
    const pct = key === 'handled' ? d.handledPct : d.pendingPct
    if (pct <= 0) return null

    const cx = Number(x) + segmentWidth / 2
    const cy = Number(y) + Number(height) / 2
    const text =
      key === 'handled' ? `${d.handled}건 · ${d.handledPct}%` : `${d.pending}건 · ${d.pendingPct}%`
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

/** 한쪽만 100%면 네 모서리, 둘 다 있으면 바깥쪽만 라운드 */
function stackRadius(
  row: HandlingStat | undefined,
  side: 'handled' | 'pending',
): CornerRadius {
  const hasHandled = (row?.handledPct ?? 0) > 0
  const hasPending = (row?.pendingPct ?? 0) > 0
  const r = BAR_RADIUS
  if (side === 'handled') {
    if (!hasHandled) return [0, 0, 0, 0]
    return hasPending ? [r, 0, 0, r] : [r, r, r, r]
  }
  if (!hasPending) return [0, 0, 0, 0]
  return hasHandled ? [0, r, r, 0] : [r, r, r, r]
}

function barShape(data: HandlingStat[], side: 'handled' | 'pending') {
  return function Shape(props: unknown) {
    const {
      x = 0,
      y = 0,
      width = 0,
      height = 0,
      index = 0,
      fill,
      fillOpacity,
    } = props as BarShapeProps
    if (width <= 0) return <g />
    return (
      <Rectangle
        x={x}
        y={y}
        width={width}
        height={height}
        fill={fill}
        fillOpacity={fillOpacity}
        radius={stackRadius(data[index], side)}
      />
    )
  }
}

export function HandlingChart({
  data,
  includeA11yTable = true,
}: {
  data: HandlingStat[]
  includeA11yTable?: boolean
}) {
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
            shape={barShape(data, 'handled')}
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
            shape={barShape(data, 'pending')}
            isAnimationActive={false}
          >
            <LabelList content={segLabel(data, 'pending', 'var(--accent-ink)')} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      {includeA11yTable && (
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
      )}
    </div>
  )
}

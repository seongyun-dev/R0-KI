import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import type { ZoneShareStat } from '../../types/domain'
import { RAMP } from './chartTheme'
import { ChartTooltip } from './ChartTooltip'

/* 구역별 이벤트 비율 — 시안 R0Ki-stats cZone 그대로.
   도넛(62~86%) + 중앙 총계. 순위 목록(st-rank)은 Stats.tsx 가 담당. */
export function ZonePieChart({
  data,
  includeA11yTable = true,
}: {
  data: ZoneShareStat[]
  includeA11yTable?: boolean
}) {
  const total = data.reduce((s, d) => s + d.count, 0)

  return (
    <div className="st-chart">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data}
            dataKey="count"
            nameKey="zone"
            innerRadius="62%"
            outerRadius="86%"
            stroke="var(--page)"
            strokeWidth={3}
            isAnimationActive={false}
          >
            {data.map((d, i) => (
              <Cell key={d.zone} fill="var(--graphic)" fillOpacity={RAMP[i % RAMP.length]} />
            ))}
          </Pie>
          <Tooltip
            content={
              <ChartTooltip
                opacities={Object.fromEntries(data.map((d, i) => [d.zone, RAMP[i % RAMP.length]]))}
              />
            }
          />
        </PieChart>
      </ResponsiveContainer>

      {/* 도넛 중앙 총계 */}
      <div className="st-dc">
        <span className="v">{total}건</span>
        <span className="k">전체</span>
      </div>

      {includeA11yTable && (
        <table className="sr-only">
          <caption>구역별 이벤트 건수 및 비율</caption>
          <thead>
            <tr><th scope="col">구역</th><th scope="col">건수</th><th scope="col">비율(%)</th></tr>
          </thead>
          <tbody>
            {data.map((d) => (
              <tr key={d.zone}><th scope="row">{d.zone}</th><td>{d.count}</td><td>{d.pct}</td></tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

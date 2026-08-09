import type { TooltipProps } from 'recharts'

/** 차트 공통 툴팁 — 값/라벨은 텍스트 토큰, 색은 옆의 마크가 담당 */
export function ChartTooltip({ active, payload, label }: TooltipProps<number, string>) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-control bg-ink px-3 py-2 text-xs text-white shadow-pop">
      <p className="font-mono font-semibold tabular">{label}</p>
      <ul className="mt-1 flex flex-col gap-0.5">
        {payload.map((p) => (
          <li key={String(p.dataKey)} className="flex items-center gap-2">
            <span aria-hidden className="h-2 w-2 flex-none rounded-sm" style={{ background: p.color }} />
            <span className="text-white/70">{p.name}</span>
            <span className="ml-auto font-mono font-semibold tabular">{p.value}건</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

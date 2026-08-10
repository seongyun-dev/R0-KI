import type { TooltipProps } from 'recharts'

/* r0ki 차트 공통 툴팁 — 시안 ECharts TIP 그대로.
   배경은 --page(불투명), 헤어라인 테두리, 12px 라운드.
   시리즈 마커는 --graphic + 명도 램프라 opacities 로 시리즈별 투명도를 받는다. */
export function ChartTooltip({
  active,
  payload,
  label,
  unit = '건',
  opacities,
}: TooltipProps<number, string> & {
  /** 값 뒤에 붙는 단위 (기본 '건') */
  unit?: string
  /** 시리즈명 → fillOpacity (마커를 차트와 같은 명도로) */
  opacities?: Record<string, number>
}) {
  if (!active || !payload?.length) return null
  return (
    <div
      style={{
        background: 'var(--page)',
        border: '1px solid var(--hair)',
        borderRadius: 12,
        padding: '9px 12px',
        boxShadow: '0 8px 24px rgba(20,56,104,.18)',
        fontFamily: 'var(--sans)',
        fontSize: 13,
        fontWeight: 600,
        color: 'var(--text-1)',
      }}
    >
      {label != null && label !== '' && (
        <p style={{ fontFamily: 'var(--mono)', fontWeight: 700, marginBottom: 4 }}>{label}</p>
      )}
      <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 3 }}>
        {payload.map((p) => (
          <li key={String(p.dataKey ?? p.name)} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span
              aria-hidden
              style={{
                width: 9,
                height: 9,
                borderRadius: 3,
                flex: 'none',
                background: 'var(--graphic)',
                opacity: opacities?.[p.name ?? ''] ?? 1,
              }}
            />
            <span style={{ color: 'var(--text-2)' }}>{p.name}</span>
            <span style={{ marginLeft: 'auto', paddingLeft: 14, fontFamily: 'var(--mono)', fontWeight: 700 }}>
              {p.value}
              {unit}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

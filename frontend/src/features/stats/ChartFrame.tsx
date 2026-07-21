import type { ReactNode } from 'react'

export type ChartFrameProps = {
  title: string
  /** 차트 요약 직접 라벨 (예: 07/15 6건 · 전일 -4건 ▼) */
  caption?: ReactNode
  legend?: { label: string; color: string }[]
  /** 스크린리더용 데이터 테이블 (색만으로 정보를 전달하지 않기 위함) */
  table: { caption: string; head: string[]; rows: (string | number)[][] }
  children: ReactNode
}

/** 차트 공통 프레임 — 제목 + 요약 + 범례 + 접근성 테이블 */
export function ChartFrame({ title, caption, legend, table, children }: ChartFrameProps) {
  return (
    <figure className="flex flex-col gap-3">
      <figcaption className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-bold text-muted">{title}</h2>
        {caption && <span className="font-mono text-xs tabular text-muted">{caption}</span>}
      </figcaption>

      {legend && (
        <ul className="flex flex-wrap gap-x-4 gap-y-1">
          {legend.map((l) => (
            <li key={l.label} className="flex items-center gap-1.5 text-xs text-muted">
              <span aria-hidden className="h-2.5 w-2.5 rounded-sm" style={{ background: l.color }} />
              {l.label}
            </li>
          ))}
        </ul>
      )}

      {children}

      <table className="sr-only">
        <caption>{table.caption}</caption>
        <thead>
          <tr>
            {table.head.map((h) => (
              <th key={h} scope="col">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((r, i) => (
            <tr key={i}>
              {r.map((cell, j) =>
                j === 0 ? <th key={j} scope="row">{cell}</th> : <td key={j}>{cell}</td>,
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  )
}

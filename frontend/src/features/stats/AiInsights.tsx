import { Card } from '../../components/ui'

/** AI 인사이트 (1m) — 기간 통계에서 도출한 권장 사항 */
export function AiInsights({ insights }: { insights: string[] }) {
  return (
    <Card className="p-5 sm:p-6">
      <h2 className="mb-3 flex items-center gap-2 text-sm font-bold text-muted">
        <span aria-hidden className="h-1.5 w-1.5 rounded-pill bg-accent" />
        AI 인사이트
      </h2>
      <ul className="flex flex-col gap-3">
        {insights.map((text) => (
          <li
            key={text}
            className="rounded-card-sm border-l-4 border-accent bg-surface px-5 py-4 text-sm leading-relaxed"
          >
            “{text}”
          </li>
        ))}
      </ul>
    </Card>
  )
}

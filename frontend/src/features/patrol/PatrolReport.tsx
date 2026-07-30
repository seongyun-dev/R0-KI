import { Card } from '../../components/ui'
import type { Patrol } from '../../types/domain'

/** PATROL REPORT 블록 (1e) — AI 요약만 */
export function PatrolReport({ patrol }: { patrol: Patrol }) {
  const report = patrol.report
  if (!report) return null

  return (
    <Card className="p-6 sm:p-8">
      <section>
        <h3 className="mb-2 text-sm font-bold text-muted">AI 요약</h3>
        <blockquote className="rounded-card-sm border-l-4 border-accent bg-surface px-5 py-4 text-sm leading-relaxed">
          “{report.aiSummary}”
        </blockquote>
      </section>
    </Card>
  )
}

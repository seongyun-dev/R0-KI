import { Card, StatusBadge } from '../../components/ui'
import type { Patrol } from '../../types/domain'

const EVENT_TYPES = ['불법주차', '쓰레기', '위험구역', '응급상황', '침입']

/** PATROL REPORT 블록 (1e) — AI 순찰 보고서 */
export function PatrolReport({ patrol, complexName = '가온아파트' }: { patrol: Patrol; complexName?: string }) {
  const report = patrol.report
  if (!report) return null
  const events = (patrol.points ?? []).filter((p) => EVENT_TYPES.includes(p.type))

  return (
    <Card className="overflow-hidden">
      {/* 보고서 헤더 */}
      <div className="border-b border-line bg-surface px-6 py-5 sm:px-8">
        <p className="font-mono text-xs font-bold tracking-widest text-muted">PATROL REPORT</p>
        <div className="mt-2 flex flex-wrap items-end justify-between gap-3">
          <h2 className="text-lg font-bold">AI 순찰 보고서 — {patrol.id}</h2>
          <dl className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted">
            <div className="flex gap-1.5">
              <dt>보고서번호</dt>
              <dd className="font-mono font-semibold tabular text-fg">{report.reportNo}</dd>
            </div>
            <div className="flex gap-1.5">
              <dt>작성일시</dt>
              <dd className="font-mono tabular text-fg">{report.createdAt}</dd>
            </div>
            <div className="flex gap-1.5">
              <dt>로봇</dt>
              <dd className="font-semibold text-fg">{patrol.robotId} · {complexName}</dd>
            </div>
          </dl>
        </div>
      </div>

      <div className="flex flex-col gap-7 px-6 py-6 sm:px-8">
        {/* AI 요약 */}
        <section>
          <h3 className="mb-2 text-sm font-bold text-muted">AI 요약</h3>
          <blockquote className="rounded-card-sm border-l-4 border-accent bg-surface px-5 py-4 text-sm leading-relaxed">
            “{report.aiSummary}”
          </blockquote>
        </section>

        {/* 주요 탐지 이벤트 */}
        <section>
          <h3 className="mb-2 text-sm font-bold text-muted">주요 탐지 이벤트</h3>
          {events.length > 0 ? (
            <ul className="flex flex-col gap-2">
              {events.map((e, i) => (
                <li key={i} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 rounded-control bg-surface px-4 py-2.5 text-sm">
                  <span className="font-mono font-bold tabular">{e.time}</span>
                  <span className="font-semibold">{e.type}</span>
                  <span className="text-muted">{e.location}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted">탐지된 이벤트가 없습니다</p>
          )}
        </section>

        {/* 이상 징후 코멘트 */}
        {report.anomalyComment && (
          <section>
            <h3 className="mb-2 text-sm font-bold text-muted">이상 징후 코멘트</h3>
            <p className="rounded-control bg-warning-soft px-4 py-3 text-sm leading-relaxed text-fg">
              {report.anomalyComment}
            </p>
          </section>
        )}

        {/* 순찰 지점 기록 */}
        <section>
          <h3 className="mb-2 text-sm font-bold text-muted">순찰 지점 기록</h3>
          <div className="overflow-x-auto">
            <table className="w-full min-w-max text-sm">
              <thead>
                <tr className="border-b border-line text-xs font-semibold text-muted">
                  <th scope="col" className="px-3 py-2 text-left">시간</th>
                  <th scope="col" className="px-3 py-2 text-left">유형</th>
                  <th scope="col" className="px-3 py-2 text-left">위치</th>
                  <th scope="col" className="px-3 py-2 text-left">상태</th>
                  <th scope="col" className="px-3 py-2 text-left">이상 상황</th>
                </tr>
              </thead>
              <tbody>
                {(patrol.points ?? []).map((p, i) => (
                  <tr key={i} className="border-b border-line">
                    <td className="px-3 py-3 font-mono font-semibold tabular">{p.time}</td>
                    <td className="px-3 py-3">{p.type}</td>
                    <td className="px-3 py-3">{p.location}</td>
                    <td className="px-3 py-3"><StatusBadge label={p.status} bracket /></td>
                    <td className="px-3 py-3 text-muted">{p.note ?? '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </Card>
  )
}

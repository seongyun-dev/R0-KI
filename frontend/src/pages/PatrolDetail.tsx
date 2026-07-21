import { useParams } from 'react-router-dom'
import { PageHeader } from '../components/layout/PageHeader'
import { DownloadIcon } from '../components/icons'
import { Button, Card, EmptyState, QueryErrorState, Skeleton, StatusBadge, useToast } from '../components/ui'
import { PatrolReport } from '../features/patrol/PatrolReport'
import { PatrolTimeline } from '../features/patrol/PatrolTimeline'
import { RouteMap } from '../features/patrol/RouteMap'
import { usePatrol } from '../features/patrol/usePatrols'

/** "09:00"~"09:42" → 42 (분) */
function durationMin(start: string, end?: string | null) {
  if (!end) return null
  const [sh, sm] = start.split(':').map(Number)
  const [eh, em] = end.split(':').map(Number)
  return (eh * 60 + em - (sh * 60 + sm) + 1440) % 1440
}

/** 순찰 관리 상세 (1e) — 보고서 형식 */
export default function PatrolDetail() {
  const { id } = useParams()
  const { data: patrol, isLoading, error, refetch } = usePatrol(id)
  const toast = useToast()

  if (isLoading) {
    return (
      <div className="flex flex-col gap-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-72 w-full" />
      </div>
    )
  }
  if (error) {
    return <QueryErrorState error={error} onRetry={refetch} />
  }
  if (!patrol) {
    return (
      <EmptyState
        title="순찰 이력을 찾을 수 없습니다"
        description={`요청한 순찰(${id})이 존재하지 않습니다`}
        action={<Button variant="outline" to="/app/patrol">목록으로</Button>}
      />
    )
  }

  const dur = durationMin(patrol.start, patrol.end)
  const summary: { label: string; value: React.ReactNode }[] = [
    {
      label: '시작 / 종료',
      value: (
        <span className="font-mono tabular">
          {patrol.start} / {patrol.end ?? '-'}
          {dur !== null && <span className="text-muted"> ({dur}분)</span>}
        </span>
      ),
    },
    { label: '경로', value: patrol.routeSummary ?? patrol.routeZones.join('→') },
    {
      label: '배터리',
      value: (
        <span className="font-mono tabular">
          {patrol.batteryFrom ?? '-'}%→{patrol.batteryTo ?? '-'}%
        </span>
      ),
    },
    { label: '상태', value: <StatusBadge label={patrol.status} bracket /> },
  ]

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        breadcrumb={[
          { label: 'Dashboard', to: '/app' },
          { label: '순찰관리', to: '/app/patrol' },
          { label: patrol.id },
        ]}
        title={`순찰 상세 — ${patrol.id} (${patrol.robotId})`}
        actions={
          <>
            <Button variant="accent" size="sm" onClick={() => window.print()}>
              <DownloadIcon />
              PDF 다운로드
            </Button>
            <Button variant="outline" size="sm" onClick={() => toast('✓ 재순찰이 요청되었습니다')}>
              재순찰 요청
            </Button>
          </>
        }
      />

      {/* 요약 */}
      <Card className="p-5 sm:p-6">
        <dl className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4">
          {summary.map((s) => (
            <div key={s.label} className="flex flex-col gap-1">
              <dt className="text-xs font-semibold text-muted">{s.label}</dt>
              <dd className="text-sm font-semibold">{s.value}</dd>
            </div>
          ))}
        </dl>
      </Card>

      {/* 이동 경로 지도 + 순찰 타임라인 */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="p-5 sm:p-6">
          <h2 className="mb-4 text-sm font-bold text-muted">이동 경로 지도</h2>
          <RouteMap zones={patrol.routeZones} />
        </Card>
        <Card className="p-5 sm:p-6">
          <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-sm font-bold text-muted">
              순찰 지점 기록 — 전체 경유지
              {patrol.points && (
                <span className="font-mono tabular">
                  {' '}(이상 {patrol.points.filter((p) => p.eventId).length}건)
                </span>
              )}
            </h2>
            <span className="text-xs text-muted">상태 변경은 이벤트 상세에서 관리</span>
          </div>
          {patrol.points ? (
            <PatrolTimeline points={patrol.points} />
          ) : (
            <p className="text-sm text-muted">기록된 타임라인이 없습니다</p>
          )}
        </Card>
      </div>

      {/* PATROL REPORT */}
      {patrol.report ? (
        <PatrolReport patrol={patrol} />
      ) : (
        <EmptyState title="보고서가 아직 생성되지 않았습니다" description="순찰이 완료되면 AI 보고서가 자동 생성됩니다" />
      )}
    </div>
  )
}

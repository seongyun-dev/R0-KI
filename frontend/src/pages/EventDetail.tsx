import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { PageHeader } from '../components/layout/PageHeader'
import { CameraIcon } from '../components/icons'
import { Button, Card, EmptyState, QueryErrorState, Skeleton, StatusBadge, useToast } from '../components/ui'
import { useEvent, useUpdateEventStatus } from '../features/events/useEvents'
import { useElapsed } from '../lib/useElapsed'
import { cn } from '../lib/cn'
import type { ProcessingStatus } from '../types/domain'

// 처리 상태 — 경비원 관리 3단계 (와이어프레임 v15, 1g·1o)
const PROC_STATUSES: ProcessingStatus[] = ['탐지', '처리중', '처리완료']
const PROC_SELECTED: Record<string, string> = {
  탐지: 'bg-danger text-white ring-danger',
  처리중: 'bg-warning text-white ring-warning',
  처리완료: 'bg-success text-white ring-success',
}

/** 처리 상태 토글 — [탐지][처리중][처리완료] (기본: 탐지) */
function ProcStatusToggle({
  value,
  onChange,
  disabled,
}: {
  value: ProcessingStatus
  onChange: (s: ProcessingStatus) => void
  disabled?: boolean
}) {
  return (
    <div>
      <p className="mb-2 text-xs font-bold tracking-wider text-muted">처리 상태 — 경비원 관리 (기본: 탐지)</p>
      <div className="flex gap-2" role="group" aria-label="처리 상태 변경">
        {PROC_STATUSES.map((s) => (
          <button
            key={s}
            type="button"
            disabled={disabled}
            aria-pressed={value === s}
            onClick={() => onChange(s)}
            className={cn(
              'min-h-10 flex-1 rounded-control text-sm font-bold ring-1 transition-colors',
              value === s ? PROC_SELECTED[s] : 'bg-bg text-muted ring-line hover:bg-surface',
            )}
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  )
}

/** 이벤트 상세 (1g) — 증거 이미지 + 메타 + 인라인 처리 상태. 긴급이면 1o 변형 */
export default function EventDetail() {
  const { id } = useParams()
  const { data: event, isLoading, error, refetch } = useEvent(id)
  const updateStatus = useUpdateEventStatus()
  const toast = useToast()
  // 처리 상태(경비원 관리) — 서버 연동 시 mutation으로 교체
  const [proc, setProc] = useState<ProcessingStatus>('탐지')

  const isEmergency = event?.status === '긴급'

  useEffect(() => {
    if (!event) return
    // 긴급 이벤트는 별도 처리 상태(기본 탐지), 일반 이벤트는 자신의 상태에서 시작
    setProc(event.processingStatus ?? (event.status === '처리중' || event.status === '처리완료' ? event.status : '탐지'))
  }, [event])

  // 1o "경과시간 3분 12초"부터 실시간 카운트
  const elapsed = useElapsed(Boolean(event) && Boolean(isEmergency), 192)

  if (isLoading) {
    return (
      <div className="flex flex-col gap-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="aspect-video w-full max-w-2xl" />
        <Skeleton className="h-40 w-full" />
      </div>
    )
  }
  if (error) {
    return <QueryErrorState error={error} onRetry={refetch} />
  }
  if (!event) {
    return (
      <EmptyState
        title="이벤트를 찾을 수 없습니다"
        description={`요청한 이벤트(${id})가 존재하지 않습니다`}
        action={<Button variant="outline" to="/app/events">목록으로</Button>}
      />
    )
  }

  const changeProc = async (s: ProcessingStatus) => {
    const previous = proc
    setProc(s)
    try {
      await updateStatus.mutateAsync({ eventId: event.backendId ?? event.id, status: s })
      toast(`✓ 처리 상태가 [ ${s} ](으)로 변경되었습니다`)
    } catch (reason) {
      setProc(previous)
      toast(reason instanceof Error ? reason.message : '처리 상태 변경에 실패했습니다')
    }
  }

  // 1o: 유형 "응급상황(쓰러짐 의심)" · 탐지로봇 "(현장 대기중)" · 경과시간 · 처리상태
  const meta: { label: string; value: React.ReactNode }[] = [
    {
      label: '유형',
      value: (
        <span className="font-semibold">
          {event.type}
          {isEmergency && event.subType ? `(${event.subType})` : ''}
        </span>
      ),
    },
    { label: '탐지시각', value: <span className="font-mono tabular">{event.time}</span> },
    { label: '위치', value: event.location },
    {
      label: '탐지로봇',
      value: (
        <span className="font-mono tabular">
          {event.robotId}
          {isEmergency && <span className="font-sans text-muted"> (현장 대기중)</span>}
        </span>
      ),
    },
    { label: '신뢰도', value: <span className="font-mono tabular">{event.confidence ?? '-'}%</span> },
    ...(isEmergency
      ? [{ label: '경과시간', value: <span className="font-mono tabular text-danger">{elapsed}</span> }]
      : []),
    { label: '처리상태', value: <StatusBadge label={proc} bracket /> },
  ]

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        breadcrumb={[
          { label: 'Dashboard', to: '/app' },
          { label: '이벤트관리', to: '/app/events' },
          { label: event.id },
        ]}
        title={isEmergency ? `⚠ 긴급 이벤트 상세 — ${event.id}` : `이벤트 상세 — ${event.id}`}
        aside={isEmergency ? <StatusBadge label="긴급 · 즉시 확인 필요" bracket /> : undefined}
      />

      {/* 긴급 판단 사유 (1o) */}
      {isEmergency && event.emergencyReason && (
        <div className="rounded-card-sm bg-danger-soft px-5 py-4 text-sm leading-relaxed ring-1 ring-danger/30">
          <span className="font-bold text-danger">긴급 판단 사유: </span>
          {event.emergencyReason}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        {/* 증거 이미지 (로봇 카메라 캡처) */}
        <Card tone="dark" className="overflow-hidden">
          <div className="relative flex aspect-video flex-col items-center justify-center gap-3">
            {event.evidenceImageUrl ? (
              <img src={event.evidenceImageUrl} alt={`${event.type} 증거 이미지`} className="h-full w-full object-cover" />
            ) : (
              <>
                <CameraIcon className="text-4xl text-subtle" />
                <p className="text-sm font-semibold text-subtle">
                  {isEmergency
                    ? `[ ${event.robotId} 현장 이미지 · ${event.time} 수신 ]`
                    : '증거 이미지 (로봇 카메라 캡처)'}
                </p>
              </>
            )}
            {/* 카메라 오버레이 */}
            <div className="absolute left-4 top-4 flex items-center gap-2 font-mono text-xs text-white/80">
              <span aria-hidden className="h-2 w-2 animate-pulse rounded-pill bg-danger" />
              REC · {event.robotId}
            </div>
            <div className="absolute bottom-4 right-4 font-mono text-xs tabular text-white/80">
              2026/07/15 {event.time}
            </div>
          </div>
        </Card>

        {/* 메타 */}
        <Card className="p-5 sm:p-6">
          <dl className="flex flex-col divide-y divide-line">
            {meta.map((m) => (
              <div key={m.label} className="flex items-center justify-between gap-4 py-3 first:pt-0 last:pb-0">
                <dt className="text-sm text-muted">{m.label}</dt>
                <dd className="text-sm">{m.value}</dd>
              </div>
            ))}
          </dl>
          {event.memo && (
            <div className="mt-4 rounded-control bg-surface px-4 py-3">
              <p className="text-xs font-semibold text-muted">처리 메모</p>
              <p className="mt-1 text-sm">{event.memo}</p>
            </div>
          )}

          {/* 처리 상태 — 경비원 관리 (1g·1o 인라인 토글) */}
          <div className={cn('mt-5 border-t pt-5', isEmergency ? 'border-danger/30' : 'border-line')}>
            <ProcStatusToggle
              value={proc}
              onChange={(status) => void changeProc(status)}
              disabled={updateStatus.isPending}
            />
          </div>

          {/* 긴급 액션 (1o): 보안 출동 요청 · 입주민 긴급알림 발송 */}
          {isEmergency && (
            <div className="mt-4 flex flex-col gap-2">
              <Button variant="dark" className="w-full bg-danger" onClick={() => toast('✓ 보안팀 출동이 요청되었습니다')}>
                보안 출동 요청
              </Button>
              <Button variant="outline" className="w-full" onClick={() => toast('✓ 입주민 긴급알림이 발송되었습니다')}>
                입주민 긴급알림 발송
              </Button>
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}

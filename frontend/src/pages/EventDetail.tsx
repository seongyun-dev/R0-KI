import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useParams } from 'react-router-dom'
import { PageHeader } from '../components/layout/PageHeader'
import { CameraIcon } from '../components/icons'
import {
  Button,
  Card,
  EmptyState,
  Field,
  Modal,
  QueryErrorState,
  Skeleton,
  StatusBadge,
  Textarea,
  useToast,
} from '../components/ui'
import { useEvent, useUpdateEventStatus } from '../features/events/useEvents'
import { useElapsed } from '../lib/useElapsed'
import { cn } from '../lib/cn'
import type { ProcessingStatus } from '../types/domain'

// 처리 상태 — 경비원 관리 3단계 (와이어프레임 v15, 1g)
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

/** 이벤트 상세 (1g) — 증거 이미지 + 메타 + 인라인 처리 상태 */
export default function EventDetail() {
  const { id } = useParams()
  const { data: event, isLoading, error, refetch } = useEvent(id)
  const updateStatus = useUpdateEventStatus()
  const toast = useToast()
  // 처리 상태(경비원 관리) — 서버 연동 시 mutation으로 교체
  const [proc, setProc] = useState<ProcessingStatus>('탐지')
  const [memo, setMemo] = useState<string>()
  const [processedAt, setProcessedAt] = useState<string>()
  // 처리완료 시 처리 메모 입력 모달
  const [memoModalOpen, setMemoModalOpen] = useState(false)
  const [memoInput, setMemoInput] = useState('')

  useEffect(() => {
    if (!event) return
    setProc(event.processingStatus ?? (event.status === '처리중' || event.status === '처리완료' ? event.status : '탐지'))
    setMemo(event.memo)
    setProcessedAt(event.processedAt)
  }, [event])

  // 경과시간 — 탐지/처리중일 때만 실시간 카운트. 메모 모달이 열려 있는 동안은 멈춤
  // (1초마다 재렌더되면 모달 포커스가 튕겨 메모 입력이 방해됨)
  const isOngoing = proc === '탐지' || proc === '처리중'
  // 경과시간 기준 = 탐지시각(occurredAt)부터 지금까지 (백엔드 실데이터 반영)
  const baseSec = useMemo(() => {
    if (!event?.occurredAt) return 0
    const s = Math.floor((Date.now() - Date.parse(event.occurredAt)) / 1000)
    return Number.isFinite(s) && s > 0 ? s : 0
  }, [event?.occurredAt])
  const elapsed = useElapsed(Boolean(event) && isOngoing && !memoModalOpen, baseSec)

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

  const changeProc = async (s: ProcessingStatus, note?: string) => {
    const previous = proc
    setProc(s)
    if (note !== undefined) setMemo(note)
    // 처리완료로 바뀌면 완료 시각 기록
    if (s === '처리완료') setProcessedAt((prev) => prev ?? new Date().toTimeString().slice(0, 5))
    try {
      await updateStatus.mutateAsync({ eventId: event.backendId ?? event.id, status: s, note })
      toast(s === '처리완료' ? '✓ 처리 완료되었습니다.' : `✓ 처리 상태가 [ ${s} ](으)로 변경되었습니다`)
    } catch (reason) {
      setProc(previous)
      toast(reason instanceof Error ? reason.message : '처리 상태 변경에 실패했습니다')
    }
  }

  // 처리완료 선택 시엔 바로 변경하지 않고 메모 입력 모달을 연다
  const onProcChange = (s: ProcessingStatus) => {
    if (s === '처리완료') {
      setMemoInput(memo ?? '')
      setMemoModalOpen(true)
      return
    }
    void changeProc(s)
  }

  const confirmComplete = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setMemoModalOpen(false)
    // 처리 메모는 선택 입력 — 비워도 완료 가능
    void changeProc('처리완료', memoInput.trim() || undefined)
  }

  const meta: { label: string; value: React.ReactNode }[] = [
    { label: '유형', value: <span className="font-semibold">{event.type}{event.subType ? `(${event.subType})` : ''}</span> },
    { label: '탐지시각', value: <span className="font-mono tabular">{event.time}</span> },
    { label: '위치', value: event.location },
    { label: '탐지로봇', value: <span className="font-mono tabular">{event.robotId}</span> },
    { label: '신뢰도', value: <span className="font-mono tabular">{event.confidence ?? '-'}%</span> },
    ...(isOngoing
      ? [{ label: '경과시간', value: <span className="font-mono tabular">{elapsed}</span> }]
      : []),
    ...(proc === '처리완료' && processedAt
      ? [{ label: '처리시간', value: <span className="font-mono tabular">{processedAt}</span> }]
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
        title={`이벤트 상세 — ${event.id}`}
      />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        {/* 증거 이미지 (로봇 카메라 캡처) */}
        <Card tone="dark" className="overflow-hidden">
          <div className="relative flex aspect-video flex-col items-center justify-center gap-3">
            {event.evidenceImageUrl ? (
              <img src={event.evidenceImageUrl} alt={`${event.type} 증거 이미지`} className="h-full w-full object-cover" />
            ) : (
              <>
                <CameraIcon className="text-4xl text-subtle" />
                <p className="text-sm font-semibold text-subtle">증거 이미지 (로봇 카메라 캡처)</p>
              </>
            )}
            {/* 카메라 오버레이 */}
            <div className="absolute left-4 top-4 flex items-center gap-2 font-mono text-xs text-white/80">
              <span aria-hidden className="h-2 w-2 animate-pulse rounded-pill bg-danger" />
              REC · {event.robotId}
            </div>
            <div className="absolute bottom-4 right-4 font-mono text-xs tabular text-white/80">
              {event.occurredAt
                ? `${new Intl.DateTimeFormat('sv-SE').format(new Date(event.occurredAt)).replace(/-/g, '/')} `
                : ''}
              {event.time}
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

          {/* 처리 메모 — 완료 후 재표시 */}
          {proc === '처리완료' && memo && (
            <div className="mt-4 rounded-control bg-surface px-4 py-3">
              <p className="text-xs font-semibold text-muted">처리 메모</p>
              <p className="mt-1 text-sm">{memo}</p>
            </div>
          )}

          {/* 처리 상태 — 경비원 관리 (인라인 토글) */}
          <div className="mt-5 border-t border-line pt-5">
            {/* 처리완료 후에는 되돌릴 수 없음 → 토글 비활성화 */}
            <ProcStatusToggle
              value={proc}
              onChange={onProcChange}
              disabled={updateStatus.isPending || proc === '처리완료'}
            />
          </div>
        </Card>
      </div>

      {/* 처리 완료 메모 입력 모달 */}
      <Modal open={memoModalOpen} onClose={() => setMemoModalOpen(false)} title="처리 완료">
        <form className="flex flex-col gap-4" onSubmit={confirmComplete}>
          <Field label="처리 메모" htmlFor="proc-memo" hint="선택 입력 — 비워도 완료할 수 있어요">
            <Textarea
              id="proc-memo"
              value={memoInput}
              onChange={(e) => setMemoInput(e.target.value)}
              rows={4}
              placeholder="처리 내용을 남겨주세요 (예: 경비팀 현장 확인·조치 완료)"
              autoFocus
            />
          </Field>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setMemoModalOpen(false)}>취소</Button>
            <Button type="submit" variant="dark">완료 처리</Button>
          </div>
        </form>
      </Modal>
    </div>
  )
}

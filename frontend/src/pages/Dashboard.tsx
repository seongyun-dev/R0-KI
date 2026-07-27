import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { PageHeader } from '../components/layout/PageHeader'
import { BotIcon } from '../components/icons'
import { Card, QueryErrorState, Skeleton, StatusBadge } from '../components/ui'
import { ComplexMap } from '../features/dashboard/ComplexMap'
import { EmergencyAlertModal } from '../features/dashboard/EmergencyAlertModal'
import { useComplexMap } from '../features/dashboard/useComplexMap'
import { useEmergencyAlert, isEmergencySeen, markEmergencySeen } from '../features/dashboard/useEmergencyAlert'
import { useEvents } from '../features/events/useEvents'
import { BatteryBar } from '../features/robots/BatteryBar'
import { useRobots } from '../features/robots/useRobot'
import { cn } from '../lib/cn'
import type { PatrolEvent } from '../types/domain'

/** 대시보드 (1c) — 실시간 지도 + 최근 이벤트(긴급만) + 로봇 상태 요약. 긴급 발생 시 알림 모달(1c+) */
export default function Dashboard() {
  const navigate = useNavigate()
  const {
    data: events,
    isLoading: eventsLoading,
    error: eventsError,
    refetch: refetchEvents,
  } = useEvents()
  const {
    data: robots,
    isLoading: robotsLoading,
    error: robotsError,
    refetch: refetchRobots,
  } = useRobots()
  const {
    data: mapData,
    isLoading: mapLoading,
    error: mapError,
    refetch: refetchMap,
  } = useComplexMap()
  // 최근 이벤트 카드 — 긴급을 최상단, 그 아래 처리된(과거) 이벤트 순
  // (백엔드: 긴급만 활성 이벤트로 저장, 나머지는 순찰 완료 후 처리된 이력)
  const recentEvents = [...(events ?? [])].sort(
    (a, b) => (a.riskLevel === '긴급' ? 0 : 1) - (b.riskLevel === '긴급' ? 0 : 1),
  )

  // 긴급 알림 — 진입 시 목록을 훑지 않고, 백엔드 push(목업은 시뮬레이션)로 도착할 때만 띄운다
  const [alertEvent, setAlertEvent] = useState<PatrolEvent | null>(null)
  useEmergencyAlert((event) => {
    if (!isEmergencySeen(event.id)) setAlertEvent(event)
  })

  const dismissAlert = () => {
    if (alertEvent) markEmergencySeen(alertEvent.id)
    setAlertEvent(null)
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader breadcrumb={[{ label: 'Dashboard' }]} title="대시보드" />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        {/* 실시간 지도 */}
        <Card className="p-5 sm:p-6">
          <div className="mb-4 flex items-center justify-between gap-3">
            <h2 className="text-sm font-bold text-muted">실시간 지도</h2>
            <Link
              to="/app/map"
              className="text-sm font-semibold text-accent underline-offset-4 hover:underline"
            >
              ⤢ 지도 확대 보기
            </Link>
          </div>
          {mapError ? (
            <QueryErrorState error={mapError} onRetry={refetchMap} className="aspect-[2/1]" />
          ) : mapLoading || !mapData ? (
            <Skeleton className="aspect-[2/1] w-full rounded-card-sm" />
          ) : (
            <ComplexMap map={mapData.map} robot={mapData.robot} pins={mapData.pins} />
          )}
        </Card>

        {/* 최근 이벤트 — 긴급만 (1c) */}
        <Card className="flex flex-col p-5 sm:p-6">
          <div className="mb-4 flex items-center justify-between gap-3">
            <h2 className="text-sm font-bold text-muted">최근 이벤트</h2>
          </div>
          {eventsError ? (
            <QueryErrorState error={eventsError} onRetry={refetchEvents} />
          ) : eventsLoading ? (
            <div className="flex flex-col gap-3">
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
            </div>
          ) : (
            <div className="flex flex-col gap-2.5">
              {recentEvents.map((e) => (
                <Link
                  key={e.id}
                  to={`/app/events/${e.id}`}
                  className={cn(
                    'block rounded-control px-4 py-3 ring-1 transition-colors',
                    e.riskLevel === '긴급' ? 'bg-danger-soft/60 ring-danger hover:bg-danger-soft' : 'bg-bg ring-line hover:bg-surface',
                  )}
                >
                  <div className="mb-1 flex items-center justify-between gap-3">
                    <span className="text-sm font-bold">
                      {e.type}
                      {e.subType ? ` · ${e.subType}` : ''}
                    </span>
                    <StatusBadge label={e.riskLevel === '긴급' ? '긴급' : e.status} bracket className="flex-none" />
                  </div>
                  <p className="text-xs text-muted">
                    <span className="font-mono tabular">{e.time}</span> · {e.location} ·{' '}
                    <span className="font-mono tabular">{e.robotId}</span>
                  </p>
                </Link>
              ))}
            </div>
          )}
          <Link
            to="/app/events"
            className="mt-auto pt-3 text-sm font-semibold text-accent underline-offset-4 hover:underline"
          >
            전체 이벤트 →
          </Link>
        </Card>
      </div>

      {/* 로봇 상태 요약 (1c) */}
      <Card className="p-5 sm:p-6">
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="text-sm font-bold text-muted">로봇 상태 요약</h2>
          <Link to="/app/robots" className="text-sm font-semibold text-accent underline-offset-4 hover:underline">
            로봇 관리 →
          </Link>
        </div>
        {robotsError ? (
          <QueryErrorState error={robotsError} onRetry={refetchRobots} />
        ) : robotsLoading ? (
          <div className="grid gap-3 sm:grid-cols-3">
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-3">
            {(robots ?? []).map((r) => (
              <Link
                key={r.id}
                to={`/app/robots/${r.id}`}
                className="flex items-center gap-3.5 rounded-card-sm p-4 ring-1 ring-line transition-colors hover:bg-surface"
              >
                <BotIcon className="flex-none text-4xl text-muted" aria-hidden />
                <div className="min-w-0 flex-1">
                  <div className="mb-1.5 flex items-center justify-between gap-2">
                    <span className="font-mono text-sm font-bold tabular">{r.id}</span>
                    <StatusBadge label={r.status} bracket className="flex-none" />
                  </div>
                  <BatteryBar value={r.battery} warning={r.status === '충전중'} />
                  <p className="mt-1.5 truncate text-xs text-muted">
                    {r.location}
                    {r.status === '순찰중' ? ' 순찰중' : r.status === '대기' ? ' 대기' : ''}
                  </p>
                </div>
              </Link>
            ))}
          </div>
        )}
      </Card>

      {/* 긴급 알림 모달 (1c+) — push 도착 시에만 표시 */}
      {alertEvent && (
        <EmergencyAlertModal
          open={Boolean(alertEvent)}
          event={alertEvent}
          onClose={dismissAlert}
          onConfirm={() => {
            const id = alertEvent.id
            dismissAlert()
            navigate(`/app/events/${id}`)
          }}
        />
      )}
    </div>
  )
}

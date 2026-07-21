import { Suspense, lazy, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { CameraIcon, CloseIcon } from '../components/icons'
import { Button, QueryErrorState, Skeleton, useToast } from '../components/ui'
import { useComplexMap } from '../features/dashboard/useComplexMap'
import { useEvents } from '../features/events/useEvents'
import { useElapsed } from '../lib/useElapsed'
import type { PatrolEvent } from '../types/domain'

// 3D 라이브 씬(three.js) — 진입 시 지연 로드
const MapLiveScene = lazy(() => import('../features/dashboard/MapLiveScene'))

/** 긴급 알림 패널 (1h) — 빨간 포인트 클릭 시 표시 */
function EmergencyPanel({ event, onClose }: { event: PatrolEvent; onClose: () => void }) {
  const navigate = useNavigate()
  const toast = useToast()
  const elapsed = useElapsed(true, 192)

  return (
    <aside
      aria-label="긴급 알림"
      className="absolute right-4 top-4 z-10 flex w-80 max-w-[calc(100%-2rem)] flex-col gap-4 rounded-card-sm bg-card p-5 shadow-pop ring-2 ring-danger"
    >
      <div className="flex items-center justify-between gap-3">
        <span className="inline-flex items-center gap-2 font-mono text-xs font-bold tracking-widest text-danger">
          <span aria-hidden className="h-2 w-2 animate-pulse rounded-pill bg-danger" />
          [ 긴급 알림 ]
        </span>
        <button
          type="button"
          onClick={onClose}
          aria-label="긴급 알림 패널 닫기"
          className="grid h-7 w-7 place-items-center rounded-pill text-subtle hover:bg-white/10 hover:text-white"
        >
          <CloseIcon />
        </button>
      </div>

      <h2 className="text-base font-bold text-white">
        {event.type} {event.subType ? `(${event.subType})` : ''}
      </h2>

      <dl className="flex flex-col gap-1.5 text-sm text-subtle">
        <div>위치: <span className="font-semibold text-white">{event.location}</span></div>
        <div>
          탐지시각: <span className="font-mono tabular text-white">{event.time}</span> · 경과{' '}
          <span className="font-mono tabular text-danger">{elapsed}</span>
        </div>
        <div>탐지로봇: <span className="font-mono tabular text-white">{event.robotId}</span> (현장 대기중)</div>
        <div>신뢰도: <span className="font-mono font-bold tabular text-white">{event.confidence}%</span></div>
      </dl>

      {/* 현장 스냅샷 */}
      <div className="flex h-28 flex-col items-center justify-center gap-1.5 rounded-control bg-white/5 ring-1 ring-white/10">
        <CameraIcon className="text-xl text-subtle" />
        <p className="text-xs text-subtle">현장 스냅샷 ({event.robotId} 전송)</p>
      </div>

      <div className="flex flex-col gap-2">
        <Button variant="light" size="sm" className="w-full" onClick={() => navigate(`/app/events/${event.id}`)}>
          긴급 이벤트 상세 보기 →
        </Button>
        <Button variant="dark" size="sm" className="w-full bg-danger" onClick={() => toast('✓ 보안팀 출동이 요청되었습니다')}>
          보안 출동 요청
        </Button>
      </div>
    </aside>
  )
}

/** 지도 확대 보기 (1h) — 지도 전용 풀스크린. 3D 로봇이 체크포인트 경로를 실시간 순찰 */
export default function MapFull() {
  const navigate = useNavigate()
  const { data: mapData, isLoading, error, refetch } = useComplexMap()
  const { data: events } = useEvents()
  const [panelOpen, setPanelOpen] = useState(false)

  const emergency = (events ?? []).find((e) => e.status === '긴급')

  return (
    <div className="fixed inset-0 z-40 flex flex-col bg-ink text-white">
      {/* 상단 바 */}
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-4 py-3.5 sm:px-6">
        <span className="font-mono text-xs font-bold tracking-widest text-accent-light">
          [ LIVE MAP · 체크포인트 + 이동 경로 ]
        </span>
        <span className="inline-flex items-center gap-2 rounded-pill bg-white/10 px-3 py-1 font-mono text-xs text-subtle">
          <span aria-hidden className="h-1.5 w-1.5 rounded-pill bg-online" />
          [ 실시간 연결됨 ]
        </span>
        <button
          type="button"
          onClick={() => navigate('/app')}
          className="inline-flex items-center gap-1.5 rounded-control px-3 py-2 text-sm font-semibold text-subtle transition-colors hover:bg-white/10 hover:text-white"
        >
          <CloseIcon />
          닫고 대시보드로
        </button>
      </header>

      {/* 3D 라이브 맵 */}
      <div className="relative min-h-0 flex-1">
        {error ? (
          <div className="m-6">
            <QueryErrorState error={error} onRetry={refetch} />
          </div>
        ) : isLoading || !mapData ? (
          <Skeleton className="m-6 h-[calc(100%-3rem)] rounded-card-sm bg-white/5" />
        ) : (
          <Suspense fallback={<Skeleton className="m-6 h-[calc(100%-3rem)] rounded-card-sm bg-white/5" />}>
            <MapLiveScene
              map={mapData.map}
              checkpoints={mapData.checkpoints}
              pins={mapData.pins}
              onEmergencyClick={() => setPanelOpen(true)}
              className="h-full w-full"
            />
          </Suspense>
        )}

        {/* 로봇 상태 칩 */}
        {mapData && (
          <span className="pointer-events-none absolute left-4 top-4 inline-flex items-center gap-2 rounded-pill bg-white/10 px-3.5 py-1.5 font-mono text-xs font-bold text-white backdrop-blur sm:left-6 sm:top-5">
            🤖 {mapData.robot.id} · 순찰중
          </span>
        )}

        {/* 긴급 포인트 칩 — 3D 핀과 동일 동작(키보드 접근 겸용) */}
        {emergency && !panelOpen && (
          <button
            type="button"
            onClick={() => setPanelOpen(true)}
            className="absolute bottom-5 left-4 inline-flex items-center gap-2 rounded-pill bg-danger-soft/15 px-3.5 py-2 font-mono text-xs font-bold text-danger ring-1 ring-danger/60 backdrop-blur transition-colors hover:bg-danger/20 sm:left-6"
          >
            <span aria-hidden className="h-2 w-2 animate-pulse rounded-pill bg-danger" />
            [ 긴급 · {emergency.location} ] ← 클릭
          </button>
        )}

        {panelOpen && emergency && <EmergencyPanel event={emergency} onClose={() => setPanelOpen(false)} />}
      </div>
    </div>
  )
}

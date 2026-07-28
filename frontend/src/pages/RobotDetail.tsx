import { Suspense, lazy, useState, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { PageHeader } from '../components/layout/PageHeader'
import { PlusIcon } from '../components/icons'
import { Button, Card, EmptyState, QueryErrorState, Skeleton, StatusBadge, useToast } from '../components/ui'
import { RobotEditDrawer } from '../features/robots/RobotEditDrawer'
import { useDeleteRobot, useRobot, useUpdateRobot } from '../features/robots/useRobot'
import { usePatrols } from '../features/patrol/usePatrols'
import { cn } from '../lib/cn'
import type { Robot } from '../types/domain'

// three.js 청크 분리 — 상세 진입 시 지연 로드
const RobotDiagnosticView = lazy(() =>
  import('../components/robot/RobotDiagnosticView').then((m) => ({ default: m.RobotDiagnosticView })),
)

function SectionCard({ title, children, className }: { title: string; children: ReactNode; className?: string }) {
  return (
    <Card compact className={cn('p-5', className)}>
      <h2 className="mb-3 text-sm font-bold text-muted">{title}</h2>
      {children}
    </Card>
  )
}

function DescList({ items }: { items: { label: string; value: ReactNode }[] }) {
  return (
    <dl className="flex flex-col divide-y divide-line">
      {items.map((it) => (
        <div key={it.label} className="flex items-center justify-between gap-3 py-2 first:pt-0 last:pb-0">
          <dt className="text-sm text-muted">{it.label}</dt>
          <dd className="text-right text-sm font-semibold">{it.value}</dd>
        </div>
      ))}
    </dl>
  )
}

/* LIVE DIAGNOSTICS 패널 — 부품 상태를 로봇 주변 네 모서리에 주석으로 배치 (와이어프레임 1i 중앙) */
const PART_CORNERS = [
  'left-5 top-14 items-start text-left',
  'right-5 top-14 items-end text-right',
  'left-5 bottom-14 items-start text-left',
  'right-5 bottom-14 items-end text-right',
]

/** 로봇 관리 상세 (1i) — R-01. 좌(프로필) | 중앙(LIVE DIAGNOSTICS) | 우(리포트·기록) */
export default function RobotDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const robotId = id ?? 'R-01'
  const { data: loaded, isLoading, error, refetch } = useRobot(robotId)
  const { data: patrols } = usePatrols()
  const toast = useToast()
  const updateRobot = useUpdateRobot()
  const deleteRobot = useDeleteRobot()
  const [drawerOpen, setDrawerOpen] = useState(false)
  // 수정 드로어 저장 결과(목업 — 서버 연동 시 mutation으로 교체)
  const [patch, setPatch] = useState<Partial<Robot> | null>(null)

  if (isLoading) {
    return (
      <div className="flex flex-col gap-6">
        <Skeleton className="h-8 w-64" />
        <div className="grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)_280px]">
          <Skeleton className="h-96 w-full" />
          <Skeleton className="h-[480px] w-full" />
          <Skeleton className="h-96 w-full" />
        </div>
      </div>
    )
  }
  if (error) {
    return <QueryErrorState error={error} onRetry={refetch} />
  }
  if (!loaded) {
    return (
      <EmptyState
        title="로봇을 찾을 수 없습니다"
        description={`요청한 로봇(${robotId})이 존재하지 않습니다`}
        action={<Button variant="outline" to="/app/robots">로봇 관리로</Button>}
      />
    )
  }

  const robot: Robot = { ...loaded, ...patch }
  const recent = (patrols ?? []).filter((p) => p.robotId === robot.id).slice(0, 3)

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        breadcrumb={[
          { label: 'Dashboard', to: '/app' },
          { label: '로봇 관리', to: '/app/robots' },
          { label: robot.id },
        ]}
        title={`로봇 관리 — ${robot.id}`}
        aside={<StatusBadge label={robot.status} bracket />}
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => setDrawerOpen(true)}>수정</Button>
            <Button variant="accent" size="sm" to="/app/robots/new">
              <PlusIcon />
              로봇 등록
            </Button>
          </>
        }
      />

      {/* 와이어프레임 1i: 260px | 1fr | 280px 3컬럼 */}
      <div className="grid items-start gap-4 lg:grid-cols-[260px_minmax(0,1fr)_280px]">
        {/* ── 좌측: 프로필 ── */}
        <div className="flex flex-col gap-4">
          <SectionCard title="로봇 프로필">
            <DescList
              items={[
                { label: '로봇명', value: <span className="font-mono tabular">{robot.name}</span> },
                { label: '등록번호', value: <span className="font-mono tabular">{robot.registrationNo}</span> },
                { label: '도입일', value: <span className="font-mono tabular">{robot.introducedAt}</span> },
              ]}
            />
          </SectionCard>
        </div>

        {/* ── 중앙: LIVE DIAGNOSTICS — 로봇 주변 네 모서리에 부품 상태 주석 (흰 배경) ── */}
        <Card className="relative min-h-[480px] overflow-hidden">
          <span className="absolute left-5 top-5 z-10 font-mono text-xs font-bold tracking-widest text-accent">
            [ LIVE DIAGNOSTICS ]
          </span>
          <span className="absolute bottom-5 right-5 z-10 font-mono text-xs text-muted">
            {robot.id} · 정면 45°
          </span>

          {robot.parts.slice(0, 4).map((part, i) => (
            <div
              key={part.name}
              className={cn('pointer-events-none absolute z-10 flex flex-col gap-1', PART_CORNERS[i])}
            >
              <span className="text-xs font-semibold text-muted">{part.name}</span>
              <StatusBadge label={part.status} bracket />
            </div>
          ))}

          <Suspense fallback={null}>
            <RobotDiagnosticView className="absolute inset-0" />
          </Suspense>
        </Card>

        {/* ── 우측: 상태 리포트 · 최근 순찰 기록 ── */}
        <div className="flex flex-col gap-4">
          <SectionCard title="상태 리포트">
            <DescList
              items={[
                { label: '현재 상태', value: <StatusBadge label={robot.status} bracket /> },
                { label: '배터리 잔량', value: <span className="font-mono tabular">{robot.battery}%</span> },
                // 누적 주행: 로봇 x,y 위치 로그 기반 이동거리 합산 / 가동률: 가동·정지 시간 비율
                { label: '누적 주행', value: <span className="font-mono tabular">{robot.odometerKm ?? '-'}km</span> },
                { label: '이번 주 가동률', value: <span className="font-mono tabular">{robot.weeklyUptime ?? '-'}%</span> },
              ]}
            />
          </SectionCard>

          <SectionCard title="최근 순찰 기록">
            <ul className="flex flex-col divide-y divide-line">
              {recent.map((p) => {
                // 경로 대신 해당 순찰에서 탐지된 이벤트 건수만 표시
                const eventText = p.eventCount > 0 ? `이벤트 ${p.eventCount}건` : '탐지 이벤트 없음'
                return (
                  <li key={p.id} className="flex items-center justify-between gap-2 py-2.5 first:pt-0">
                    <div className="flex min-w-0 flex-col gap-0.5">
                      <span className="font-mono text-sm font-semibold tabular">
                        {p.start}–{p.end ?? ''}
                      </span>
                      <span className="truncate text-xs text-muted">{eventText}</span>
                    </div>
                    <StatusBadge label={p.status} bracket className="flex-none" />
                  </li>
                )
              })}
            </ul>
            <Link
              to="/app/patrol"
              className="mt-3 inline-block text-sm font-semibold text-accent underline-offset-4 hover:underline"
            >
              전체 이력 →
            </Link>
          </SectionCard>
        </div>
      </div>

      <RobotEditDrawer
        open={drawerOpen}
        robot={robot}
        onClose={() => setDrawerOpen(false)}
        onSave={async ({ name }) => {
          try {
            await updateRobot.mutateAsync({
              robotId: robot.backendId ?? robot.id,
              robotName: name,
            })
            setPatch({ name })
            toast('✓ 저장되었습니다')
          } catch (reason) {
            toast(reason instanceof Error ? reason.message : '로봇 수정에 실패했습니다')
            throw reason
          }
        }}
        onDelete={async () => {
          try {
            await deleteRobot.mutateAsync({ robotId: robot.backendId ?? robot.id })
            toast('✓ 로봇이 삭제되었습니다')
            navigate('/app/robots')
          } catch (reason) {
            toast(reason instanceof Error ? reason.message : '로봇 삭제에 실패했습니다')
            throw reason
          }
        }}
      />
    </div>
  )
}

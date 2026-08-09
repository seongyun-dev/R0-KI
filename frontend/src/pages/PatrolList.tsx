import { useState } from 'react'
import { Link } from 'react-router-dom'
import { PageHeader } from '../components/layout/PageHeader'
import {
  Button,
  Card,
  DataTable,
  Select,
  QueryErrorState,
  type Column,
} from '../components/ui'
import { useRobot } from '../features/robots/useRobot'
import { usePatrols } from '../features/patrol/usePatrols'
import type { Patrol } from '../types/domain'
import { env } from '../config/env'
import { useAuthStore } from '../features/auth/useAuthStore'

const columns: Column<Patrol>[] = [
  { key: 'id', header: '순찰ID', render: (p) => <span className="font-mono font-bold tabular">{p.id}</span> },
  { key: 'start', header: '시작', render: (p) => <span className="font-mono tabular">{p.date} {p.start}</span> },
  { key: 'end', header: '종료', render: (p) => <span className="font-mono tabular">{p.end ?? '-'}</span> },
  { key: 'route', header: '순찰 경로 (구역 순서)', render: (p) => <span className="text-muted">{p.routeZones.join(' → ')}</span> },
  { key: 'events', header: '이벤트', render: (p) => <span className="font-mono tabular">{p.eventCount}</span>, align: 'right' },
  {
    key: 'detail',
    header: '',
    align: 'right',
    render: (p) => (
      <Link to={`/app/patrol/${p.id}`} className="font-semibold text-accent underline-offset-4 hover:underline">
        상세 →
      </Link>
    ),
  },
]

/** 순찰 관리 목록 (1d) — 순찰 이력 R-01 */
export default function PatrolList() {
  const sessionRobotId = useAuthStore((state) => state.robotId)
  const selectedRobotId = env.useMocks ? 'R-01' : sessionRobotId ?? env.defaultRobotId
  const { data: robot } = useRobot(selectedRobotId)
  const [period, setPeriod] = useState('all')
  const [status, setStatus] = useState('all')
  const [applied, setApplied] = useState({ period: 'all', status: 'all' })
  const { data: patrols, isLoading, error, refetch } = usePatrols({
    robotId: selectedRobotId,
    period: applied.period,
    status: applied.status,
  })

  const rows = patrols ?? []

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        breadcrumb={[{ label: 'Dashboard', to: '/app' }, { label: '순찰관리' }]}
        title={`순찰 이력 — ${robot?.name ?? selectedRobotId ?? '로봇'}`}
        aside={
          robot && (
            <span className="inline-flex items-center gap-1.5 rounded-pill bg-success-soft px-3 py-1 text-xs font-semibold text-success">
              [ {robot.status} · 배터리 <span className="font-mono tabular">{robot.battery}%</span> ]
            </span>
          )
        }
      />

      <Card className="p-5 sm:p-6">
        {/* 필터바 */}
        <form
          className="mb-4 flex flex-wrap items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            setApplied({ period, status })
          }}
        >
          <Select aria-label="기간 선택" value={period} onChange={(e) => setPeriod(e.target.value)} className="w-40">
            <option value="all">기간 전체</option>
            <option value="today">오늘</option>
            <option value="7d">최근 7일</option>
            <option value="30d">최근 30일</option>
          </Select>
          <Select aria-label="상태" value={status} onChange={(e) => setStatus(e.target.value)} className="w-32">
            <option value="all">상태 전체</option>
            <option value="완료">완료</option>
            <option value="진행중">진행중</option>
          </Select>
          <Button type="submit" variant="dark" size="sm">검색</Button>
        </form>

        {error ? (
          <QueryErrorState error={error} onRetry={refetch} />
        ) : (
          <DataTable
            columns={columns}
            rows={rows}
            rowKey={(p) => p.id}
            loading={isLoading}
            emptyMessage="조건에 맞는 순찰 이력이 없습니다"
          />
        )}
      </Card>
    </div>
  )
}

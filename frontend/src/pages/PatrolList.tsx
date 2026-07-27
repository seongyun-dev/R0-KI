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
import { useRobots } from '../features/robots/useRobot'
import { usePatrols } from '../features/patrol/usePatrols'
import type { Patrol } from '../types/domain'
import { env } from '../config/env'
import { useAuthStore } from '../features/auth/useAuthStore'

/** 순찰 관리 목록 (1d) — 순찰 이력 */
export default function PatrolList() {
  const sessionRobotId = useAuthStore((state) => state.robotId)
  const selectedRobotId = env.useMocks ? 'R-01' : sessionRobotId ?? env.defaultRobotId
  const { data: robots } = useRobots()
  const [period, setPeriod] = useState('all')
  const [applied, setApplied] = useState({ period: 'all' })
  const { data: patrols, isLoading, error, refetch } = usePatrols({
    robotId: selectedRobotId,
    period: applied.period,
  })

  // 완료된 순찰만 기록/표시 (진행중 등 제외)
  const rows = (patrols ?? []).filter((p) => p.status === '완료')
  // 로봇 이름 조회 (사용자 지정 이름 반영) — 서버 응답의 robotName 우선, 없으면 목록에서 조회
  const nameById = new Map((robots ?? []).map((r) => [r.id, r.name]))

  const columns: Column<Patrol>[] = [
    { key: 'id', header: '순찰ID', render: (p) => <span className="font-mono font-bold tabular">{p.id}</span> },
    {
      key: 'robot',
      header: '로봇',
      render: (p) => <span className="font-semibold">{p.robotName ?? nameById.get(p.robotId) ?? p.robotId}</span>,
    },
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

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        breadcrumb={[{ label: 'Dashboard', to: '/app' }, { label: '순찰관리' }]}
        title="순찰 이력"
      />

      <Card className="p-5 sm:p-6">
        {/* 필터바 — 기간만 (상태는 완료 순찰만 기록하므로 제거) */}
        <form
          className="mb-4 flex flex-wrap items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            setApplied({ period })
          }}
        >
          <Select aria-label="기간 선택" value={period} onChange={(e) => setPeriod(e.target.value)} className="w-40">
            <option value="all">기간 전체</option>
            <option value="today">오늘</option>
            <option value="7d">최근 7일</option>
            <option value="30d">최근 30일</option>
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

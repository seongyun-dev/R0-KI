import { useState } from 'react'
import { Link } from 'react-router-dom'
import { PageHeader } from '../components/layout/PageHeader'
import { PlusIcon } from '../components/icons'
import { Button, Card, DataTable, QueryErrorState, StatusBadge, useToast, type Column } from '../components/ui'
import { BatteryBar } from '../features/robots/BatteryBar'
import { RobotEditDrawer } from '../features/robots/RobotEditDrawer'
import { useDeleteRobot, useRobots, useRobotStats, useUpdateRobot } from '../features/robots/useRobot'
import type { Robot } from '../types/domain'

/** 로봇 관리 목록 (1i) — KPI + 로봇 테이블. 상세는 1i-r01(/app/robots/:id) */
export default function RobotList() {
  const { data: robots, isLoading, error, refetch } = useRobots()
  const { data: stats } = useRobotStats()
  const toast = useToast()
  const updateRobot = useUpdateRobot()
  const deleteRobot = useDeleteRobot()
  const [editing, setEditing] = useState<Robot | null>(null)
  // 수정 드로어 저장 결과(목업 — 서버 연동 시 mutation으로 교체)
  const [patches, setPatches] = useState<Record<string, Partial<Robot>>>({})

  const rows = (robots ?? []).map((r) => ({ ...r, ...patches[r.id] }))

  // KPI는 단지 전체 현황 통계(GET /api/robots/stats) 기준. 목록은 페이지네이션되므로 rows로 계산하지 않는다.
  const kpis = [
    { label: '전체 로봇', value: stats?.totalCount ?? rows.length, cls: '' },
    { label: '순찰중', value: stats?.patrollingCount ?? 0, cls: 'text-success' },
    { label: '대기 · 충전중', value: stats?.idleOrChargingCount ?? 0, cls: 'text-muted' },
  ]

  const columns: Column<Robot>[] = [
    { key: 'name', header: '로봇명', render: (r) => <span className="font-mono font-bold tabular">{r.name}</span> },
    { key: 'status', header: '상태', render: (r) => <StatusBadge label={r.status} bracket /> },
    {
      key: 'battery',
      header: '배터리',
      render: (r) => <BatteryBar value={r.battery} warning={r.status === '충전중'} />,
    },
    { key: 'location', header: '현재 위치', render: (r) => r.location ?? '-' },
    {
      key: 'lastPatrol',
      header: '최근 순찰',
      render: (r) => <span className="font-mono tabular">{r.lastPatrol ?? '-'}</span>,
    },
    {
      key: 'actions',
      header: '',
      align: 'right',
      render: (r) => (
        <span className="inline-flex items-center gap-3">
          <Link
            to={`/app/robots/${r.id}`}
            className="font-semibold text-accent underline-offset-4 hover:underline"
          >
            상세 →
          </Link>
          <button
            type="button"
            className="font-semibold text-muted underline-offset-4 hover:underline"
            onClick={() => setEditing(r)}
          >
            수정
          </button>
        </span>
      ),
    },
  ]

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        breadcrumb={[{ label: 'Dashboard', to: '/app' }, { label: '로봇 관리' }]}
        title="로봇 목록"
        actions={
          <Button variant="accent" size="sm" to="/app/robots/new">
            <PlusIcon />
            로봇 등록
          </Button>
        }
      />

      {/* KPI (1i): 전체 로봇 / 순찰중 / 대기·충전중 */}
      <div className="grid gap-4 sm:grid-cols-3">
        {kpis.map((k) => (
          <Card compact className="p-5" key={k.label}>
            <p className="text-xs font-bold tracking-wider text-muted">{k.label}</p>
            <p className={`mt-1.5 font-mono text-2xl font-bold tabular ${k.cls}`}>{k.value}</p>
          </Card>
        ))}
      </div>

      <Card className="p-5 sm:p-6">
        {error ? (
          <QueryErrorState error={error} onRetry={refetch} />
        ) : (
          <DataTable
            columns={columns}
            rows={rows}
            rowKey={(r) => r.id}
            loading={isLoading}
            emptyMessage="등록된 로봇이 없습니다"
          />
        )}
      </Card>

      {editing && (
        <RobotEditDrawer
          open={Boolean(editing)}
          robot={{ ...editing, ...patches[editing.id] }}
          onClose={() => setEditing(null)}
          onSave={async ({ name }) => {
            try {
              await updateRobot.mutateAsync({
                robotId: editing.backendId ?? editing.id,
                robotName: name,
              })
              setPatches((prev) => ({ ...prev, [editing.id]: { name } }))
              toast('✓ 저장되었습니다')
            } catch (reason) {
              toast(reason instanceof Error ? reason.message : '로봇 수정에 실패했습니다')
              throw reason
            }
          }}
          onDelete={async () => {
            try {
              await deleteRobot.mutateAsync({ robotId: editing.backendId ?? editing.id })
              toast('✓ 로봇이 삭제되었습니다')
              refetch()
            } catch (reason) {
              toast(reason instanceof Error ? reason.message : '로봇 삭제에 실패했습니다')
              throw reason
            }
          }}
        />
      )}
    </div>
  )
}

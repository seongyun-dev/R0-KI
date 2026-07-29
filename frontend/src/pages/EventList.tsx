import { useState } from 'react'
import { Link } from 'react-router-dom'
import { PageHeader } from '../components/layout/PageHeader'
import {
  Button,
  Card,
  DataTable,
  Select,
  StatusBadge,
  QueryErrorState,
  type Column,
} from '../components/ui'
import { useEvents } from '../features/events/useEvents'
import type { PatrolEvent } from '../types/domain'
import type {
  EventListRequest,
  EventPeriodCode,
  EventTypeCode,
  ProcessingStatusCode,
  RiskLevelCode,
} from '../api/contracts'
// 담당자는 처리중/처리완료일 때만 표시 (백엔드 제공)
const hasAssignee = (e: PatrolEvent) => e.status === '처리중' || e.status === '처리완료'

const columns: Column<PatrolEvent>[] = [
  { key: 'id', header: 'ID', render: (e) => <span className="font-mono font-bold tabular">{e.id}</span> },
  { key: 'time', header: '시간', render: (e) => <span className="font-mono tabular">{e.time}</span> },
  { key: 'type', header: '유형', render: (e) => <span className="font-semibold">{e.type}</span> },
  { key: 'location', header: '위치', render: (e) => e.location },
  { key: 'robot', header: '로봇', render: (e) => <span className="font-mono tabular">{e.robotId}</span> },
  { key: 'risk', header: '위험도', render: (e) => (e.riskLevel ? <StatusBadge label={e.riskLevel} bracket /> : '—') },
  { key: 'status', header: '상태', render: (e) => <StatusBadge label={e.status} bracket /> },
  { key: 'assignee', header: '담당자', render: (e) => (hasAssignee(e) ? (e.assignee ?? '-') : '—') },
  {
    key: 'detail',
    header: '',
    align: 'right',
    render: (e) => (
      <Link to={`/app/events/${e.id}`} className="font-semibold text-accent underline-offset-4 hover:underline">
        상세 →
      </Link>
    ),
  },
]

/** 이벤트 관리 목록 (1f) */
export default function EventList() {
  const [type, setType] = useState<EventTypeCode | ''>('')
  const [status, setStatus] = useState<ProcessingStatusCode | ''>('')
  const [period, setPeriod] = useState<EventPeriodCode | ''>('')
  const [risk, setRisk] = useState<RiskLevelCode | ''>('')
  const [applied, setApplied] = useState<EventListRequest>({ period: 'ALL', page: 0, size: 10, sort: ['occurredAt,DESC']})
  const { data: events, isLoading, error, refetch } = useEvents(applied)

  const rows = events ?? []

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        breadcrumb={[{ label: 'Dashboard', to: '/app' }, { label: '이벤트관리' }]}
        title="이벤트 목록"
      />

      <Card className="p-5 sm:p-6">
        {/* 필터: 유형 ▾ / 위험도 ▾ / 상태 ▾ / 기간 ▾ / [검색] */}
        <form
          className="mb-4 flex flex-wrap items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault()

            setApplied({
              ...(type ? { type } : {}),
              ...(status ? { status } : {}),
              // ...(risk ? { risk } : {}),
              ...(period ? { period } : {}),
              page: 0,
              size: 10,
              sort: ['occurredAt,DESC'],
            })
          }}
        >
          <Select aria-label="유형" value={type} onChange={(e) => setType(e.target.value as EventTypeCode | '')} className="w-36">
            <option value="">유형 전체</option>
            <option value="EMERGENCY">응급상황</option>
            <option value="ILLEGAL_PARKING">불법주차</option>
            <option value="UNREGISTERED_VEHICLE">미등록 차량</option>
            <option value="TRASH_DETECTED">쓰레기</option>
            <option value="RECYCLING_AREA_FULL">분리수거장</option>
          </Select>
          <Select aria-label="위험도" value={risk} onChange={(e) => setRisk(e.target.value as RiskLevelCode | '')} className="w-32">
            <option value="all">위험도 전체</option>
            <option value="EMERGENCY">긴급</option>
            <option value="NORMAL">보통</option>
            <option value="LOW">낮음</option>
          </Select>
          <Select aria-label="상태" value={status} onChange={(e) => setStatus(e.target.value as ProcessingStatusCode | '')} className="w-32">
            <option value="all">상태 전체</option>
            <option value="DETECTED">탐지</option>
            <option value="PROCESSING">처리중</option>
            <option value="COMPLETED">처리완료</option>
          </Select>
          <Select aria-label="기간" value={period} onChange={(e) => setPeriod(e.target.value as EventPeriodCode | '')} className="w-36">
            <option value="ALL">기간 전체</option>
            <option value="TODAY">오늘</option>
            <option value="LAST_7_DAYS">최근 7일</option>
          </Select>
          <Button type="submit" variant="dark" size="sm">검색</Button>
        </form>

        {error ? (
          <QueryErrorState error={error} onRetry={refetch} />
        ) : (
          <DataTable
            columns={columns}
            rows={rows}
            rowKey={(e) => e.id}
            loading={isLoading}
            emptyMessage="조건에 맞는 이벤트가 없습니다"
          />
        )}
      </Card>
    </div>
  )
}

import { useState } from 'react'
import { PageHeader } from '../components/layout/PageHeader'
import { DownloadIcon } from '../components/icons'
import { Button, Card, QueryErrorState, Select, Skeleton, StatTile, useToast } from '../components/ui'
import { AiInsights } from '../features/stats/AiInsights'
import { EventTrendChart } from '../features/stats/EventTrendChart'
import { HandlingChart } from '../features/stats/HandlingChart'
import { HourlyTypeChart } from '../features/stats/HourlyTypeChart'
import { ZonePieChart } from '../features/stats/ZonePieChart'
import { useStats } from '../features/stats/useStats'
import { downloadCsv } from '../lib/downloadCsv'

/** 통계 대시보드 (1m) — KPI 4 + 추이 + 시간대별 + 처리 현황 + 구역 비율 + AI 인사이트 */
export default function Stats() {
  const toast = useToast()
  const [period, setPeriod] = useState('month')
  const [zone, setZone] = useState('all')
  const { data, isLoading, error, refetch } = useStats({ period, zone })

  const onExport = () => {
    if (!data) return
    const rows: (string | number)[][] = [
      ['구분', '항목', '값'],
      ['KPI', '총 순찰 횟수', data.summary.totalPatrols],
      ['KPI', '총 이벤트', data.summary.totalEvents],
      ['KPI', '평균 처리시간(분)', data.summary.avgHandleMin],
      ['KPI', '가동률(%)', data.summary.uptime],
      [],
      ['일자별 이벤트 추이', '일자', '건수'],
      ...data.daily.map((d) => ['', d.date, d.count]),
      [],
      ['시간대별 이벤트(유형별)', '시간대', '주차', '쓰레기', '위험구역'],
      ...data.hourly.map((h) => ['', h.slot, h.주차, h.쓰레기, h.위험구역]),
      [],
      ['처리 현황', '항목', '처리(건)', '미처리(건)', '처리율(%)'],
      ...data.handling.map((h) => ['', h.label, h.handled, h.pending, h.handledPct]),
      [],
      ['구역별 이벤트 비율', '구역', '건수', '비율(%)'],
      ...data.zones.map((z) => ['', z.zone, z.count, z.pct]),
      [],
      ['AI 인사이트', '내용'],
      ...data.insights.map((t) => ['', t]),
    ]
    downloadCsv('patrol-stats.csv', rows)
    toast('✓ CSV를 내보냈습니다')
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        breadcrumb={[{ label: 'Dashboard', to: '/app' }, { label: '통계' }]}
        title="기간별 통계 & 인사이트"
        actions={
          <>
            <Select aria-label="기간" value={period} onChange={(e) => setPeriod(e.target.value)} className="w-32">
              <option value="month">이번 달</option>
              <option value="week">이번 주</option>
              <option value="quarter">이번 분기</option>
            </Select>
            <Select aria-label="구역" value={zone} onChange={(e) => setZone(e.target.value)} className="w-36">
              <option value="all">구역: 전체</option>
              <option value="parking">구역: 주차장</option>
              <option value="recycle">구역: 분리수거장</option>
              <option value="danger">구역: 위험구역</option>
            </Select>
            <Button variant="outline" size="sm" onClick={onExport} disabled={!data}>
              <DownloadIcon />
              CSV 내보내기
            </Button>
          </>
        }
      />

      {error && <QueryErrorState error={error} onRetry={refetch} />}

      {/* KPI 카드 4 */}
      {!error && (isLoading || !data) ? (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-28 w-full rounded-card-sm" />
          ))}
        </div>
      ) : !error && data ? (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatTile
            value={`${data.summary.totalPatrols}회`}
            label="총 순찰 횟수"
            delta={{ text: data.summary.deltas?.patrols ?? '', direction: 'up' }}
          />
          <StatTile
            value={`${data.summary.totalEvents}건`}
            label="총 이벤트"
            delta={{ text: data.summary.deltas?.events ?? '', direction: 'up' }}
          />
          <StatTile
            value={`${data.summary.avgHandleMin}분`}
            label="평균 처리시간"
            delta={{ text: data.summary.deltas?.handle ?? '', direction: 'down' }}
          />
          <StatTile
            value={`${data.summary.uptime}%`}
            label="가동률"
            delta={{ text: data.summary.deltas?.uptime ?? '', direction: 'neutral' }}
            tone="dark"
          />
        </div>
      ) : null}

      {/* 일자별 추이 · 시간대별 유형별 */}
      {!error && <div className="grid gap-6 xl:grid-cols-2">
        <Card className="p-5 sm:p-6">
          {isLoading || !data ? <Skeleton className="h-72 w-full" /> : <EventTrendChart data={data.daily} />}
        </Card>
        <Card className="p-5 sm:p-6">
          {isLoading || !data ? <Skeleton className="h-72 w-full" /> : <HourlyTypeChart data={data.hourly} />}
        </Card>
      </div>}

      {/* 처리 현황 · 구역별 비율 */}
      {!error && <div className="grid gap-6 xl:grid-cols-2">
        <Card className="p-5 sm:p-6">
          {isLoading || !data ? <Skeleton className="h-64 w-full" /> : <HandlingChart data={data.handling} />}
        </Card>
        <Card className="p-5 sm:p-6">
          {isLoading || !data ? <Skeleton className="h-64 w-full" /> : <ZonePieChart data={data.zones} />}
        </Card>
      </div>}

      {/* AI 인사이트 */}
      {!error && (isLoading || !data ? <Skeleton className="h-40 w-full rounded-card" /> : <AiInsights insights={data.insights} />)}
    </div>
  )
}

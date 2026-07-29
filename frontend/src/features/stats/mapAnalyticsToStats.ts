/**
 * 백엔드 Analytics 응답 → Stats 화면용 StatsResponse 매퍼.
 *
 * 역할:
 * - 여러 API(overview / trend×2 / handling / by-zone) 결과를
 *   기존 Stats.tsx 가 기대하는 { summary, daily, hourly, handling, zones, insights } 로 합친다.
 * - 화면(KPI 카드·차트 컴포넌트) 디자인은 건드리지 않고, 필드 이름·단위만 맞춘다.
 *
 * 연결:
 * - overview → summary (총 순찰/이벤트/평균 처리시간 + deltas)
 * - trend?bucket=day → daily (일자별 추이)
 * - trend?bucket=hour3 → hourly (3시간×8칸, 주차/쓰레기 묶음)
 * - handling → handling (처리/미처리)
 * - by-zone → zones (파이차트, pct는 여기서 계산)
 * - insights → 빈 배열 (AI API 제외, 레이아웃만 유지)
 */

import type {
  AnalyticsByZoneResponse,
  AnalyticsDecimalDelta,
  AnalyticsHandlingResponse,
  AnalyticsIntDelta,
  AnalyticsOverviewResponse,
  AnalyticsTrendResponse,
} from '../../api/analyticsContracts'
import type {
  AiInsight,
  DailyEventStat,
  HandlingStat,
  HourlyEventStat,
  StatSummary,
  ZoneShareStat,
} from '../../types/domain'

/** Stats 페이지가 쓰는 합본 응답 (useStats 반환 형태) */
export type StatsDashboardData = {
  summary: StatSummary
  daily: DailyEventStat[]
  hourly: HourlyEventStat[]
  handling: HandlingStat[]
  zones: ZoneShareStat[]
  insights: (string | AiInsight)[]
}

/** 백엔드 EventType → 프론트 시간대 차트 시리즈(주차/쓰레기) */
const PARKING_TYPES = new Set(['ILLEGAL_PARKING', 'UNREGISTERED_VEHICLE'])
const TRASH_TYPES = new Set(['TRASH_DETECTED', 'RECYCLING_AREA_FULL'])

/** hour3 슬롯 라벨 (백엔드 0시·3시·…·21시 시작과 1:1) */
const HOUR3_SLOT_LABELS = [
  '0-3시',
  '3-6시',
  '6-9시',
  '9-12시',
  '12-15시',
  '15-18시',
  '18-21시',
  '21-24시',
] as const

function num(value: unknown, fallback = 0) {
  const n = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(n) ? n : fallback
}

/** "이전 대비 +12.5%" 형태. rate가 0이면 그대로 표기 */
function formatRateDelta(delta: AnalyticsIntDelta | null | undefined, suffix = '%') {
  if (!delta) return undefined
  const rate = num(delta.changeRate)
  const sign = rate > 0 ? '+' : ''
  return `이전 대비 ${sign}${rate}${suffix}`
}

/** 평균 처리시간 증감 — 분 단위 diff를 문구로 */
function formatHandleDelta(delta: AnalyticsDecimalDelta | null | undefined) {
  if (!delta || delta.diff == null) return undefined
  const diff = num(delta.diff)
  const sign = diff > 0 ? '+' : ''
  return `이전 대비 ${sign}${diff}분`
}

/** LocalDateTime 문자열 → MM/DD (일자별 차트 X축) */
function toMonthDay(bucketStart: string) {
  // "2026-07-01T00:00:00" 또는 offset 포함 모두 앞 10자로 날짜 파싱
  const datePart = bucketStart.slice(0, 10)
  const [, m, d] = datePart.split('-')
  if (!m || !d) return bucketStart
  return `${m}/${d}`
}

/** overview → KPI summary */
export function mapOverviewToSummary(overview: AnalyticsOverviewResponse): StatSummary {
  const avg = overview.totals.avgHandleMin
  return {
    totalPatrols: num(overview.totals.patrolCount),
    totalEvents: num(overview.totals.totalCount),
    // 대상 없으면 0으로 표시 (카드 자리는 유지)
    avgHandleMin: avg == null ? 0 : Math.round(num(avg)),
    uptime: 0, // 백엔드 미제공 — CSV/타입 호환용 placeholder
    deltas: {
      patrols: formatRateDelta(overview.delta.patrol),
      events: formatRateDelta(overview.delta.total),
      handle: formatHandleDelta(overview.delta.handleTime),
    },
  }
}

/** trend(day) → 일자별 추이 */
export function mapTrendToDaily(trend: AnalyticsTrendResponse): DailyEventStat[] {
  return trend.series.map((item) => ({
    date: toMonthDay(item.bucketStart),
    count: num(item.totalCount),
  }))
}

/**
 * trend(hour3) → 시간대별 유형 차트.
 * byType enum을 주차/쓰레기로 합산. (위험/EMERGENCY는 시안과 같이 제외)
 * series가 비거나 8칸 미만이어도 라벨 8칸을 채워 차트가 깨지지 않게 한다.
 */
export function mapTrendToHourly(trend: AnalyticsTrendResponse): HourlyEventStat[] {
  const byHour = new Map<number, { 주차: number; 쓰레기: number }>()

  for (const item of trend.series) {
    const hour = Number(item.bucketStart.slice(11, 13))
    const slotIndex = Number.isFinite(hour) ? Math.floor(hour / 3) : 0
    let parking = 0
    let trash = 0
    for (const [type, count] of Object.entries(item.byType ?? {})) {
      const c = num(count)
      if (PARKING_TYPES.has(type)) parking += c
      else if (TRASH_TYPES.has(type)) trash += c
    }
    const prev = byHour.get(slotIndex) ?? { 주차: 0, 쓰레기: 0 }
    byHour.set(slotIndex, { 주차: prev.주차 + parking, 쓰레기: prev.쓰레기 + trash })
  }

  return HOUR3_SLOT_LABELS.map((slot, index) => {
    const counts = byHour.get(index) ?? { 주차: 0, 쓰레기: 0 }
    return { slot, 주차: counts.주차, 쓰레기: counts.쓰레기 }
  })
}

/** handling → 처리 현황 차트 (비율은 정수 %로 반올림해 라벨이 시안과 비슷하게) */
export function mapHandling(response: AnalyticsHandlingResponse): HandlingStat[] {
  return (response.items ?? []).map((item) => ({
    label: item.label,
    handled: num(item.handled),
    pending: num(item.pending),
    handledPct: Math.round(num(item.handledPct)),
    pendingPct: Math.round(num(item.pendingPct)),
  }))
}

/** by-zone → 파이차트. pct = eventCount / 합계 * 100 */
export function mapZones(response: AnalyticsByZoneResponse): ZoneShareStat[] {
  const items = response.items ?? []
  const total = items.reduce((sum, z) => sum + num(z.eventCount), 0)
  return items.map((z) => {
    const count = num(z.eventCount)
    const pct = total === 0 ? 0 : Math.round((count * 100) / total)
    return {
      zone: z.zoneName || `구역 ${z.zoneId}`,
      count,
      pct,
    }
  })
}

/** 5개 API 결과를 Stats 대시보드 한 덩어리로 조립 */
export function assembleStatsDashboard(parts: {
  overview: AnalyticsOverviewResponse
  dailyTrend: AnalyticsTrendResponse
  hourlyTrend: AnalyticsTrendResponse
  handling: AnalyticsHandlingResponse
  byZone: AnalyticsByZoneResponse
}): StatsDashboardData {
  return {
    summary: mapOverviewToSummary(parts.overview),
    daily: mapTrendToDaily(parts.dailyTrend),
    hourly: mapTrendToHourly(parts.hourlyTrend),
    handling: mapHandling(parts.handling),
    zones: mapZones(parts.byZone),
    // AI 인사이트 API는 이번 연동 범위 밖 — 패널은 유지하되 목록은 비움
    insights: [],
  }
}

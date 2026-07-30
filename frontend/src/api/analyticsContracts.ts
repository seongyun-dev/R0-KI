/**
 * 백엔드 Analytics API 응답 계약.
 *
 * 연결 대상 (워크트리 back …-261):
 * - GET /api/analytics/events/overview
 * - GET /api/analytics/events/trend
 * - GET /api/analytics/events/handling
 * - GET /api/analytics/events/by-zone
 * - GET /api/analytics/insights
 *
 * 공통 래퍼 { success, code, message, data }는 apiRequest가 data만 꺼내 주므로
 * 여기 타입은 data 본문만 정의한다.
 */

/** overview — KPI + 최다 항목 + 증감 */
export type AnalyticsOverviewResponse = {
  period: { from: string; to: string; timezone: string }
  totals: {
    totalCount: number
    todayCount: number
    /** COMPLETED 순찰 수 */
    patrolCount: number
    /** 평균 처리시간(분). 대상 없으면 null */
    avgHandleMin: number | null
  }
  top: {
    eventType: string | null
    zone: { zoneId: number; zoneName: string } | null
  }
  delta: {
    total: AnalyticsIntDelta
    patrol: AnalyticsIntDelta
    handleTime: AnalyticsDecimalDelta | null
    byType: unknown[]
  }
}

export type AnalyticsIntDelta = {
  current: number
  previous: number
  diff: number
  changeRate: number
}

export type AnalyticsDecimalDelta = {
  current: number | null
  previous: number | null
  diff: number | null
  changeRate: number | null
}

/** trend — day/week/month 시계열 또는 hour3 시각대 */
export type AnalyticsTrendResponse = {
  bucket: 'day' | 'week' | 'month' | 'hour3'
  series: AnalyticsTrendBucket[]
}

export type AnalyticsTrendBucket = {
  bucketStart: string
  bucketEnd: string
  totalCount: number
  /** EventType enum → 건수. 없는 키는 생략될 수 있음 */
  byType: Record<string, number>
  byStatus: Record<string, number>
}

/** handling — 처리/미처리 현황 */
export type AnalyticsHandlingResponse = {
  items: AnalyticsHandlingItem[]
}

export type AnalyticsHandlingItem = {
  label: string
  handled: number
  pending: number
  handledPct: number
  pendingPct: number
}

/** by-zone — 구역(checkpoint_id)별 건수 */
export type AnalyticsByZoneResponse = {
  items: AnalyticsByZoneItem[]
  topZone: { zoneId: number; zoneName: string; eventCount: number } | null
}

export type AnalyticsByZoneItem = {
  zoneId: number
  zoneName: string
  eventCount: number
  patrolCount: number
  eventRatePerPatrol: number | null
  topEventType: string | null
}

/** insights — 직전 완료 주/월 AI 리포트 */
export type AnalyticsInsightPeriodType = 'WEEK' | 'MONTH'

export type AnalyticsInsightGenerationStatus =
  | 'PENDING'
  | 'PROCESSING'
  | 'COMPLETED'
  | 'FAILED'

export type AnalyticsInsightResponse = {
  insightId: number
  periodType: AnalyticsInsightPeriodType
  periodKey: string
  periodFrom: string
  periodTo: string
  timezone: string
  generationStatus: AnalyticsInsightGenerationStatus
  /** COMPLETED 일 때만 채워짐. 마크다운 본문 */
  insightContent: string | null
}

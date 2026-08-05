import type {
  AiInsight,
  DailyEventStat,
  HandlingStat,
  HourlyEventStat,
  StatSummary,
  ZoneShareStat,
} from '../types/domain'
import type {
  AnalyticsInsightPeriodType,
  AnalyticsInsightResponse,
} from '../api/analyticsContracts'

/** LLM 인사이트 목업과 공유하는 핵심 수치 */
export const MOCK_INSIGHT_TOTAL_EVENTS = 83
export const MOCK_INSIGHT_HANDLED = 59
export const MOCK_INSIGHT_PENDING = 24
export const MOCK_INSIGHT_ILLEGAL_PARKING = 24
export const MOCK_INSIGHT_TRASH = 18
export const MOCK_INSIGHT_B2_PENDING_PARKING = 3

export const MOCK_INSIGHT_ZONES: ZoneShareStat[] = [
  { zone: '지하주차장 B2', count: 35, pct: 42 },
  { zone: '101동', count: 22, pct: 27 },
  { zone: '103동 화단', count: 14, pct: 17 },
  { zone: '102동', count: 12, pct: 14 },
]

// 통계 대시보드 목업 — mockAnalyticsInsight() 수치와 동일
export const statSummary: StatSummary = {
  totalPatrols: 142,
  totalEvents: MOCK_INSIGHT_TOTAL_EVENTS,
  avgHandleMin: 12,
  uptime: 94,
  deltas: {
    patrols: '전주 대비 +8%',
    events: '전주 대비 +15%',
    handle: '전주 대비 -3분',
    uptime: '목표 90% 초과',
  },
}

// 일자별 이벤트 추이 — 합계 83건 (07/15 6건 · 전일 대비 -4건 ▼)
export const dailyEvents: DailyEventStat[] = [
  { date: '07/01', count: 3 },
  { date: '07/02', count: 5 },
  { date: '07/03', count: 4 },
  { date: '07/04', count: 6 },
  { date: '07/05', count: 2 },
  { date: '07/06', count: 7 },
  { date: '07/07', count: 5 },
  { date: '07/08', count: 8 },
  { date: '07/09', count: 6 },
  { date: '07/10', count: 4 },
  { date: '07/11', count: 8 },
  { date: '07/12', count: 7 },
  { date: '07/13', count: 5 },
  { date: '07/14', count: 6 },
  { date: '07/15', count: 7 },
]

/* 시간대별 — 주차 24건 · 쓰레기 18건 (인사이트 유형별 건수와 일치) */
export const hourlyEvents: HourlyEventStat[] = [
  { slot: '0-3시', 주차: 1, 쓰레기: 1 },
  { slot: '3-6시', 주차: 1, 쓰레기: 1 },
  { slot: '6-9시', 주차: 2, 쓰레기: 2 },
  { slot: '9-12시', 주차: 3, 쓰레기: 3 },
  { slot: '12-15시', 주차: 4, 쓰레기: 2 },
  { slot: '15-18시', 주차: 6, 쓰레기: 4 },
  { slot: '18-21시', 주차: 5, 쓰레기: 3 },
  { slot: '21-24시', 주차: 2, 쓰레기: 2 },
]

// 처리 현황 — 전체 83건 = 처리 59 + 미처리 24
export const handlingStats: HandlingStat[] = [
  {
    label: '전체',
    handled: MOCK_INSIGHT_HANDLED,
    pending: MOCK_INSIGHT_PENDING,
    handledPct: 71,
    pendingPct: 29,
  },
  {
    label: '주차',
    handled: 18,
    pending: 6,
    handledPct: 75,
    pendingPct: 25,
  },
  {
    label: '쓰레기',
    handled: 14,
    pending: 4,
    handledPct: 78,
    pendingPct: 22,
  },
]

export const zoneShares: ZoneShareStat[] = MOCK_INSIGHT_ZONES

// 레거시 카드형 인사이트 (목업 모드 useStats 반환용)
export const aiInsights: AiInsight[] = [
  {
    title: '한눈에 보기',
    body: `지난 기간 총 ${MOCK_INSIGHT_TOTAL_EVENTS}건의 이벤트가 탐지되었고, 지하주차장 B2에서 발생이 가장 많았습니다.`,
    action: 'B2 구역 순찰 빈도 상향',
  },
  {
    title: '어떤 일이 많았나',
    body: `불법주차 ${MOCK_INSIGHT_ILLEGAL_PARKING}건, 쓰레기 적치 ${MOCK_INSIGHT_TRASH}건 순이었습니다.`,
    action: '주차·쓰레기 집중 구역 확인',
  },
  {
    title: '지금 할 일',
    body: `B2 구역 미처리 불법주차 ${MOCK_INSIGHT_B2_PENDING_PARKING}건을 우선 확인하세요.`,
    action: '미처리 이벤트 점검',
  },
]

/** AI 인사이트 API 목업 — 마크다운 리포트 본문 */
export function mockAnalyticsInsight(
  periodType: AnalyticsInsightPeriodType,
): AnalyticsInsightResponse {
  const isWeek = periodType === 'WEEK'
  return {
    insightId: 1,
    periodType,
    periodKey: isWeek ? '2026-W29' : '2026-06',
    periodFrom: isWeek ? '2026-07-14T00:00:00' : '2026-06-01T00:00:00',
    periodTo: isWeek ? '2026-07-20T23:59:59' : '2026-06-30T23:59:59',
    timezone: 'Asia/Seoul',
    generationStatus: 'COMPLETED',
    insightContent: [
      '## 한눈에 보기',
      `- 지난 ${isWeek ? '주' : '달'} 총 ${MOCK_INSIGHT_TOTAL_EVENTS}건의 이벤트가 탐지되었습니다.`,
      '- 지하주차장 B2에서 발생이 가장 많았습니다.',
      '',
      '## 어떤 일이 많았나',
      `- 불법주차 ${MOCK_INSIGHT_ILLEGAL_PARKING}건으로 가장 많았습니다.`,
      `- 쓰레기 적치 ${MOCK_INSIGHT_TRASH}건이 이어졌습니다.`,
      '',
      '## 어디를 더 보면 좋은가',
      '- 지하주차장 B2 — 불법주차가 반복됩니다.',
      '- 101동 앞 — 저녁 시간대 이벤트가 집중됩니다.',
      '',
      '## 처리 상태',
      `- 전체 ${MOCK_INSIGHT_TOTAL_EVENTS}건 중 ${MOCK_INSIGHT_HANDLED}건 처리, ${MOCK_INSIGHT_PENDING}건 미처리입니다.`,
      '',
      '## 지금 할 일',
      `- B2 구역 미처리 불법주차 ${MOCK_INSIGHT_B2_PENDING_PARKING}건을 우선 확인하세요.`,
    ].join('\n'),
  }
}

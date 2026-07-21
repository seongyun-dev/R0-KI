import type {
  DailyEventStat,
  HandlingStat,
  HourlyEventStat,
  StatSummary,
  ZoneShareStat,
} from '../types/domain'

// 와이어프레임 1m (통계 대시보드) 값 그대로
export const statSummary: StatSummary = {
  totalPatrols: 142,
  totalEvents: 83,
  avgHandleMin: 12,
  uptime: 94,
  deltas: {
    patrols: '전주 대비 +8%',
    events: '전주 대비 +15%',
    handle: '전주 대비 -3분',
    uptime: '목표 90% 초과',
  },
}

// 일자별 이벤트 추이 07/01~07/15 — 07/15 6건 · 전일 대비 -4건 ▼
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
  { date: '07/11', count: 9 },
  { date: '07/12', count: 7 },
  { date: '07/13', count: 5 },
  { date: '07/14', count: 10 },
  { date: '07/15', count: 6 },
]

/* 시간대별 이벤트 발생(유형별 누적) — 구간별 합계는 와이어프레임 값 그대로
   (6 / 9 / 17 / 13 / 20 / 15 / 9). 유형별 분해는 합계에 맞춘 목업. */
export const hourlyEvents: HourlyEventStat[] = [
  { slot: '0-6시', 주차: 2, 쓰레기: 1, 위험구역: 3 },
  { slot: '6-9시', 주차: 5, 쓰레기: 3, 위험구역: 1 },
  { slot: '9-12시', 주차: 9, 쓰레기: 5, 위험구역: 3 },
  { slot: '12-15시', 주차: 6, 쓰레기: 5, 위험구역: 2 },
  { slot: '15-18시', 주차: 11, 쓰레기: 6, 위험구역: 3 },
  { slot: '18-21시', 주차: 8, 쓰레기: 4, 위험구역: 3 },
  { slot: '21-24시', 주차: 3, 쓰레기: 2, 위험구역: 4 },
]

// 처리 현황 (100% 기준) — 전체 83건 = 처리 59 + 미처리 24
export const handlingStats: HandlingStat[] = [
  { label: '전체', handled: 59, pending: 24, handledPct: 71, pendingPct: 29 },
  { label: '주차', handled: 34, pending: 12, handledPct: 74, pendingPct: 26 },
  { label: '쓰레기', handled: 20, pending: 8, handledPct: 71, pendingPct: 29 },
  { label: '위험구역', handled: 5, pending: 4, handledPct: 56, pendingPct: 44 },
]

// 구역별 이벤트 비율 (파이차트) — 합계 21건
export const zoneShares: ZoneShareStat[] = [
  { zone: '지하주차장 B2', count: 9, pct: 42 },
  { zone: '101동', count: 5, pct: 26 },
  { zone: '103동 화단', count: 4, pct: 21 },
  { zone: '102동', count: 3, pct: 11 },
]

// AI 인사이트 (1m)
export const aiInsights: string[] = [
  '지하주차장 B2 구역 불법주차가 최근 2주간 지속 증가(전주 대비 +40%), 해당 구역 순찰 빈도 상향 권장',
  'R-01 좌측 휠 모터 점검 필요 — 배터리 효율 저하 감지',
]

import type {
  AiInsight,
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

/* 시간대별 이벤트 — 백엔드 hour3(3시간×8칸)와 동일 라벨.
   목업 합계는 기존 와이어프레임 분위기를 유지하도록 분배. */
export const hourlyEvents: HourlyEventStat[] = [
  { slot: '0-3시', 주차: 1, 쓰레기: 0 },
  { slot: '3-6시', 주차: 1, 쓰레기: 1 },
  { slot: '6-9시', 주차: 5, 쓰레기: 3 },
  { slot: '9-12시', 주차: 9, 쓰레기: 5 },
  { slot: '12-15시', 주차: 6, 쓰레기: 5 },
  { slot: '15-18시', 주차: 11, 쓰레기: 6 },
  { slot: '18-21시', 주차: 8, 쓰레기: 4 },
  { slot: '21-24시', 주차: 3, 쓰레기: 2 },
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

// AI 인사이트 (1m) — 리포트 소견. 수치는 위 목업 통계와 일치시킨다.
export const aiInsights: AiInsight[] = [
  {
    title: '불법주차 증가 추세',
    body: '지하주차장 B2 구역 불법주차가 최근 2주간 지속 증가했습니다(전주 대비 +40%). 저녁 시간대 재발 비중이 높아 반복 발생 구간으로 분류됩니다.',
    action: 'B2 구역 순찰 빈도 상향',
  },
  {
    title: 'R-01 구동부 이상 신호',
    body: 'R-01 좌측 휠 모터에서 배터리 효율 저하가 감지되었습니다. 동일 경로 대비 소모 전력이 늘어 주행 저항 증가가 의심됩니다.',
    action: '좌측 휠 모터 점검',
  },
  {
    title: '오후 시간대 이벤트 집중',
    body: '15-18시 구간에서 17건이 발생해 전체의 20%를 차지했습니다. 주차·쓰레기 유형이 대부분으로 생활 동선과 겹치는 시간대입니다.',
    action: '오후 순찰 경로 강화',
  },
  {
    title: '위험구역 처리율 저조',
    body: '위험구역 이벤트 처리율이 56%로 전체 평균(71%)을 밑돌았습니다. 미처리 4건이 대기 중이며 평균 처리시간도 길어지는 추세입니다.',
    action: '처리 우선순위 상향',
  },
]

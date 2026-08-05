import type { Patrol } from '../types/domain'

// 와이어프레임 1d(목록)·1e(상세 보고서) 예시값 그대로
// 맨 앞 P-1043 은 방금 끝난 순찰 — 대시보드 순찰 완료 모달이 이 건을 띄운다.
export const patrols: Patrol[] = [
  {
    id: 'P-1043',
    robotId: 'R-01',
    date: '07/15',
    start: '14:05',
    end: '14:47',
    routeZones: ['출발지', '101동', '102동', '103동', '지하주차장 B2', '출발지'],
    routeSummary: '101동→102동→103동→지하주차장 B2',
    eventCount: 2,
    status: '완료',
    batteryFrom: 92,
    batteryTo: 78,
    report: {
      reportNo: 'RPT-1043',
      createdAt: '2026/07/15 14:49',
      aiSummary:
        '07월 15일 오후 순찰(14:05~14:47)에서 총 2건이 탐지되었습니다. 101동 앞에서 불법주차 차량 1대(신뢰도 92%), 지하주차장 B2에서 응급상황(쓰러짐 의심, 신뢰도 92%)이 확인되어 긴급으로 승격되었습니다. 나머지 구간은 이상이 없습니다.',
    },
  },
  {
    id: 'P-1042',
    robotId: 'R-01',
    date: '07/15',
    start: '09:00',
    end: '09:42',
    routeZones: ['출발지', '주차장 A', '분리수거장', '지하주차장 B2', '출발지'],
    routeSummary: '101동→102동→103동',
    eventCount: 2,
    status: '완료',
    batteryFrom: 100,
    batteryTo: 82,
    report: {
      reportNo: 'RPT-1042',
      createdAt: '2026/07/15 09:45',
      aiSummary:
        '07월 15일 오전 순찰(09:00~09:42)에서 총 2건의 이벤트가 탐지되었습니다. 주차장 A에서 미등록 차량 1대(신뢰도 92%), 분리수거장에서 무단 투기 쓰레기가 확인되었습니다. 지하주차장 B2를 포함한 나머지 구간은 이상이 없습니다.',
      anomalyComment:
        '최근 7일간 주차장 A의 불법주차 빈도가 +40% 증가했습니다 — 해당 구역 순찰 빈도 상향을 권장합니다.',
    },
    // 순찰 지점 기록 (1e v15) — 이상 지점 상태는 이벤트 상세(1g) 링크
    points: [
      { time: '09:00', type: '출발', location: '출발지 (충전 스테이션)', status: '이상무' },
      {
        time: '09:12',
        type: '불법주차',
        location: '주차장 A',
        status: '탐지',
        note: '미등록 차량 1대 감지 · 신뢰도 92%',
        eventId: 'E-3311',
      },
      { time: '09:21', type: '정기 점검', location: '분리수거장', status: '이상무' },
      {
        time: '09:30',
        type: '쓰레기',
        location: '지하주차장 B2',
        status: '처리완료',
        note: '무단투기 의심 물체 → 관리자 확인 완료',
        eventId: 'E-3310',
      },
      {
        time: '09:42',
        type: '복귀',
        location: '출발지 (충전 스테이션)',
        status: '이상무',
        note: '배터리 82% · 자동 충전 시작',
      },
    ],
  },
  {
    id: 'P-1041',
    robotId: 'R-01',
    date: '07/15',
    start: '06:00',
    end: '06:38',
    routeZones: ['출발지', '주차장 B', '지하주차장 B2', '출발지'],
    eventCount: 1,
    status: '완료',
    batteryFrom: 100,
    batteryTo: 86,
  },
  {
    id: 'P-1040',
    robotId: 'R-01',
    date: '07/14',
    start: '22:00',
    end: null,
    routeZones: ['출발지', '전체 구역 야간 순찰 (진행중)'],
    eventCount: 0,
    status: '진행중',
    batteryFrom: 100,
  },
]

import type { PatrolEvent } from '../types/domain'

// 와이어프레임 1f(목록)·1g(상세)·1c(최근 이벤트 — 긴급만) 예시값 그대로 (v15)
export const events: PatrolEvent[] = [
  {
    id: 'E-3313',
    time: '14:32',
    type: '응급상황',
    location: '지하주차장 B2',
    robotId: 'R-01',
    status: '긴급',
    confidence: 92,
    subType: '쓰러짐 의심',
    emergencyReason:
      'AI가 응급상황(쓰러짐 의심 인물)을 92% 신뢰도로 탐지 — 최근 5분 내 동일 위치 재탐지로 자동 "긴급" 승격됨',
  },
  // 대시보드 최근 이벤트(긴급만) 두 번째 카드 (1c)
  {
    id: 'E-3312',
    time: '11:48',
    type: '화재 의심',
    location: '102동 전기실',
    robotId: 'R-01',
    status: '긴급',
    confidence: 87,
    subType: '연기 감지',
  },
  {
    id: 'E-3311',
    time: '14:20',
    type: '불법주차',
    location: '101동 앞',
    robotId: 'R-01',
    status: '탐지',
    confidence: 92,
  },
  {
    id: 'E-3310',
    time: '13:10',
    type: '쓰레기',
    location: '103동 화단',
    robotId: 'R-02',
    status: '처리완료',
    confidence: 88,
    memo: '경비팀 수거 완료',
  },
  {
    id: 'E-3309',
    time: '11:05',
    type: '위험구역',
    location: '위험구역(B2)',
    robotId: 'R-02',
    status: '처리중',
    confidence: 85,
    memo: '경비팀 현장 확인 중',
  },
]

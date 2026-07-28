// 도메인 타입 — 와이어프레임(docs/screens.md) 기반. 목업/실서버 공용.
// 필요 시 확장하되, 화면에 실제로 쓰는 필드는 여기 반영해 일관성 유지.

export type StatusLabel =
  | '완료' | '이상무' | '정상' | '순찰중' | '온라인' | '활성'
  | '진행중' | '수신됨'
  | '점검필요' | '주의'
  | '긴급' | '응급상황' | '침입'
  // 이벤트 처리 상태 — 경비원 관리 3단계 (와이어프레임 v15)
  | '탐지' | '처리중' | '처리완료'
  // 로봇 상태 (1i 목록)
  | '대기' | '충전중' | '오류' | '오프라인'
  // 순찰 상태
  | '중단' | '실패';

export type RobotStatus = '대기' | '순찰중' | '충전중' | '오류' | '오프라인';
export type PatrolStatus = '진행중' | '완료' | '중단' | '실패';
export type ProcessingStatus = '탐지' | '처리중' | '처리완료';
export type RiskLevel = '낮음' | '보통' | '긴급';

export type Tone = 'success' | 'info' | 'warning' | 'danger' | 'neutral';

export type EventType = '불법주차' | '쓰레기' | '위험구역' | '응급상황' | '화재 의심' | '침입' | '정기 점검';
export type ZoneType = '주차장' | '분리수거장' | '위험구역' | '출입구' | '도착지' | '기타';

export interface Complex {          // 아파트단지
  id: string;
  name: string;                     // 예: 가온아파트
  roadAddress: string;
  zipcode?: string;
}

export interface Zone {
  id: string;
  type: ZoneType;
  label: string;                    // 예: 주차장 A, 지하주차장 B2
  // 구역 지정(1y): 그리드 좌표(열 A~N, 행 1~7) 또는 rect
  rect?: { x: number; y: number; w: number; h: number };
}

// ---- IoT 맵 (백엔드 → 프론트) ----
// 로봇이 스캔해 백엔드에 올린 단지 맵. 온보딩(1y)에서 등록한 Zone과
// 같은 그리드 좌표계(cols×rows)를 쓴다. 프론트는 이 데이터를 렌더만 한다.
export interface ComplexMapData {
  cols: number;                     // 14 (열 A~N)
  rows: number;                     // 7
  zones: Zone[];
  mapId?: string;
  mapUrl?: string;
}

export interface MapRobot {         // 실시간 로봇 위치 (그리드 좌표, 소수 허용)
  id: string;                       // R-01
  x: number;
  y: number;
  battery?: number;
  updatedAt?: string;
}

export interface MapPin {           // 지도 위 이벤트 핀
  id: string;                       // 이벤트 ID (E-3312)
  label: string;                    // "불법주차 · 101동 앞"
  x: number;
  y: number;
  tone: Tone;
}

export interface MapCheckpoint {    // 순찰 체크포인트 (1h LIVE MAP)
  id: string;
  icon: string;                     // 🚩 🗑 🅿
  label: string;                    // 출발지, 분리수거장, 주차장 A…
  x: number;
  y: number;
}

export interface Robot {
  id: string;                       // R-01
  backendId?: string | number;
  name: string;                     // R-01
  registrationNo: string;           // RB-2024-01
  serialNo?: string;                // SN-2026-0001
  introducedAt: string;             // 2026/03/12
  zone: string;                     // 담당 구역 (전체 / 101~103동)
  status: StatusLabel;              // 순찰중 등
  battery: number;                  // 78 (%)
  location?: string;                // 현재 위치 — 지하주차장 B2 / 충전 스테이션 (1i 목록)
  lastPatrol?: string;              // 최근 순찰 — 09:00–09:42 (1i 목록)
  parts: { name: string; status: StatusLabel }[]; // 카메라/라이다/휠모터/구동부
  odometerKm?: number;              // 12.4 — x,y 위치 로그 기반 이동거리 합산
  weeklyUptime?: number;            // 94 (%) — 가동/정지/전체 시간 비율
}

export interface PatrolPoint {      // 순찰 지점 기록 (상세 1e)
  time: string;                     // 09:12
  type: EventType | '출발' | '복귀' | '정기 점검';
  location: string;                 // 주차장 A
  status: StatusLabel;              // 이상무 / 탐지 / 처리완료
  note?: string;                    // 미등록 차량 1대 감지 · 신뢰도 92%
  eventId?: string;                 // 이상 지점 → 이벤트 상세(1g) 링크. 상태 변경은 이벤트 상세에서
}

export interface Patrol {
  id: string;                       // P-1042
  backendId?: string | number;
  robotId: string;                  // R-01
  robotName?: string;               // 로봇 이름 (사용자 지정) — 서버 응답에 포함, 없으면 로봇 목록에서 조회
  date: string;                     // 07/15
  start: string;                    // 09:00
  end?: string | null;              // 09:42 (진행중이면 null)
  routeZones: string[];             // [출발지, 주차장 A, 분리수거장, 위험구역(B2), 출발지]
  routeSummary?: string;            // 상세 요약용 경로 표기 (1e: "101동→102동→103동")
  eventCount: number;               // 2
  status: StatusLabel;              // 완료 / 진행중
  batteryFrom?: number;             // 100
  batteryTo?: number;               // 82
  report?: PatrolReport;
  points?: PatrolPoint[];
}

export interface PatrolReport {     // PATROL REPORT (1e)
  reportNo: string;                 // RPT-1042
  createdAt: string;                // 자동 생성 일시
  aiSummary: string;
  anomalyComment?: string;
}

export interface PatrolEvent {      // 이벤트 (1f/1g)
  id: string;                       // E-3312
  backendId?: string | number;
  patrolId?: string;
  time: string;                     // 14:20
  type: EventType;
  location: string;                 // 101동 앞
  robotId: string;                  // R-01
  status: StatusLabel;              // 탐지 / 처리중 / 처리완료 (긴급은 riskLevel로 분리)
  riskLevel?: RiskLevel;            // 긴급 / 보통 / 낮음
  processingStatus?: ProcessingStatus;
  assignee?: string;                // 담당자 (처리중/처리완료 시) — 백엔드 제공
  processedAt?: string;             // 처리 완료 시각 (처리완료 시 표시)
  occurredAt?: string;
  x?: number;
  y?: number;
  confidence?: number;              // 92 (%)
  evidenceImageUrl?: string;
  memo?: string;
  subType?: string;                 // 긴급 세부 — "쓰러짐 의심" (1c+/1o)
  emergencyReason?: string;         // 긴급 판단 사유 (1o)
}

export interface StatSummary {      // 통계 KPI (1m)
  totalPatrols: number;             // 142
  totalEvents: number;              // 83
  avgHandleMin: number;             // 12
  uptime: number;                   // 94
  deltas?: { patrols?: string; events?: string; handle?: string; uptime?: string };
}

export interface DailyEventStat {   // 일자별 이벤트 추이 (1m 라인 차트)
  date: string;                     // 07/15
  count: number;                    // 6
}

// 시간대별 이벤트 발생(유형별 누적 막대, 1m). 유형 키는 와이어프레임 표기 그대로.
export interface HourlyEventStat {
  slot: string;                     // 9-12시
  주차: number;
  쓰레기: number;
  위험구역: number;
}

export interface HandlingStat {     // 처리 현황 100% 기준 (1m)
  label: string;                    // 전체 / 주차 / 쓰레기 / 위험구역
  handled: number;                  // 59 (건)
  pending: number;                  // 24 (건)
  handledPct: number;               // 71 (%)
  pendingPct: number;               // 29 (%)
}

export interface ZoneShareStat {    // 구역별 이벤트 비율 파이차트 (1m)
  zone: string;                     // 지하주차장 B2
  count: number;                    // 9 (건)
  pct: number;                      // 42 (%)
}

export interface User {
  loginId: string;
  name: string;
  nickname: string;
  phone: string;
  complexId: string;
  role: '관리자';
}

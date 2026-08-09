import type { ComplexMapData, MapCheckpoint, MapPin, MapRobot } from '../types/domain'

/* IoT 맵 목업 — 실제로는 백엔드가 내려주는 응답.
   로봇이 스캔한 단지 맵(그리드 14×7)과 온보딩(1y)에서 등록된 구역 목록.
   서버 연동 시 GET /complexes/:id/map 응답으로 교체.

   배치는 관제 지도 시안 그대로 — 위/아래 3열 건물, 가운데 설비(주차장·놀이터·분리수거장),
   좌·상단 경계에 정문·후문. 순찰 경로는 이 블록들을 감싸는 외곽 순환 동선이다. */
export const complexMap: ComplexMapData = {
  cols: 14,
  rows: 7,
  metersPerCell: 15,
  zones: [
    // 상단 3개 동
    { id: 'Z-01', type: '기타', label: '101동', rect: { x: 1.8, y: 0.4, w: 3.1, h: 1.05 } },
    { id: 'Z-02', type: '기타', label: '102동', rect: { x: 5.4, y: 0.4, w: 3.0, h: 1.05 } },
    { id: 'Z-03', type: '기타', label: '103동', rect: { x: 8.9, y: 0.4, w: 3.0, h: 1.05 } },
    // 가운데 설비
    { id: 'Z-04', type: '주차장', label: '지상주차장', rect: { x: 1.8, y: 2.15, w: 4.1, h: 1.6 } },
    { id: 'Z-05', type: '기타', label: '놀이터', rect: { x: 6.4, y: 2.15, w: 2.1, h: 1.6 } },
    { id: 'Z-06', type: '분리수거장', label: '분리수거장', rect: { x: 9.0, y: 2.15, w: 2.9, h: 1.6 } },
    // 하단 3개 블록
    { id: 'Z-07', type: '기타', label: '104동', rect: { x: 1.8, y: 4.6, w: 3.1, h: 1.25 } },
    { id: 'Z-08', type: '기타', label: '커뮤니티센터', rect: { x: 5.4, y: 4.6, w: 3.0, h: 1.25 } },
    { id: 'Z-09', type: '주차장', label: '지하주차장 진입', rect: { x: 8.9, y: 4.6, w: 3.0, h: 1.25 } },
    // 경계 출입구 — 구역 상자 대신 경계 바 + 라벨로 그려진다
    { id: 'Z-10', type: '출입구', label: '정문', rect: { x: 0, y: 1.9, w: 0.6, h: 1.3 } },
    { id: 'Z-11', type: '출입구', label: '후문', rect: { x: 5.6, y: 0, w: 1.7, h: 0.5 } },
  ],
}

/* 실시간 레이어 — 로봇 위치·이벤트 핀 (서버 연동 시 폴링/웹소켓으로 교체) */
export const mapRobot: MapRobot = { id: 'R-01', name: 'R0-Ki 1호기', x: 13.2, y: 3.1, battery: 78 }

/* 로봇별 지도 위치 — 대시보드 하단 로봇 목록에서 고른 로봇을 지도에 띄울 때 쓴다.
   순찰중(R-01·R-04)은 경로 위, 대기·충전중(R-02·R-03)은 충전 스테이션(출발지) 근처의 마지막 위치.
   좌표는 체크포인트 점·라벨과 겹치지 않도록 지점에서 살짝 비켜 둔다. */
export const mapRobots: MapRobot[] = [
  { id: 'R-01', name: 'R0-Ki 1호기', x: 13.2, y: 3.1, battery: 78 },
  { id: 'R-02', name: 'R0-Ki 2호기', x: 1.9, y: 5.6, battery: 100 },
  { id: 'R-03', name: 'R0-Ki 3호기', x: 1.2, y: 5.6, battery: 45 },
  { id: 'R-04', name: 'R0-Ki 4호기', x: 4.6, y: 6.4, battery: 63 },
]

export const mapPins: MapPin[] = [
  {
    id: 'E-3313',
    label: '응급상황 · 쓰러짐 의심',
    detail: '02:14 감지 · 지하주차장 진입로',
    x: 11.6,
    y: 4.3,
    tone: 'danger',
  },
  { id: 'E-3311', label: '불법주차 · 지상주차장', x: 4.4, y: 3.9, tone: 'warning' },
  { id: 'E-3310', label: '쓰레기 · 분리수거장', x: 9.6, y: 4.1, tone: 'success' },
]

/* 순찰 체크포인트 + 이동 경로 — 배열 순서 = 순찰 경로(마지막 → 처음으로 순환).
   note 가 있는 지점만 지도에서 물방울 마커 + 콜아웃 카드로 강조된다. */
export const mapCheckpoints: MapCheckpoint[] = [
  { id: 'CP-01', icon: '🚩', label: '출발지', x: 1.0, y: 6.4, note: '경비실 · 충전소 00:58 출발' },
  { id: 'CP-02', icon: '·', label: '', x: 1.0, y: 4.05 },
  { id: 'CP-03', icon: '·', label: '', x: 1.0, y: 1.75 },
  { id: 'CP-04', icon: '🏢', label: '101동', x: 3.85, y: 1.75, note: '01:22 통과 · 이상 없음' },
  { id: 'CP-05', icon: '🏢', label: '102동', x: 7.46, y: 1.75 },
  { id: 'CP-06', icon: '🏢', label: '103동', x: 10.85, y: 1.75, note: '02:03 통과 · 최근 지점' },
  { id: 'CP-07', icon: '·', label: '', x: 13.2, y: 1.75 },
  { id: 'CP-08', icon: '·', label: '', x: 13.2, y: 4.05 },
  { id: 'CP-09', icon: '·', label: '', x: 13.2, y: 6.4 },
  { id: 'CP-10', icon: '🅿', label: '지하주차장', x: 10.42, y: 6.4 },
  { id: 'CP-11', icon: '🏛', label: '커뮤니티', x: 7.03, y: 6.4 },
  { id: 'CP-12', icon: '🏢', label: '104동', x: 3.9, y: 6.4 },
]

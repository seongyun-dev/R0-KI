import type { ComplexMapData, MapCheckpoint, MapPin, MapRobot } from '../types/domain'

/* IoT 맵 목업 — 실제로는 백엔드가 내려주는 응답.
   로봇이 스캔한 단지 맵(그리드 14×7)과 온보딩(1y)에서 등록된 구역 목록.
   서버 연동 시 GET /complexes/:id/map 응답으로 교체. */
export const complexMap: ComplexMapData = {
  cols: 14,
  rows: 7,
  zones: [
    { id: 'Z-01', type: '주차장', label: '주차장 A', rect: { x: 1, y: 1, w: 4, h: 2 } },
    { id: 'Z-02', type: '분리수거장', label: '분리수거장', rect: { x: 6, y: 1, w: 3, h: 2 } },
    { id: 'Z-03', type: '기타', label: '101동', rect: { x: 10, y: 1, w: 3, h: 2 } },
    { id: 'Z-04', type: '주차장', label: '지하주차장 B2', rect: { x: 1, y: 4, w: 4, h: 2 } },
    { id: 'Z-05', type: '기타', label: '103동 화단', rect: { x: 6, y: 4, w: 3, h: 2 } },
    { id: 'Z-06', type: '위험구역', label: '위험구역(B2)', rect: { x: 10, y: 4, w: 3, h: 2 } },
  ],
}

/* 실시간 레이어 — 로봇 위치·이벤트 핀 (서버 연동 시 폴링/웹소켓으로 교체) */
export const mapRobot: MapRobot = { id: 'R-01', x: 6.2, y: 3.5 }

export const mapPins: MapPin[] = [
  { id: 'E-3313', label: '응급상황 · 지하주차장 B2', x: 3.0, y: 5.0, tone: 'danger' },
  { id: 'E-3311', label: '불법주차 · 101동 앞', x: 11.0, y: 3.3, tone: 'warning' },
  { id: 'E-3310', label: '쓰레기 · 103동 화단', x: 7.5, y: 4.8, tone: 'success' },
]

/* 순찰 체크포인트 + 이동 경로 (1h LIVE MAP) — 배열 순서 = 순찰 경로 */
export const mapCheckpoints: MapCheckpoint[] = [
  { id: 'CP-0', icon: '🚩', label: '출발지', x: 1.2, y: 6.2 },
  { id: 'CP-1', icon: '🅿', label: '주차장 A', x: 3.0, y: 2.0 },
  { id: 'CP-2', icon: '🗑', label: '분리수거장', x: 7.5, y: 2.0 },
  { id: 'CP-3', icon: '🅿', label: '주차장 B', x: 12.0, y: 5.6 },
]

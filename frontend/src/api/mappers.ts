import type {
  ComplexResponse,
  EmergencyEventSseResponse,
  EventDetailResponse,
  EventListItemResponse,
  MapInfoResponse,
  MapMonitoringResponse,
  NotificationDetailResponse,
  NotificationHistoryItemResponse,
  PatrolDetailResponse,
  PatrolListResponse,
  PatrolRouteCheckpointResponse,
  PatrolTimelineResponse,
  RobotDetailResponse,
  RobotListResponse,
  RobotLocationEvent,
  ZoneResponse,
} from './contracts'
import type {
  Complex,
  ComplexMapData,
  EventType,
  MapCheckpoint,
  MapPin,
  MapRobot,
  NotificationDetailRecord,
  NotificationRecord,
  NotificationSendStatus,
  Patrol,
  PatrolEvent,
  PatrolPoint,
  ProcessingStatus,
  RiskLevel,
  Robot,
  StatusLabel,
  Zone,
  ZoneType,
} from '../types/domain'

const GRID_COLS = 14
const GRID_ROWS = 7

export function toNumber(value: number | string | null | undefined, fallback = 0) {
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function dateParts(value?: string | null) {
  if (!value) return { date: '', time: '' }
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    const [date = '', time = ''] = value.split('T')
    return { date, time: time.slice(0, 5) }
  }
  return {
    date: new Intl.DateTimeFormat('ko-KR', { month: '2-digit', day: '2-digit' })
      .format(parsed)
      .replace(/\. /g, '/')
      .replace('.', ''),
    time: new Intl.DateTimeFormat('ko-KR', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).format(parsed),
  }
}

function formatDate(value?: string | null) {
  if (!value) return '-'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value.slice(0, 10).replace(/-/g, '/')
  return new Intl.DateTimeFormat('ko-KR').format(parsed).replace(/\.$/, '').replace(/\. /g, '/')
}

function eventType(value: string): EventType {
  const map: Record<string, EventType> = {
    // 백엔드 enum 코드
    ILLEGAL_PARKING: '불법주차',
    UNREGISTERED_VEHICLE: '불법주차',
    TRASH_DETECTED: '쓰레기',
    RECYCLING_AREA_FULL: '쓰레기',
    EMERGENCY: '응급상황',
    // 한글 별칭(하위호환)
    미등록차량: '불법주차',
    쓰레기탐지: '쓰레기',
    분리수거장포화: '쓰레기',
    화재의심: '화재 의심',
  }
  return map[value] ?? (value as EventType)
}

function processingStatus(value: string): ProcessingStatus {
  const map: Record<string, ProcessingStatus> = {
    DETECTED: '탐지',
    PROCESSING: '처리중',
    COMPLETED: '처리완료',
  }
  if (map[value]) return map[value]
  if (value === '처리중' || value === '처리완료') return value
  return '탐지'
}

function riskLevel(value: string): RiskLevel {
  const map: Record<string, RiskLevel> = { LOW: '낮음', NORMAL: '보통', EMERGENCY: '긴급' }
  if (map[value]) return map[value]
  if (value === '긴급' || value === '보통' || value === '낮음') return value
  return '낮음'
}

export function complexResponseToDomain(value: ComplexResponse): Complex {
  return {
    id: String(value.apartmentComplexId),
    name: value.apartmentName,
    roadAddress: value.address,
    zipcode: value.postalCode ?? undefined,
  }
}

/** 목록 항목(EventListResponse) → 도메인 (1f) */
export function eventListItemToDomain(value: EventListItemResponse): PatrolEvent {
  const processing = processingStatus(value.status)
  return {
    id: String(value.eventId),
    backendId: value.eventId,
    time: dateParts(value.occurredAt).time,
    occurredAt: value.occurredAt,
    type: eventType(value.type),
    location: value.location ?? '위치 미확인',
    robotId: value.robotName, // 백엔드는 로봇 이름을 제공(id 아님) — 표시용
    status: processing,
    riskLevel: riskLevel(value.riskLevel),
    processingStatus: processing,
    assignee: value.assignee ?? undefined,
  }
}

export function emergencyEventSseToDomain(value: EmergencyEventSseResponse): PatrolEvent {
  const processing = processingStatus(value.processingStatus)
  return {
    id: String(value.eventId),
    backendId: value.eventId,
    time: dateParts(value.occurredAt).time,
    occurredAt: value.occurredAt,
    type: eventType(value.eventType),
    location: value.location ?? '위치 미확인',
    robotId: value.robotName,
    status: processing,
    riskLevel: riskLevel(value.riskLevel),
    processingStatus: processing,
    x: value.x ?? undefined,
    y: value.y ?? undefined,
  }
}

/** 상세(EventDetailResponse) → 도메인 (1g) */
export function eventDetailToDomain(value: EventDetailResponse): PatrolEvent {
  const processing = processingStatus(value.status)
  return {
    id: String(value.eventId),
    backendId: value.eventId,
    time: dateParts(value.occurredAt).time,
    occurredAt: value.occurredAt,
    type: eventType(value.type),
    location: value.location ?? '위치 미확인',
    robotId: value.robotName, // 표시용(백엔드는 이름 제공)
    status: processing,
    riskLevel: riskLevel(value.riskLevel),
    processingStatus: processing,
    processedAt: value.processedAt ? dateParts(value.processedAt).time : undefined,
    // 백엔드 confidence는 0~1 → % 로 표시
    confidence: value.confidence == null ? undefined : Math.round(toNumber(value.confidence) * 100),
    evidenceImageUrl: value.evidence?.fileUrl,
    memo: value.processingNote ?? undefined,
  }
}

/* ── 알림 기록 ─────────────────────────────────────────────── */

/** 발송 시각 표기 — 07/30 14:20. 미발송(null)이면 '—' */
function stampLabel(value?: string | null) {
  if (!value) return '—'
  const { date, time } = dateParts(value)
  if (!date) return time || '—'
  return `${date} ${time}`
}

/** 101동 1502호. 값이 없으면 '—', 이미 동/호가 붙어 있으면 그대로 쓴다. */
function unitLabel(building?: string | null, unit?: string | null) {
  const b = building?.trim()
  const u = unit?.trim()
  const parts = [
    b ? (b.endsWith('동') ? b : `${b}동`) : '',
    u ? (u.endsWith('호') ? u : `${u}호`) : '',
  ].filter(Boolean)
  return parts.length > 0 ? parts.join(' ') : '—'
}

/** 발송 상태 코드 → 한글. 코드가 비면 발송 시각 유무로 판단한다. */
function notificationStatus(value: string, sentAt?: string | null): NotificationSendStatus {
  const map: Record<string, NotificationSendStatus> = {
    SUCCESS: '발송완료',
    SENT: '발송완료',
    DELIVERED: '발송완료',
    COMPLETED: '발송완료',
    PENDING: '발송대기',
    WAITING: '발송대기',
    QUEUED: '발송대기',
    READY: '발송대기',
    PROCESSING: '발송대기',
    FAILED: '발송실패',
    FAIL: '발송실패',
    ERROR: '발송실패',
  }
  const code = (value ?? '').trim().toUpperCase()
  if (map[code]) return map[code]
  if (value) return value as NotificationSendStatus
  return sentAt ? '발송완료' : '발송대기'
}

/** 목록 항목(NotificationHistoryItemResponse) → 도메인 */
export function notificationListItemToDomain(
  value: NotificationHistoryItemResponse,
): NotificationRecord {
  return {
    id: String(value.notificationId),
    backendId: value.notificationId,
    eventId: String(value.eventId),
    eventType: eventType(value.eventType),
    recipientName: value.recipientName || '—',
    address: unitLabel(value.buildingNumber, value.unitNumber),
    status: notificationStatus(value.status, value.sentAt),
    sentAt: value.sentAt ?? undefined,
    sentAtLabel: stampLabel(value.sentAt),
  }
}

/** 상세(NotificationDetailResponse) → 도메인 */
export function notificationDetailToDomain(
  value: NotificationDetailResponse,
): NotificationDetailRecord {
  return {
    id: String(value.notificationId),
    backendId: value.notificationId,
    eventId: String(value.eventId),
    eventType: eventType(value.eventType),
    recipientName: value.recipientName || '—',
    address: unitLabel(value.buildingNumber, value.unitNumber),
    status: notificationStatus(value.status, value.sentAt),
    sentAt: value.sentAt ?? undefined,
    sentAtLabel: stampLabel(value.sentAt),
    title: value.title || '알림',
    content: value.content ?? '',
    recipientPhone: value.recipientPhoneNumber || '—',
    occurredAt: value.occurredAt ?? undefined,
    occurredAtLabel: stampLabel(value.occurredAt),
    location: value.location || '위치 미확인',
    licensePlate: value.licensePlate || undefined,
  }
}

function patrolStatus(value: string): StatusLabel {
  const map: Record<string, StatusLabel> = {
    IN_PROGRESS: '진행중',
    COMPLETED: '완료',
    STOPPED: '중단',
    FAILED: '실패',
  }
  return map[value] ?? (value as StatusLabel)
}

/** route(체크포인트 방문) → 순서대로 구역 이름 배열. 연속 중복은 제거. */
function routeZoneNames(route: PatrolRouteCheckpointResponse[] = []): string[] {
  return [...route]
    .sort((a, b) => a.sequence - b.sequence)
    .map((checkpoint) => checkpoint.checkpointName)
    .filter((name): name is string => Boolean(name))
    .filter((name, index, names) => index === 0 || name !== names[index - 1])
}

function timelinePoint(value: PatrolTimelineResponse): PatrolPoint {
  const { time } = dateParts(value.recordedAt)
  return {
    time,
    type: value.eventType ? eventType(value.eventType) : '정기 점검',
    location: value.checkpointName ?? '위치 미확인',
    status: (value.processingStatus ? processingStatus(value.processingStatus) : '이상무') as StatusLabel,
    eventId: value.eventId == null ? undefined : String(value.eventId),
    x: value.xCoordinate == null ? undefined : toNumber(value.xCoordinate),
    y: value.yCoordinate == null ? undefined : toNumber(value.yCoordinate),
  }
}

/** 목록 항목(PatrolListResponse) → 도메인 (1d) */
export function patrolListItemToDomain(value: PatrolListResponse): Patrol {
  const started = dateParts(value.startedAt)
  const ended = dateParts(value.endedAt)
  const zones = routeZoneNames(value.route)
  return {
    id: String(value.patrolId),
    backendId: value.patrolId,
    robotId: value.robotName, // 백엔드 목록은 로봇 이름만 제공(id 아님) — 표시용
    robotName: value.robotName,
    date: started.date,
    start: started.time,
    end: value.endedAt ? ended.time : null,
    routeZones: zones.length > 0 ? zones : ['경로 정보 없음'],
    routeSummary: zones.length > 0 ? zones.join('→') : undefined,
    eventCount: value.detectedEventCount,
    status: patrolStatus(value.patrolStatus),
  }
}

/** 상세(PatrolDetailResponse) → 도메인 (1e). 응답에 patrolId가 없어 id는 인자로 받는다. */
export function patrolDetailToDomain(value: PatrolDetailResponse, id: string): Patrol {
  const started = dateParts(value.startedAt)
  const ended = dateParts(value.endedAt)
  const zones = routeZoneNames(value.route)
  const timeline = value.timeline ?? []
  const summaryContent = value.aiSummary?.summaryContent
  return {
    id,
    backendId: id,
    robotId: value.robotName, // 상세엔 robotId 없음 — 이름을 표시용으로
    robotName: value.robotName,
    date: started.date,
    start: started.time,
    end: value.endedAt ? ended.time : null,
    routeZones: zones.length > 0 ? zones : ['경로 정보 없음'],
    routeSummary: zones.length > 0 ? zones.join('→') : undefined,
    eventCount: timeline.filter((point) => point.eventId != null).length,
    status: patrolStatus(value.patrolStatus),
    batteryFrom: value.battery?.startLevel == null ? undefined : toNumber(value.battery.startLevel),
    batteryTo: value.battery?.endLevel == null ? undefined : toNumber(value.battery.endLevel),
    // AI 요약이 실제 생성(내용 존재)된 경우에만 보고서 노출
    report: summaryContent
      ? {
          reportNo: id,
          createdAt: value.endedAt ?? value.startedAt,
          aiSummary: summaryContent,
        }
      : undefined,
    points: timeline.length > 0 ? timeline.map(timelinePoint) : undefined,
    mapUrl: value.mapUrl ?? undefined,
    routePoints: (value.routePoints ?? [])
      .map((point) => ({
        x: toNumber(point.xCoordinate),
        y: toNumber(point.yCoordinate),
        recordedAt: point.recordedAt,
      }))
      .filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y)),
  }
}

export function robotStatusLabel(value: string): StatusLabel {
  const map: Record<string, StatusLabel> = {
    IDLE: '대기',
    PATROLLING: '순찰중',
    CHARGING: '충전중',
    ERROR: '오류',
    OFFLINE: '오프라인',
    OBSTACLE_STOP: '중단',
    DELETED: '오프라인',
  }
  return map[value] ?? (value as StatusLabel)
}

function sensorStatusLabel(value: string): StatusLabel {
  const map: Record<string, StatusLabel> = {
    NORMAL: '정상',
    NEEDS_INSPECTION: '점검필요',
    ERROR: '오류',
    DISCONNECTED: '오프라인',
  }
  return map[value] ?? (value as StatusLabel)
}

/** 목록 항목(RobotListResponse) → 도메인 (1i). 축소형이라 상세 필드는 플레이스홀더. */
export function robotListItemToDomain(value: RobotListResponse): Robot {
  return {
    id: String(value.robotId),
    backendId: value.robotId,
    name: value.robotName,
    registrationNo: '-',
    introducedAt: '-',
    zone: '미지정',
    status: robotStatusLabel(value.robotStatus),
    battery: value.batteryLevel == null ? undefined : toNumber(value.batteryLevel),
    location: value.location ?? '위치 미확인',
    parts: [],
  }
}

/** 상세(RobotDetailResponse) → 도메인 (1i). 센서 3필드 → parts 배열. */
export function robotDetailToDomain(value: RobotDetailResponse): Robot {
  const sensors: { name: string; status?: string | null }[] = [
    { name: '카메라 모듈', status: value.cameraStatus },
    { name: '라이다 센서', status: value.lidarStatus },
    { name: '휠 모터', status: value.motorStatus },
  ]
  return {
    id: String(value.robotId),
    backendId: value.robotId,
    name: value.robotName,
    registrationNo: value.robotSerialNumber,
    serialNo: value.robotSerialNumber,
    introducedAt: formatDate(value.registeredAt),
    zone: '미지정',
    status: robotStatusLabel(value.robotStatus),
    battery: value.batteryLevel == null ? undefined : toNumber(value.batteryLevel),
    parts: sensors
      .filter((s) => s.status != null)
      .map((s) => ({ name: s.name, status: sensorStatusLabel(s.status as string) })),
    weeklyUptime:
      value.weeklyOperationRate == null ? undefined : toNumber(value.weeklyOperationRate),
    recentPatrols: value.recentPatrols,
  }
}

function zoneType(value: string): ZoneType {
  if (
    value === '주차장' ||
    value === '분리수거장' ||
    value === '위험구역' ||
    value === '출입구' ||
    value === '도착지'
  ) {
    return value
  }
  return '기타'
}

type Bounds = { minX: number; minY: number; maxX: number; maxY: number }

function responseBounds(response: MapMonitoringResponse): Bounds {
  const coordinates = response.zones.flatMap((zone) => [
    [toNumber(zone.minX), toNumber(zone.minY)],
    [toNumber(zone.maxX), toNumber(zone.maxY)],
  ])
  coordinates.push([
    toNumber(response.robot.xCoordinate),
    toNumber(response.robot.yCoordinate),
  ])
  const xs = coordinates.map(([x]) => x)
  const ys = coordinates.map(([, y]) => y)
  return {
    minX: Math.min(...xs),
    minY: Math.min(...ys),
    maxX: Math.max(...xs),
    maxY: Math.max(...ys),
  }
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value))
}

export function mapPointToGrid(
  xValue: number | string,
  yValue: number | string,
  map: MapInfoResponse,
  fallbackBounds: Bounds,
) {
  const x = toNumber(xValue)
  const y = toNumber(yValue)
  const resolution = toNumber(map.resolution)
  const width = toNumber(map.width)
  const height = toNumber(map.height)

  if (resolution > 0 && width > 0 && height > 0 && map.originX != null && map.originY != null) {
    const pixelX = (x - toNumber(map.originX)) / resolution
    const pixelY = height - (y - toNumber(map.originY)) / resolution
    return {
      x: clamp((pixelX / width) * GRID_COLS, 0, GRID_COLS),
      y: clamp((pixelY / height) * GRID_ROWS, 0, GRID_ROWS),
    }
  }

  const spanX = Math.max(1, fallbackBounds.maxX - fallbackBounds.minX)
  const spanY = Math.max(1, fallbackBounds.maxY - fallbackBounds.minY)
  return {
    x: clamp(((x - fallbackBounds.minX) / spanX) * GRID_COLS, 0, GRID_COLS),
    y: clamp(GRID_ROWS - ((y - fallbackBounds.minY) / spanY) * GRID_ROWS, 0, GRID_ROWS),
  }
}

function zoneToDomain(
  value: ZoneResponse,
  map: MapInfoResponse,
  bounds: Bounds,
): { zone: Zone; checkpoint: MapCheckpoint } {
  const min = mapPointToGrid(value.minX, value.minY, map, bounds)
  const max = mapPointToGrid(value.maxX, value.maxY, map, bounds)
  const x = Math.min(min.x, max.x)
  const y = Math.min(min.y, max.y)
  const w = Math.max(0.3, Math.abs(max.x - min.x))
  const h = Math.max(0.3, Math.abs(max.y - min.y))
  const label = value.checkpointLabel ?? value.checkpointType
  const icon: Record<string, string> = {
    출발지: '🚩',
    도착지: '🏁',
    주차장: '🅿',
    분리수거장: '🗑',
    위험구역: '⚠',
  }
  return {
    zone: {
      id: String(value.checkpointId),
      type: zoneType(value.checkpointType),
      label,
      rect: { x, y, w, h },
    },
    checkpoint: {
      id: String(value.checkpointId),
      icon: icon[value.checkpointType] ?? '●',
      label,
      x: x + w / 2,
      y: y + h / 2,
    },
  }
}

export type MapViewData = {
  map: ComplexMapData
  robot: MapRobot
  pins: MapPin[]
  checkpoints: MapCheckpoint[]
}

export function mapMonitoringToView(response: MapMonitoringResponse): MapViewData {
  const bounds = responseBounds(response)
  const converted = response.zones.map((zone) => zoneToDomain(zone, response.map, bounds))
  const robotPoint = mapPointToGrid(
    response.robot.xCoordinate,
    response.robot.yCoordinate,
    response.map,
    bounds,
  )
  const robot: MapRobot = {
    id: response.robot.robotName || String(response.robot.robotId),
    ...robotPoint,
    battery:
      response.robot.batteryLevel == null ? undefined : toNumber(response.robot.batteryLevel),
    updatedAt: response.robot.updatedAt,
  }
  const checkpoints =
    converted.length > 0
      ? converted.map((item) => item.checkpoint)
      : [{ id: 'current', icon: '🤖', label: '현재 위치', ...robotPoint }]

  return {
    map: {
      cols: GRID_COLS,
      rows: GRID_ROWS,
      zones: converted.map((item) => item.zone),
      mapId: String(response.map.mapId),
      mapUrl: response.map.mapUrl,
    },
    robot,
    pins: [],
    checkpoints,
  }
}

export function locationEventToMapRobot(
  event: RobotLocationEvent,
  monitoring: MapMonitoringResponse,
): MapRobot {
  const point = mapPointToGrid(
    event.x ?? monitoring.robot.xCoordinate,
    event.y ?? monitoring.robot.yCoordinate,
    monitoring.map,
    responseBounds(monitoring),
  )
  return {
    id: String(event.robotId),
    ...point,
    updatedAt: event.locationUpdatedAt ?? undefined,
  }
}

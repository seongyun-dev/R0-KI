import type {
  ComplexResponse,
  EventDetailResponse,
  EventListResponse,
  MapInfoResponse,
  MapMonitoringResponse,
  PatrolPathPointResponse,
  PatrolResponse,
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
export function eventListItemToDomain(value: EventListResponse): PatrolEvent {
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

function patrolPoint(value: PatrolPathPointResponse): PatrolPoint {
  const { time } = dateParts(value.recordedAt)
  return {
    time,
    type: value.eventType ? eventType(value.eventType) : '정기 점검',
    location: value.checkpointLabel ?? `좌표 ${toNumber(value.xCoordinate).toFixed(1)}, ${toNumber(value.yCoordinate).toFixed(1)}`,
    status: (value.processingStatus ? processingStatus(value.processingStatus) : '이상무') as StatusLabel,
    note: value.note ?? undefined,
    eventId: value.eventId == null ? undefined : String(value.eventId),
  }
}

export function patrolResponseToDomain(
  value: PatrolResponse,
  path: PatrolPathPointResponse[] = [],
): Patrol {
  const started = dateParts(value.patrolStartedAt)
  const ended = dateParts(value.patrolEndedAt)
  const routeZones = path
    .map((point) => point.checkpointLabel)
    .filter((label): label is string => Boolean(label))
    .filter((label, index, values) => index === 0 || label !== values[index - 1])

  return {
    id: String(value.patrolId),
    backendId: value.patrolId,
    robotId: String(value.robotId),
    date: started.date,
    start: started.time,
    end: value.patrolEndedAt ? ended.time : null,
    routeZones: routeZones.length > 0 ? routeZones : ['경로 정보 없음'],
    routeSummary: routeZones.length > 0 ? routeZones.join('→') : undefined,
    eventCount: value.detectedEventCount,
    status: value.patrolStatus as StatusLabel,
    batteryFrom: value.batteryFrom == null ? undefined : toNumber(value.batteryFrom),
    batteryTo: value.batteryTo == null ? undefined : toNumber(value.batteryTo),
    report: value.report
      ? {
          reportNo: String(value.report.reportId),
          createdAt: value.report.createdAt,
          aiSummary: value.report.patrolSummary ?? value.report.reportContent ?? '',
          anomalyComment: value.report.anomalyComment ?? undefined,
        }
      : undefined,
    points: path.length > 0 ? path.map(patrolPoint) : undefined,
  }
}

function robotStatusLabel(value: string): StatusLabel {
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
    battery: toNumber(value.batteryLevel),
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
    battery: toNumber(value.batteryLevel),
    parts: sensors
      .filter((s) => s.status != null)
      .map((s) => ({ name: s.name, status: sensorStatusLabel(s.status as string) })),
    weeklyUptime:
      value.weeklyOperationRate == null ? undefined : toNumber(value.weeklyOperationRate),
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
    event.xCoordinate,
    event.yCoordinate,
    monitoring.map,
    responseBounds(monitoring),
  )
  return {
    id: event.robotName || String(event.robotId),
    ...point,
    battery: event.batteryLevel == null ? undefined : toNumber(event.batteryLevel),
    updatedAt: event.updatedAt ?? event.locationUpdatedAt,
  }
}

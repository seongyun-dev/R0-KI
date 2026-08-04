export type Id = number | string

export type PageResponse<T> = {
  content?: T[]
  items?: T[]
  data?: T[]
  page?: number
  size?: number
  totalElements?: number
  totalPages?: number
}

export type ListResponse<T> = T[] | PageResponse<T>

export type SignUpRequest = {
  username: string
  password: string
  name: string
  phoneNumber: string
  apartment: {
    name: string
    postalCode: string
    address: string
  }
}

export type SignUpResponse = {
  success: boolean,
  code: string,
  message: string,
  data: {
    accessToken: string,
    isNewApartment: boolean
  }
}

export type SignInRequest = {
  username: string
  password: string
}

/**
 * 로그인 응답.
 *
 * 계정만 만들고 이탈한 사용자를 다시 온보딩으로 돌려보내야 해서,
 * 백엔드가 로봇·지도 등록 여부를 함께 내려준다.
 * 두 값이 모두 true 여야 대시보드로 진입한다.
 *
 * 필드가 아직 안 내려오는 동안에는 undefined 로 두고
 * readOnboardingStatus() 가 로봇 목록 조회로 보완한다.
 */
export type SignInResponse = {
  success: boolean,
  code: string,
  message: string,
  data: {
    accessToken: string
    /** 로그인한 회원의 이름 (회원가입 시 입력한 name) */
    name: string
    /** 소속 단지에 등록된 로봇이 있는가 (백엔드 SigninResponse.hasRobot) */
    hasRobot?: boolean
    /** 소속 단지에 등록된 지도가 있는가 (백엔드 SigninResponse.hasMap) */
    hasMap?: boolean
    /** 아직 백엔드가 내려주지 않는다 — 오면 온보딩 재개·지도 조회에 그대로 쓴다 */
    robotId?: Id | null
    mapId?: Id | null
  }
}

export type ComplexResponse = {
  apartmentComplexId: Id
  apartmentName: string
  address: string
  postalCode?: string | null
}

// 백엔드 enum 코드 (back/dev 기준)
export type EventTypeCode =
  | 'ILLEGAL_PARKING'
  | 'UNREGISTERED_VEHICLE'
  | 'TRASH_DETECTED'
  | 'RECYCLING_AREA_FULL'
  | 'EMERGENCY'
  
export type ProcessingStatusCode = 
  |'DETECTED' 
  | 'PROCESSING' 
  | 'COMPLETED'

export type EventPeriodCode =
  | 'ALL'
  | 'TODAY'
  | 'LAST_7_DAYS'

export type RiskLevelCode = 
  | 'LOW' 
  | 'NORMAL' 
  | 'EMERGENCY'

export type EventListRequest = {
  type?: EventTypeCode, 
  status?: ProcessingStatusCode,
  period?: EventPeriodCode,
  risk?: RiskLevelCode
  page?: number,
  size?: number,
  sort?: string[]
}

// GET /api/events (목록)
export type EventListItemResponse  = {
    eventId: number,
    occurredAt: string,
    type: EventTypeCode,
    location: string,
    robotName: string,
    riskLevel: RiskLevelCode,
    status: ProcessingStatusCode,
    assignee: string | null
  }
export type EventListResponse = {
  content: EventListItemResponse[]
  page: number,
  size: number,
  totalElements: number,
  totalPages: number,
  first: boolean,
  last: boolean
}


export type MediaTypeCode = 'IMAGE' | 'VIDEO' | string

export type EventEvidenceResponse = {
  mediaType: MediaTypeCode
  fileUrl: string
  capturedAt: string
}

// GET /api/events/{id} (상세)
export type EventDetailResponse = {
  eventId: Id
  type: EventTypeCode | string
  confidence?: number | string | null // 0~1
  occurredAt: string
  elapsedSeconds?: number | null // 처리완료 전에만
  processedAt?: string | null // 처리완료 시각
  location?: string | null
  robotName: string
  riskLevel: RiskLevelCode | string
  status: ProcessingStatusCode | string
  processingNote?: string | null
  licensePlateNumber?: string | null
  evidence?: EventEvidenceResponse | null
}

// GET /api/events/{id}/status (상태 변경)
export type EventStatusChangeRequest = {
  processingStatus: ProcessingStatusCode,
  processingNote: string,
}

export type EventStatusChangeResponse = {
  eventId: number,
  processingStatus: ProcessingStatusCode,
  updatedAt: string,
}

// POST /api/events/{eventId}/notify
export type EventNotificationResponse = {
  notificationId: number
  eventId: number
  recipientResidentId: number
  sendStatus: string
  sentAt: string
}

// GET /api/notifications
export type NotificationHistoryItemResponse = {
  notificationId: number
  eventId: number
  eventType: string
  recipientName: string
  buildingNumber: string
  unitNumber: string
  status: string
  sentAt: string | null
}

export type NotificationHistoryResponse = {
  content: NotificationHistoryItemResponse[]
  page: number
  size: number
  totalElements: number
  totalPages: number
  first: boolean
  last: boolean
}

// GET /api/notifications/{notificationId}
export type NotificationDetailResponse = {
  notificationId: number
  eventId: number
  eventType: string
  title: string
  content: string
  recipientName: string
  recipientPhoneNumber: string
  buildingNumber: string
  unitNumber: string
  occurredAt: string
  licensePlate: string
  location: string
  status: string
  sentAt: string | null
}

// POST /api/robot/events/batch (로봇 전용 이벤트 일괄 등록)
export type EventBatchItemRequest = {
  tempId: string
  eventType: Extract<EventTypeCode, 'TRASH_DETECTED' | 'RECYCLING_AREA_FULL'>
  eventTitle: string
  eventDetails?: string
  occurredAt: string
  x: number
  y: number
  riskLevel: RiskLevelCode
}

export type EventBatchCreateRequest = {
  events: EventBatchItemRequest[]
}

// apiRequest가 공통 응답 래퍼를 벗기므로 data 내부 구조만 선언한다.
export type EventBatchCreateResponse = {
  events: {
    tempId: string
    eventId: number
  }[]
}

// POST /api/robot/vehicle-checks (로봇 전용 차량 일괄 판별)
export type VehicleCheckItemRequest = {
  tempId: string
  eventDetails?: string
  x: number
  y: number
  licensePlate: string
  occurredAt: string
}

export type VehicleCheckRequest = {
  vehicles: VehicleCheckItemRequest[]
}

// apiRequest가 공통 응답 래퍼를 벗기므로 data 내부 구조만 선언한다.
export type VehicleCheckResponse = {
  violations: {
    tempId: string
    eventId: number
  }[]
}

// POST /api/events/{eventId}/evidence (로봇 전용 증거자료 업로드)
export type EvidenceUploadRequest = {
  file: File
  mediaType: 'IMAGE' | 'VIDEO'
  capturedAt?: string
}

// apiRequest가 공통 응답 래퍼를 벗기므로 data 내부 구조만 선언한다.
export type EvidenceUploadResponse = {
  evidenceId: number
}


// 백엔드 enum 코드 (back/dev 기준)
export type PatrolStatusCode =
  | 'IN_PROGRESS'
  | 'STOP_REQUESTED'
  | 'COMPLETED'
  | 'STOPPED'
  | 'FAILED'
export type AiSummaryStatusCode = 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'FAILED'

// POST /api/patrols (순찰 기록 생성)
export type PatrolCreateRequest = {
  robotId: number
}

export type PatrolCreateResponse = {
  patrolId: number
  robotId: number
  patrolStatus: PatrolStatusCode
  startedAt: string
}

export type PatrolStopResponse = {
  patrolId: number
  robotId: number
  patrolStatus: PatrolStatusCode
}

// PATCH /api/patrols/{patrolId}/end (순찰 기록 종료)
export type PatrolEndRequest = {
  robotKey: string
  patrolStatus: PatrolStatusCode
  patrolEndedAt: string
  endBatteryLevel: number
  totalDuration: number
}

export type PatrolEndResponse = Record<string, never>

export type PatrolRouteCheckpointResponse = {
  checkpointId?: Id
  checkpointName: string
  sequence: number
}

// GET /api/patrols (목록)
export type PatrolListResponse = {
  patrolId: Id
  robotName: string
  startedAt: string
  endedAt?: string | null
  patrolStatus: PatrolStatusCode | string
  detectedEventCount: number
  route?: PatrolRouteCheckpointResponse[]
}

export type PatrolListPageResponse = {
  content: PatrolListResponse[]
  page: number
  size: number
  totalElements: number
  totalPages: number
  first: boolean
  last: boolean
}

export type PatrolBatteryResponse = {
  startLevel?: number | string | null
  endLevel?: number | string | null
}

export type PatrolRoutePointResponse = {
  xCoordinate: number | string
  yCoordinate: number | string
  recordedAt: string
}

// GET /api/patrols/{patrolId}/path
export type PatrolPathPointResponse = {
  positionId: Id
  xCoordinate: number | string
  yCoordinate: number | string
  recordedAt: string
}

export type PatrolPathResponse = {
  patrolId: Id
  path: PatrolPathPointResponse[]
}

export type PatrolTimelineResponse = {
  recordedAt: string
  checkpointName?: string | null
  eventId?: Id | null
  eventType?: EventTypeCode | string
  processingStatus?: ProcessingStatusCode | string
  xCoordinate?: number | string | null
  yCoordinate?: number | string | null
}

export type PatrolAiSummaryResponse = {
  generationStatus: AiSummaryStatusCode | string
  summaryContent?: string | null
}

// GET /api/patrols/{id} (상세) — 경로/배터리/좌표/타임라인/AI요약 포함, patrolId·robotId 없음
export type PatrolDetailResponse = {
  robotName: string
  patrolStatus: PatrolStatusCode | string
  startedAt: string
  endedAt?: string | null
  totalDurationMinutes?: number | null
  mapUrl?: string | null
  route?: PatrolRouteCheckpointResponse[]
  battery?: PatrolBatteryResponse
  routePoints?: PatrolRoutePointResponse[]
  timeline?: PatrolTimelineResponse[]
  aiSummary?: PatrolAiSummaryResponse | null
}

// 백엔드 enum 코드 (back/dev 기준)
export type RobotStatusCode =
  | 'IDLE'
  | 'PATROLLING'
  | 'CHARGING'
  | 'ERROR'
  | 'OFFLINE'
  | 'DELETED'
  | 'OBSTACLE_STOP'
  
export type SensorStatusCode = 'NORMAL' | 'NEEDS_INSPECTION' | 'ERROR' | 'DISCONNECTED'

// GET /api/robots (목록) — 축소형
export type RobotListResponse = {
  robotId: number
  robotName: string
  robotStatus: RobotStatusCode | string
  batteryLevel: number | null
  location: string | null
  activePatrolId?: number | null
}

export type RobotListPageResponse = {
  content: RobotListResponse[]
  page: number
  size: number
  totalElements: number
  totalPages: number
  first: boolean
  last: boolean
}

// GET /api/robots/{id} 의 recentPatrols 항목
export type RobotRecentPatrolResponse = {
  patrolId: number
  patrolStatus: string
  startedAt: string
  endedAt: string | null
  detectedEventCount: number
}

// GET /api/robots/{id} (상세)
export type RobotDetailResponse = {
  robotId: number
  robotName: string
  robotSerialNumber: string
  robotStatus: RobotStatusCode | string
  batteryLevel: number | null
  cameraStatus: SensorStatusCode | string | null
  lidarStatus: SensorStatusCode | string | null
  motorStatus: SensorStatusCode | string | null
  registeredAt: string
  weeklyOperationRate: number
  recentPatrols: RobotRecentPatrolResponse[]
}

// GET /api/robots/stats
export type RobotStatsResponse = {
  totalCount: number
  patrollingCount: number
  idleOrChargingCount: number
}

// POST /api/robots
export type RobotRegisterRequest = {
  name: string
  serialNumber: string
}
export type RobotRegisterResponse = {
  robotId: Id
  robotName: string
  robotSerialNumber: string
  robotStatus: RobotStatusCode | string
  registeredAt: string
}

// PATCH /api/robots/{id}
export type RobotUpdateRequest = {
  name: string
}
export type RobotUpdateResponse = {
  robotId: number
  robotName: string
  updatedAt: string
}

// DELETE /api/robots/{id}
export type RobotDeleteResponse = {
  robotId: number
  deletedAt: string
}

export type MappingStatusCode =
  | 'REQUESTED'
  | 'MAPPING'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED'

export type MappingStartResponse = {
  mappingSessionId: Id
  robotId: Id
  mappingStatus: MappingStatusCode
  createdAt: string
}

export type MappingStatusEventResponse = {
  mappingSessionId: Id
  status: MappingStatusCode
  mapId?: Id | null
}

export type MapDetailResponse = {
  mapId: Id
  mapName: string
  mapUrl: string
  resolution: number | string
  originX: number | string
  originY: number | string
  originYaw: number | string
  width: number
  height: number
  mapVersion: number
}

export type ZoneTypeCode =
  | 'START'
  | 'PARKING'
  | 'RECYCLING_AREA'
  | 'DANGER_ZONE'
  | 'DESTINATION'

export type ZoneCreateRequest = {
  name: string
  type: ZoneTypeCode
  startX: number
  startY: number
  endX: number
  endY: number
}

export type ZoneCreateResponse = {
  zoneId: Id
  name: string
  type: ZoneTypeCode
  minX: number | string
  minY: number | string
  maxX: number | string
  maxY: number | string
}

/** @deprecated Legacy dashboard mapper shape; no backend monitoring endpoint uses this contract. */
export type MapInfoResponse = {
  mapId: Id
  mapUrl: string
  resolution?: number | string | null
  originX?: number | string | null
  originY?: number | string | null
  width?: number | null
  height?: number | null
}

/** @deprecated Legacy dashboard mapper shape. */
export type ZoneResponse = {
  checkpointId: Id
  checkpointType: string
  checkpointLabel?: string | null
  minX: number | string
  minY: number | string
  maxX: number | string
  maxY: number | string
}

/** @deprecated Kept only until the location mapper is migrated to MapDetailResponse. */
export type MapRobotResponse = {
  robotId: Id
  robotName: string
  xCoordinate: number | string
  yCoordinate: number | string
  batteryLevel?: number | string | null
  updatedAt: string
}

/** @deprecated No backend endpoint returns this combined response. */
export type MapMonitoringResponse = {
  map: MapInfoResponse
  zones: ZoneResponse[]
  robot: MapRobotResponse
  currentPatrol?: {
    patrolId: Id
    patrolStatus: string
    patrolStartedAt: string
  } | null
}

export type RobotLocationEvent = {
  robotId: number
  x: number | null
  y: number | null
  heading: number | null
  locationUpdatedAt: string | null
}

// GET /api/robots/locations
export type RobotMapLocationResponse = RobotLocationEvent & {
  robotName: string
  status: RobotStatusCode | string
  routePoints: PatrolRoutePointResponse[]
}

export type RobotStatusUpdateEvent = {
  robotId: number
  status: RobotStatusCode | string
  batteryLevel: number | null
  statusReportedAt: string | null
}

export type PatrolCompletedSseEvent = {
  patrolId: number
  robotId: number
  robotName: string
  completedAt: string
}

export type EmergencyEventSseResponse = {
  eventId: number
  eventType: EventTypeCode
  title: string
  occurredAt: string
  location: string
  robotName: string
  riskLevel: RiskLevelCode
  processingStatus: ProcessingStatusCode
  mapId: number | null
  x: number | null
  y: number | null
}

// GET /api/robots/obstacle-events (SSE: robot-obstacle)
export type RobotObstacleEvent = {
  robotId: number
  status: 'STOP' | 'CLEAR'
  direction: string | null
  message: string | null
}

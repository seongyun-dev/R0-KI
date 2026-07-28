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

export type SignInResponse = {
  success: boolean,
  code: string,
  message: string,
  data: {
    accessToken: string
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
export type RiskLevelCode = 'LOW' | 'NORMAL' | 'EMERGENCY'
export type ProcessingStatusCode = 'DETECTED' | 'PROCESSING' | 'COMPLETED'
export type MediaTypeCode = 'IMAGE' | 'VIDEO' | string

export type EventEvidenceResponse = {
  mediaType: MediaTypeCode
  fileUrl: string
}

// GET /api/events (목록)
export type EventListResponse = {
  eventId: Id
  occurredAt: string
  type: EventTypeCode | string
  location?: string | null
  robotName: string
  riskLevel: RiskLevelCode | string
  status: ProcessingStatusCode | string
  assignee?: string | null
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

// 백엔드 enum 코드 (back/dev 기준)
export type PatrolStatusCode = 'IN_PROGRESS' | 'COMPLETED' | 'STOPPED' | 'FAILED'
export type AiSummaryStatusCode = 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'FAILED'

export type PatrolRouteCheckpointResponse = {
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

export type PatrolBatteryResponse = {
  startLevel?: number | string | null
  endLevel?: number | string | null
}

export type PatrolRoutePointResponse = {
  xCoordinate: number | string
  yCoordinate: number | string
  recordedAt: string
}

export type PatrolTimelineResponse = {
  recordedAt: string
  checkpointName?: string | null
  eventId?: Id | null
  eventType?: EventTypeCode | string
  processingStatus?: ProcessingStatusCode | string
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
  robotId: Id
  robotName: string
  robotStatus: RobotStatusCode | string
  batteryLevel?: number | string | null
  location?: string | null
}

// GET /api/robots/{id} 의 recentPatrols 항목
export type RobotRecentPatrolResponse = {
  patrolId: Id
  patrolStatus: string
  startedAt?: string | null
  endedAt?: string | null
  detectedEventCount: number
}

// GET /api/robots/{id} (상세)
export type RobotDetailResponse = {
  robotId: Id
  robotName: string
  robotSerialNumber: string
  robotStatus: RobotStatusCode | string
  batteryLevel?: number | string | null
  cameraStatus?: SensorStatusCode | string | null
  lidarStatus?: SensorStatusCode | string | null
  motorStatus?: SensorStatusCode | string | null
  registeredAt: string
  weeklyOperationRate?: number | string | null
  recentPatrols?: RobotRecentPatrolResponse[]
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
  robotId: Id
  robotName: string
  updatedAt: string
}

// DELETE /api/robots/{id}
export type RobotDeleteResponse = {
  robotId: Id
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
  robotId: Id
  robotName?: string
  xCoordinate: number | string
  yCoordinate: number | string
  batteryLevel?: number | string | null
  updatedAt?: string
  locationUpdatedAt?: string
}

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

export type SignInRequest = {
  username: string
  password: string
}

export type SignInResponse = {
  accessToken: string
  member?: {
    memberId?: Id
    username?: string
    name?: string
    role?: string
    apartmentComplexId?: Id
    mapId?: Id
    robotId?: Id
  }
  mapId?: Id
  robotId?: Id
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

export type PatrolReportResponse = {
  reportId: Id
  reportTitle: string
  patrolSummary?: string | null
  reportContent?: string | null
  totalEventCount: number
  emergencyEventCount: number
  anomalyComment?: string | null
  createdAt: string
}

export type PatrolResponse = {
  patrolId: Id
  robotId: Id
  patrolStatus: string
  patrolStartedAt?: string | null
  patrolEndedAt?: string | null
  totalDuration?: number | null
  detectedEventCount: number
  batteryFrom?: number | string | null
  batteryTo?: number | string | null
  report?: PatrolReportResponse | null
}

export type PatrolPathPointResponse = {
  positionId?: Id
  checkpointId?: Id | null
  checkpointLabel?: string | null
  eventId?: Id | null
  eventType?: string | null
  processingStatus?: string | null
  note?: string | null
  xCoordinate: number | string
  yCoordinate: number | string
  recordedAt: string
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

export type MapInfoResponse = {
  mapId: Id
  mapUrl: string
  resolution?: number | string | null
  originX?: number | string | null
  originY?: number | string | null
  width?: number | null
  height?: number | null
}

export type ZoneResponse = {
  checkpointId: Id
  checkpointType: string
  checkpointLabel?: string | null
  minX: number | string
  minY: number | string
  maxX: number | string
  maxY: number | string
}

export type MapRobotResponse = {
  robotId: Id
  robotName: string
  xCoordinate: number | string
  yCoordinate: number | string
  batteryLevel?: number | string | null
  updatedAt: string
}

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

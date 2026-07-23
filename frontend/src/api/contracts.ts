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

export type EvidenceResponse = {
  evidenceId: Id
  fileUrl: string
  mediaType: '이미지' | '영상' | string
  capturedAt?: string | null
}

export type EventResponse = {
  eventId: Id
  patrolId?: Id | null
  robotId: Id
  checkpointId?: Id | null
  checkpointLabel?: string | null
  locationLabel?: string | null
  eventType: string
  eventTitle: string
  eventDetails?: string | null
  occurredAt: string
  xCoordinate?: number | string | null
  yCoordinate?: number | string | null
  riskLevel: string
  processingStatus: string
  processedAt?: string | null
  createdAt: string
  detectionConfidence?: number | string | null
  processingNote?: string | null
  evidences?: EvidenceResponse[]
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

export type RobotPartResponse = {
  name: string
  status: string
}

export type RobotResponse = {
  robotId: Id
  robotName: string
  robotSerialNumber: string
  registrationCode?: string | null
  model?: string | null
  assignedZone?: string | null
  currentLocationLabel?: string | null
  robotStatus: string
  batteryLevel?: number | string | null
  xCoordinate?: number | string | null
  yCoordinate?: number | string | null
  locationUpdatedAt?: string | null
  lastConnectedAt?: string | null
  registeredAt: string
  odometerKm?: number | string | null
  weeklyUptime?: number | string | null
  parts?: RobotPartResponse[]
  lastPatrol?: {
    patrolId?: Id
    startedAt?: string | null
    endedAt?: string | null
  } | null
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

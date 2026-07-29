import { env } from '../config/env'
import { apiBlob, apiRequest, consumeSse, jsonBody } from './client'
import type {
  ComplexResponse,
  EventBatchCreateRequest,
  EventBatchCreateResponse,
  EventDetailResponse,
  EvidenceUploadRequest,
  EvidenceUploadResponse,
  EventListRequest,
  EventListResponse,
  EventNotificationResponse,
  EventStatusChangeRequest,
  EventStatusChangeResponse,
  EventStatusHistoryItemResponse,
  ListResponse,
  MapDetailResponse,
  MappingStartResponse,
  MappingStatusEventResponse,
  NotificationHistoryItemResponse,
  PatrolCreateRequest,
  PatrolCreateResponse,
  PatrolDetailResponse,
  PatrolEndRequest,
  PatrolEndResponse,
  PatrolListPageResponse,
  PatrolPathResponse,
  RobotDeleteResponse,
  RobotDetailResponse,
  RobotListPageResponse,
  RobotLocationEvent,
  RobotObstacleEvent,
  RobotRegisterRequest,
  RobotRegisterResponse,
  RobotStatsResponse,
  RobotUpdateRequest,
  RobotUpdateResponse,
  SignInRequest,
  SignInResponse,
  SignUpRequest,
  SignUpResponse,
  VehicleCheckRequest,
  VehicleCheckResponse,
  ZoneCreateRequest,
  ZoneCreateResponse,
} from './contracts'

export function unwrapList<T>(response: ListResponse<T>): T[] {
  if (Array.isArray(response)) return response
  return response.content ?? response.items ?? response.data ?? []
}

function withQuery(path: string, params: Record<string, string | number | undefined>) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '' && value !== 'all') query.set(key, String(value))
  })
  const suffix = query.toString()
  return suffix ? `${path}?${suffix}` : path
}

export const authApi = {
  signIn: (request: SignInRequest) =>
    apiRequest<SignInResponse['data']>('/api/auth/signin', {
      method: 'POST',
      body: jsonBody(request),
    }),
  signUp: (request: SignUpRequest) =>
    apiRequest<SignUpResponse['data']>('/api/auth/signup', {
      method: 'POST',
      body: jsonBody(request),
    }),
  searchComplexes: (keyword: string) =>
    apiRequest<ListResponse<ComplexResponse>>(
      `/api/auth/apartment-complexes?keyword=${encodeURIComponent(keyword)}`,
    ).then(unwrapList),
}

export const eventsApi = {
  // 백엔드 GET /api/events 쿼리: type / status / period (+ page,size,sort). 위험도 필터는 미지원.
  list: (request: EventListRequest = {}) => {
    const query = new URLSearchParams()
    const { sort, ...filters } = request

    Object.entries(filters).forEach(([key, value]) => {
      if (value !== undefined) query.set(key, String(value))
    })
    sort?.forEach((value) => query.append('sort', value))

    const suffix = query.toString()
    return apiRequest<EventListResponse>(suffix ? `/api/events?${suffix}` : '/api/events')
  },
  
  detail: (eventId: string | number) =>
    apiRequest<EventDetailResponse>(`/api/events/${encodeURIComponent(eventId)}`),

  updateStatus: (eventId: string | number, request: EventStatusChangeRequest) =>
    apiRequest<EventStatusChangeResponse>(`/api/events/${encodeURIComponent(eventId)}/status`, {
      method: 'PATCH',
      body: jsonBody(request),
    }),

  getStatusHistory: (eventId: string | number) =>
    apiRequest<EventStatusHistoryItemResponse[]>(
      `/api/events/${encodeURIComponent(String(eventId))}/history`,
    ),
  notify: (eventId: string | number) =>
    apiRequest<EventNotificationResponse>(
      `/api/events/${encodeURIComponent(String(eventId))}/notify`,
      {
        method: 'POST',
      },
    ),
}

export const robotEventsApi = {
  createBatch: (robotServiceToken: string, request: EventBatchCreateRequest) =>
    apiRequest<EventBatchCreateResponse>('/api/robot/events/batch', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${robotServiceToken}`,
      },
      body: jsonBody(request),
    }),
  checkVehicles: (robotServiceToken: string, request: VehicleCheckRequest) =>
    apiRequest<VehicleCheckResponse>('/api/robot/vehicle-checks', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${robotServiceToken}`,
      },
      body: jsonBody(request),
    }),
  uploadEvidence: (
    robotServiceToken: string,
    eventId: string | number,
    request: EvidenceUploadRequest,
  ) => {
    const formData = new FormData()
    formData.append('file', request.file)
    formData.append('mediaType', request.mediaType)
    if (request.capturedAt) formData.append('capturedAt', request.capturedAt)

    return apiRequest<EvidenceUploadResponse>(
      `/api/events/${encodeURIComponent(String(eventId))}/evidence`,
      {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${robotServiceToken}`,
        },
        body: formData,
      },
    )
  },
}

export const notificationsApi = {
  list: () =>
    apiRequest<NotificationHistoryItemResponse[]>('/api/notifications'),
}

export const patrolsApi = {
  create: (request: PatrolCreateRequest) =>
    apiRequest<PatrolCreateResponse>('/api/patrols', {
      method: 'POST',
      body: jsonBody(request),
    }),
  end: (patrolId: string | number, request: PatrolEndRequest) =>
    apiRequest<PatrolEndResponse>(
      `/api/patrols/${encodeURIComponent(String(patrolId))}/end`,
      {
        method: 'PATCH',
        body: jsonBody(request),
      },
    ),
  // 백엔드 GET /api/patrols 쿼리: period / status (+ page,size,sort). robotId 필터는 미지원.
  list: (
    params: {
      period?: string
      status?: string
      page?: number
      size?: number
      sort?: string[]
    } = {},
  ) => {
    const query = new URLSearchParams()
    const { sort, ...filters } = params

    Object.entries(filters).forEach(([key, value]) => {
      if (value !== undefined && value !== '' && value !== 'all') {
        query.set(key, String(value))
      }
    })
    sort?.forEach((value) => query.append('sort', value))

    const suffix = query.toString()
    return apiRequest<PatrolListPageResponse>(
      suffix ? `/api/patrols?${suffix}` : '/api/patrols',
    )
  },
  // 상세 응답에 경로·타임라인이 포함됨(별도 /path 엔드포인트 없음)
  detail: (patrolId: string | number) =>
    apiRequest<PatrolDetailResponse>(`/api/patrols/${encodeURIComponent(patrolId)}`),
  path: (patrolId: string | number) =>
    apiRequest<PatrolPathResponse>(
      `/api/patrols/${encodeURIComponent(String(patrolId))}/path`,
    ),
}

export const robotsApi = {
  list: (params: { page?: number; size?: number; sort?: string[] } = {}) => {
    const query = new URLSearchParams()
    const { sort, ...pagination } = params

    Object.entries(pagination).forEach(([key, value]) => {
      if (value !== undefined) query.set(key, String(value))
    })
    sort?.forEach((value) => query.append('sort', value))

    const suffix = query.toString()
    return apiRequest<RobotListPageResponse>(
      suffix ? `/api/robots?${suffix}` : '/api/robots',
    )
  },
  stats: () => apiRequest<RobotStatsResponse>('/api/robots/stats'),
  detail: (robotId: string | number) =>
    apiRequest<RobotDetailResponse>(`/api/robots/${encodeURIComponent(robotId)}`),
  create: (request: RobotRegisterRequest) =>
    apiRequest<RobotRegisterResponse>('/api/robots', {
      method: 'POST',
      body: jsonBody(request),
    }),
  update: (robotId: string | number, request: RobotUpdateRequest) =>
    apiRequest<RobotUpdateResponse>(`/api/robots/${encodeURIComponent(robotId)}`, {
      method: 'PATCH',
      body: jsonBody(request),
    }),
  delete: (robotId: string | number) =>
    apiRequest<RobotDeleteResponse>(`/api/robots/${encodeURIComponent(robotId)}`, {
      method: 'DELETE',
    }),
  subscribeLocations: (
    onInitial: (locations: RobotLocationEvent[]) => void,
    onLocation: (location: RobotLocationEvent) => void,
    signal: AbortSignal,
  ) =>
    consumeSse<RobotLocationEvent[] | RobotLocationEvent>(
      '/api/robots/location/events',
      (data, eventName) => {
        if (eventName === 'robot-location-initial' && Array.isArray(data)) {
          onInitial(data)
        } else if (eventName === 'robot-location' && !Array.isArray(data)) {
          onLocation(data)
        }
      },
      signal,
    ),
  subscribeObstacleEvents: (
    onObstacle: (event: RobotObstacleEvent) => void,
    signal: AbortSignal,
  ) =>
    consumeSse<RobotObstacleEvent>(
      '/api/robots/obstacle-events',
      (data, eventName) => {
        if (eventName === 'robot-obstacle') onObstacle(data)
      },
      signal,
    ),
}

export const mapApi = {
  startMapping: (robotId: string | number) =>
    apiRequest<MappingStartResponse>('/api/map/mapping-sessions', {
      method: 'POST',
      body: jsonBody({ robotId }),
    }),
  subscribeMapping: (
    mappingSessionId: string | number,
    onMessage: (data: MappingStatusEventResponse) => void,
    signal: AbortSignal,
  ) =>
    consumeSse<MappingStatusEventResponse>(
      `/api/map/mapping-sessions/${encodeURIComponent(mappingSessionId)}/events`,
      onMessage,
      signal,
    ),
  detail: (mapId: string | number) =>
    apiRequest<MapDetailResponse>(`/api/map/${encodeURIComponent(mapId)}`),
  file: (mapUrl: string, signal?: AbortSignal) => apiBlob(mapUrl, signal),
  registerZones: (mapId: string | number, zones: ZoneCreateRequest[]) =>
    apiRequest<ZoneCreateResponse[]>(`/api/map/${encodeURIComponent(mapId)}/zones`, {
      method: 'POST',
      body: jsonBody({ zones }),
    }),
  zones: (mapId: string | number) =>
    apiRequest<ZoneCreateResponse[]>(`/api/map/${encodeURIComponent(mapId)}/zones`),
}

export const statsApi = {
  get: (params: { period?: string; zone?: string } = {}) =>
    apiRequest<unknown>(withQuery(env.statsEndpoint, params)),
}

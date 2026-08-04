import { apiBlob, apiRequest, consumeSse, jsonBody } from './client'
import type {
  AnalyticsByZoneResponse,
  AnalyticsHandlingResponse,
  AnalyticsInsightPeriodType,
  AnalyticsInsightResponse,
  AnalyticsOverviewResponse,
  AnalyticsTrendResponse,
} from './analyticsContracts'
import type {
  ComplexResponse,
  EventBatchCreateRequest,
  EventBatchCreateResponse,
  EventDetailResponse,
  EmergencyEventSseResponse,
  EvidenceUploadRequest,
  EvidenceUploadResponse,
  EventListRequest,
  EventListResponse,
  EventNotificationResponse,
  EventStatusChangeRequest,
  EventStatusChangeResponse,
  ListResponse,
  MapDetailResponse,
  MappingStartResponse,
  MappingStatusEventResponse,
  NavigationWaypointsReplaceRequest,
  NavigationWaypointsResponse,
  NotificationDetailResponse,
  NotificationHistoryResponse,
  PatrolCreateRequest,
  PatrolCreateResponse,
  PatrolStopResponse,
  PatrolCompletedSseEvent,
  PatrolDetailResponse,
  PatrolEndRequest,
  PatrolEndResponse,
  PatrolListPageResponse,
  PatrolPathResponse,
  RobotDeleteResponse,
  RobotDetailResponse,
  RobotListPageResponse,
  RobotLocationEvent,
  RobotMapLocationResponse,
  RobotStatusUpdateEvent,
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
  ZoneCreateResponse,
  ZoneReplaceRequest,
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

  evidenceFile: (fileUrl: string, signal?: AbortSignal) => apiBlob(fileUrl, signal),

  updateStatus: (eventId: string | number, request: EventStatusChangeRequest) =>
    apiRequest<EventStatusChangeResponse>(`/api/events/${encodeURIComponent(eventId)}/status`, {
      method: 'PATCH',
      body: jsonBody(request),
    }),

  notify: (eventId: string | number) =>
    apiRequest<EventNotificationResponse>(
      `/api/events/${encodeURIComponent(String(eventId))}/notify`,
      {
        method: 'POST',
      },
    ),
  subscribeEmergency: (
    onEmergency: (event: EmergencyEventSseResponse) => void,
    signal: AbortSignal,
  ) =>
    consumeSse<EmergencyEventSseResponse | string>(
      '/api/events/subscribe/emergency',
      (data, eventName) => {
        if (eventName === 'emergency-event' && typeof data === 'object') {
          onEmergency(data)
        }
      },
      signal,
    ),
  subscribeGeneral: (
    onPatrolCompleted: (event: PatrolCompletedSseEvent) => void,
    signal: AbortSignal,
  ) =>
    consumeSse<PatrolCompletedSseEvent | string>(
      '/api/events/subscribe/general',
      (data, eventName) => {
        if (eventName === 'patrol-completed' && typeof data === 'object') {
          onPatrolCompleted(data)
        }
      },
      signal,
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
    apiRequest<NotificationHistoryResponse>('/api/notifications'),
  detail: (notificationId: number) =>
    apiRequest<NotificationDetailResponse>(
      `/api/notifications/${encodeURIComponent(String(notificationId))}`,
    ),
}

export const patrolsApi = {
  start: (request: PatrolCreateRequest) =>
    apiRequest<PatrolCreateResponse>('/api/patrols', {
      method: 'POST',
      body: jsonBody(request),
    }),
  stop: (patrolId: string | number) =>
    apiRequest<PatrolStopResponse>(
      `/api/patrols/${encodeURIComponent(String(patrolId))}/stop`,
      { method: 'POST' },
    ),
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
  downloadPdf: (patrolId: string | number, signal?: AbortSignal) =>
    apiBlob(`/api/patrols/${encodeURIComponent(String(patrolId))}/pdf`, signal),
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
  locations: () =>
    apiRequest<RobotMapLocationResponse[]>('/api/robots/locations'),
  location: (robotId: string | number) =>
    apiRequest<RobotMapLocationResponse>(
      `/api/robots/${encodeURIComponent(String(robotId))}/location`,
    ),
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
    onStatus: (status: RobotStatusUpdateEvent) => void,
    signal: AbortSignal,
  ) =>
    consumeSse<RobotLocationEvent[] | RobotLocationEvent | RobotStatusUpdateEvent>(
      '/api/robots/location/events',
      (data, eventName) => {
        if (eventName === 'robot-location-initial' && Array.isArray(data)) {
          onInitial(data)
        } else if (eventName === 'robot-location-updated' && !Array.isArray(data)) {
          onLocation(data as RobotLocationEvent)
        } else if (eventName === 'robot-status-updated' && !Array.isArray(data)) {
          onStatus(data as RobotStatusUpdateEvent)
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
  replaceZones: (mapId: string | number, request: ZoneReplaceRequest) =>
    apiRequest<ZoneCreateResponse[]>(`/api/map/${encodeURIComponent(mapId)}/zones`, {
      method: 'PUT',
      body: jsonBody(request),
    }),
  zones: (mapId: string | number) =>
    apiRequest<ZoneCreateResponse[]>(`/api/map/${encodeURIComponent(mapId)}/zones`),
  waypoints: (mapId: string | number) =>
    apiRequest<NavigationWaypointsResponse>(
      `/api/map/${encodeURIComponent(mapId)}/waypoints`,
    ),
  replaceWaypoints: (
    mapId: string | number,
    request: NavigationWaypointsReplaceRequest,
  ) =>
    apiRequest<NavigationWaypointsResponse>(
      `/api/map/${encodeURIComponent(mapId)}/waypoints`,
      {
        method: 'PUT',
        body: jsonBody(request),
      },
    ),
}

export const statsApi = {
  /**
   * 드롭다운 구역 키(parking/recycle/danger)를 by-zone 결과의 zoneId 목록으로 변환한다.
   *
   * <p>백엔드는 checkpoint_type 필터 파라미터가 아직 없으므로,
   * 1차는 zoneName 키워드 매칭으로 zoneIds를 만든 뒤 기존 zoneIds 필터 API를 재사용한다.
   * (예: parking -> "주차", recycle -> "분리수거", danger -> "위험")
   */
  resolveZoneIds: (
    byZone: AnalyticsByZoneResponse,
    zone: string,
  ): number[] | undefined => {
    if (!zone || zone === 'all') return undefined
    const keywordByZone: Record<string, string> = {
      parking: '주차',
      recycle: '분리수거',
      danger: '위험',
    }
    const keyword = keywordByZone[zone]
    if (!keyword) return undefined
    const ids = (byZone.items ?? [])
      .filter((item) => item.zoneName?.includes(keyword))
      .map((item) => item.zoneId)
    return ids.length > 0 ? ids : undefined
  },

  /**
   * 통계 대시보드용 Analytics API 묶음 호출.
   *
   * 예전 단일 `/api/statistics` 가정은 폐기하고,
   * 백엔드 확정 엔드포인트 4(+trend 2회)를 병렬로 부른 뒤
   * assembleStatsDashboard 매퍼가 Stats 화면 형태로 합친다.
   *
   * @param range resolveAnalyticsRange() 결과 (from/to, +09:00)
   * @param zone 구역 드롭다운 값. parking/recycle/danger를 zoneIds로 변환해 함께 적용한다.
   * @param options.trendBucket 추이 버킷. 연간은 month, 그 외 day.
   */
  fetchDashboard: async (
    range: { from: string; to: string },
    zone?: string,
    options?: { trendBucket?: 'day' | 'week' | 'month' },
  ) => {
    const trendBucket = options?.trendBucket ?? 'day'
    const base = {
      from: range.from,
      to: range.to,
    }
    // 1) 기간 필터만 적용된 by-zone을 먼저 조회해 zoneId 후보를 얻는다.
    //    이후 구역 선택값을 zoneIds로 변환해 나머지 API에 공통 적용한다.
    const byZoneAll = await apiRequest<AnalyticsByZoneResponse>(
      withQuery('/api/analytics/events/by-zone', base),
    )
    const zoneIds = statsApi.resolveZoneIds(byZoneAll, zone ?? 'all')
    const zoneIdsCsv = zoneIds?.join(',')
    const scoped = { ...base, zoneIds: zoneIdsCsv }

    const [overview, dailyTrend, hourlyTrend, handling] = await Promise.all([
      // KPI: 순찰수·이벤트·평균처리시간 + 증감
      apiRequest<AnalyticsOverviewResponse>(
        withQuery('/api/analytics/events/overview', { ...scoped, compare: 'true' }),
      ),
      // 추이 차트 (주·월·분기는 day, 올해는 month)
      apiRequest<AnalyticsTrendResponse>(
        withQuery('/api/analytics/events/trend', { ...scoped, bucket: trendBucket }),
      ),
      // 시간대×유형 차트 (3시간×8칸)
      apiRequest<AnalyticsTrendResponse>(
        withQuery('/api/analytics/events/trend', { ...scoped, bucket: 'hour3' }),
      ),
      // 처리/미처리 현황
      apiRequest<AnalyticsHandlingResponse>(
        withQuery('/api/analytics/events/handling', scoped),
      ),
    ])

    // 2) by-zone은 백엔드 zoneIds 필터가 없어 프론트에서 동일 zoneIds로 후필터한다.
    //    이렇게 하면 "기간 + 구역" 조건이 모든 패널에 동일하게 적용된다.
    const byZone =
      zoneIds && zoneIds.length > 0
        ? {
            ...byZoneAll,
            items: byZoneAll.items.filter((item) => zoneIds.includes(item.zoneId)),
          }
        : byZoneAll

    return [overview, dailyTrend, hourlyTrend, handling, byZone] as const
  },

  /**
   * 직전 완료 주/월 AI 인사이트 리포트 조회.
   *
   * 없거나 FAILED 면 백엔드가 비동기 생성을 트리거한다.
   * PENDING/PROCESSING 이면 폴링으로 COMPLETED/FAILED 까지 재조회한다.
   */
  fetchInsight: (periodType: AnalyticsInsightPeriodType) =>
    apiRequest<AnalyticsInsightResponse>(
      withQuery('/api/analytics/insights', { periodType }),
    ),
}

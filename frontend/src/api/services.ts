import { env } from '../config/env'
import { apiBlob, apiRequest, consumeSse, jsonBody } from './client'
import type {
  ComplexResponse,
  EventDetailResponse,
  EventListResponse,
  ListResponse,
  MapDetailResponse,
  MappingStartResponse,
  MappingStatusEventResponse,
  PatrolDetailResponse,
  PatrolListResponse,
  RobotDeleteResponse,
  RobotDetailResponse,
  RobotListResponse,
  RobotLocationEvent,
  RobotRegisterRequest,
  RobotRegisterResponse,
  RobotStatsResponse,
  RobotUpdateRequest,
  RobotUpdateResponse,
  SignInRequest,
  SignInResponse,
  SignUpRequest,
  SignUpResponse,
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
  list: (params: { type?: string; status?: string; period?: string } = {}) =>
    apiRequest<ListResponse<EventListResponse>>(withQuery('/api/events', params)).then(unwrapList),
  detail: (eventId: string | number) =>
    apiRequest<EventDetailResponse>(`/api/events/${encodeURIComponent(eventId)}`),
  updateStatus: (eventId: string | number, processingStatus: string, processingNote?: string) =>
    apiRequest<unknown>(`/api/events/${encodeURIComponent(eventId)}/status`, {
      method: 'PATCH',
      body: jsonBody({ processingStatus, processingNote }),
    }),
  // 긴급 이벤트 실시간 수신 (SSE) — 엔드포인트/페이로드 스키마 백엔드 확정 필요
  subscribeEmergency: (onMessage: (data: EventListResponse) => void, signal: AbortSignal) =>
    consumeSse<EventListResponse>('/api/events/emergency/stream', onMessage, signal),
}

export const patrolsApi = {
  // 백엔드 GET /api/patrols 쿼리: period / status (+ page,size,sort). robotId 필터는 미지원.
  list: (params: { period?: string; status?: string } = {}) =>
    apiRequest<ListResponse<PatrolListResponse>>(withQuery('/api/patrols', params)).then(unwrapList),
  // 상세 응답에 경로·타임라인이 포함됨(별도 /path 엔드포인트 없음)
  detail: (patrolId: string | number) =>
    apiRequest<PatrolDetailResponse>(`/api/patrols/${encodeURIComponent(patrolId)}`),
}

export const robotsApi = {
  list: () => apiRequest<ListResponse<RobotListResponse>>('/api/robots').then(unwrapList),
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
  subscribeRobotLocation: (
    robotId: string | number,
    onMessage: (data: RobotLocationEvent) => void,
    signal: AbortSignal,
  ) =>
    consumeSse<RobotLocationEvent>(
      `/api/robots/${encodeURIComponent(robotId)}/location/events`,
      onMessage,
      signal,
    ),
}

export const statsApi = {
  get: (params: { period?: string; zone?: string } = {}) =>
    apiRequest<unknown>(withQuery(env.statsEndpoint, params)),
}

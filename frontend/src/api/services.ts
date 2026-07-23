import { env } from '../config/env'
import { apiRequest, consumeSse, jsonBody } from './client'
import type {
  ComplexResponse,
  EventResponse,
  ListResponse,
  MapMonitoringResponse,
  PatrolPathPointResponse,
  PatrolResponse,
  RobotLocationEvent,
  RobotResponse,
  SignInRequest,
  SignInResponse,
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
    apiRequest<SignInResponse>('/api/auth/signin', {
      method: 'POST',
      body: jsonBody(request),
    }),
  signUp: (request: unknown) =>
    apiRequest<unknown>('/api/auth/signup', {
      method: 'POST',
      body: jsonBody(request),
    }),
  initialSignUp: (request: unknown) =>
    apiRequest<SignInResponse>('/api/auth/initial-signup', {
      method: 'POST',
      body: jsonBody(request),
    }),
  searchComplexes: (keyword: string) =>
    apiRequest<ListResponse<ComplexResponse>>(
      `/api/auth/apartment-complexes?keyword=${encodeURIComponent(keyword)}`,
    ).then(unwrapList),
}

export const eventsApi = {
  list: (params: { eventType?: string; processingStatus?: string; period?: string } = {}) =>
    apiRequest<ListResponse<EventResponse>>(withQuery('/api/events', params)).then(unwrapList),
  detail: (eventId: string | number) =>
    apiRequest<EventResponse>(`/api/events/${encodeURIComponent(eventId)}`),
  updateStatus: (eventId: string | number, processingStatus: string, processingNote?: string) =>
    apiRequest<unknown>(`/api/events/${encodeURIComponent(eventId)}/status`, {
      method: 'PATCH',
      body: jsonBody({ processingStatus, processingNote }),
    }),
}

export const patrolsApi = {
  list: (params: { robotId?: string | number; period?: string; status?: string } = {}) =>
    apiRequest<ListResponse<PatrolResponse>>(withQuery('/api/patrols', params)).then(unwrapList),
  detail: (patrolId: string | number) =>
    apiRequest<PatrolResponse>(`/api/patrols/${encodeURIComponent(patrolId)}`),
  path: (patrolId: string | number) =>
    apiRequest<ListResponse<PatrolPathPointResponse>>(
      `/api/patrols/${encodeURIComponent(patrolId)}/path`,
    ).then(unwrapList),
}

export const robotsApi = {
  list: () => apiRequest<ListResponse<RobotResponse>>('/api/robots').then(unwrapList),
  detail: (robotId: string | number) =>
    apiRequest<RobotResponse>(`/api/robots/${encodeURIComponent(robotId)}`),
  create: (request: unknown) =>
    apiRequest<RobotResponse>('/api/robots', {
      method: 'POST',
      body: jsonBody(request),
    }),
  update: (robotId: string | number, request: unknown) =>
    apiRequest<RobotResponse>(`/api/robots/${encodeURIComponent(robotId)}`, {
      method: 'PATCH',
      body: jsonBody(request),
    }),
}

export const mapApi = {
  monitoring: (mapId: string | number, robotId: string | number) =>
    apiRequest<MapMonitoringResponse>(
      `/api/map/${encodeURIComponent(mapId)}/monitoring?robotId=${encodeURIComponent(robotId)}`,
    ),
  registerZones: (mapId: string | number, zones: unknown[]) =>
    apiRequest<unknown>(`/api/map/${encodeURIComponent(mapId)}/zones`, {
      method: 'POST',
      body: jsonBody({ zones }),
    }),
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

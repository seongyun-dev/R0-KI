import { env } from '../config/env'
import { useAuthStore } from '../features/auth/useAuthStore'

export class ApiError extends Error {
  status: number
  body: unknown

  constructor(status: number, message: string, body?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

export function apiUrl(path: string) {
  if (/^https?:\/\//.test(path)) return path
  const normalized = path.startsWith('/') ? path : `/${path}`
  return `${env.apiBaseUrl}${normalized}`
}

function authHeaders() {
  const state = useAuthStore.getState()
  const isValid =
    state.accessToken != null &&
    state.accessTokenExpiresAt != null &&
    state.accessTokenExpiresAt > Date.now()

  if (!isValid) {
    if (state.accessToken) state.logout()
    return undefined
  }
  return { Authorization: `Bearer ${state.accessToken}` }
}

export async function authenticatedFetch(path: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers)
  const auth = authHeaders()
  if (auth) {
    if (!headers.has('Authorization')) headers.set('Authorization', auth.Authorization)
    // Nginx auth_request 서브요청은 영상 전용 헤더를 백엔드 Authorization으로 변환한다.
    if (!headers.has('X-Live-Authorization')) {
      headers.set('X-Live-Authorization', auth.Authorization)
    }
  }

  const response = await fetch(apiUrl(path), { ...init, headers })
  return response
}

async function readResponse(response: Response) {
  if (response.status === 204) return undefined
  const contentType = response.headers.get('content-type') ?? ''
  if (contentType.includes('application/json')) return response.json()
  const text = await response.text()
  return text || undefined
}

// 백엔드 공통 응답 래퍼(ApiResponse<T> = { success, code, message, data })를 벗긴다.
// 래퍼 형태가 아니면(구버전/외부 응답) 원본을 그대로 반환한다.
function unwrapEnvelope(body: unknown): unknown {
  if (
    body &&
    typeof body === 'object' &&
    !Array.isArray(body) &&
    'success' in body &&
    'data' in body
  ) {
    return (body as { data: unknown }).data
  }
  return body
}

const ERROR_MESSAGES_BY_CODE: Record<string, string> = {
  AUTH_001: '로그인이 필요합니다.',
  AUTH_002: '요청을 수행할 권한이 없습니다.',
  AUTH_003: '아이디 또는 비밀번호가 올바르지 않습니다.',
  AUTH_004: '사용할 수 없는 계정입니다.',
  AUTH_005: '이미 사용 중인 아이디입니다.',
  COMMON_001: '입력값을 확인해 주세요.',
  COMMON_002: '요청 형식이 올바르지 않습니다.',
  COMMON_003: '요청한 정보를 찾을 수 없습니다.',
  ROBOT_001: '로봇을 찾을 수 없습니다.',
  ROBOT_002: '이미 등록된 시리얼 번호입니다.',
}

function apiErrorMessage(status: number, body: unknown) {
  const code =
    typeof body === 'object' && body && 'code' in body
      ? String((body as { code: unknown }).code)
      : undefined

  if (code && ERROR_MESSAGES_BY_CODE[code]) return ERROR_MESSAGES_BY_CODE[code]
  if (status === 400) return '요청 내용을 확인해 주세요.'
  if (status === 401) return '로그인이 필요합니다.'
  if (status === 403) return '요청을 수행할 권한이 없습니다.'
  if (status === 404) return '요청한 정보를 찾을 수 없습니다.'
  if (status === 409) return '현재 상태에서는 요청을 처리할 수 없습니다.'
  if (status >= 500) return '서버에 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.'
  return `요청을 처리하지 못했습니다. (${status})`
}

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const isFormData = init.body instanceof FormData
  const headers = new Headers(init.headers)
  headers.set('Accept', 'application/json')
  if (!isFormData && init.body) headers.set('Content-Type', 'application/json')
  const auth = authHeaders()
  if (auth && !headers.has('Authorization')) headers.set('Authorization', auth.Authorization)
  const response = await fetch(apiUrl(path), {
    ...init,
    headers,
  })
  const body = await readResponse(response)

  if (!response.ok) {
    if (response.status === 401) useAuthStore.getState().logout()
    throw new ApiError(response.status, apiErrorMessage(response.status, body), body)
  }

  return unwrapEnvelope(body) as T
}

export async function apiBlob(path: string, signal?: AbortSignal): Promise<Blob> {
  const headers = new Headers()
  const auth = authHeaders()
  if (auth) headers.set('Authorization', auth.Authorization)
  const response = await fetch(apiUrl(path), { headers, signal })
  if (!response.ok) {
    if (response.status === 401) useAuthStore.getState().logout()
    throw new ApiError(response.status, `이미지를 불러오지 못했습니다 (${response.status})`)
  }
  return response.blob()
}

export async function consumeSse<T>(
  path: string,
  onMessage: (data: T, eventName?: string) => void,
  signal: AbortSignal,
) {
  const headers = new Headers({ Accept: 'text/event-stream' })
  const auth = authHeaders()
  if (auth) headers.set('Authorization', auth.Authorization)
  const response = await fetch(apiUrl(path), {
    headers,
    signal,
  })
  if (!response.ok || !response.body) {
    if (response.status === 401) useAuthStore.getState().logout()
    throw new ApiError(response.status, `실시간 연결에 실패했습니다 (${response.status})`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (!signal.aborted) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')

    let boundary = buffer.indexOf('\n\n')
    while (boundary >= 0) {
      const block = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)
      const eventName = block
        .split('\n')
        .find((line) => line.startsWith('event:'))
        ?.slice(6)
        .trim()
      const payload = block
        .split('\n')
        .filter((line) => line.startsWith('data:'))
        .map((line) => line.slice(5).trimStart())
        .join('\n')
      if (payload) {
        try {
          onMessage(JSON.parse(payload) as T, eventName)
        } catch {
          // 서버 heartbeat 또는 JSON이 아닌 SSE 데이터는 화면 상태에 반영하지 않는다.
        }
      }
      boundary = buffer.indexOf('\n\n')
    }
  }
}

export function jsonBody(value: unknown) {
  return JSON.stringify(value)
}

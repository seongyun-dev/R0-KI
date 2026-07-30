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
  const token = useAuthStore.getState().accessToken
  return token ? { Authorization: `Bearer ${token}` } : undefined
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
    const message =
      typeof body === 'object' && body && 'message' in body
        ? String((body as { message: unknown }).message)
        : `요청에 실패했습니다 (${response.status})`
    throw new ApiError(response.status, message, body)
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

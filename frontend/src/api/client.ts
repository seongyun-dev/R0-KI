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

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const isFormData = init.body instanceof FormData
  const headers = new Headers(init.headers)
  headers.set('Accept', 'application/json')
  if (!isFormData && init.body) headers.set('Content-Type', 'application/json')
  const auth = authHeaders()
  if (auth) headers.set('Authorization', auth.Authorization)
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

  return body as T
}

export async function consumeSse<T>(
  path: string,
  onMessage: (data: T) => void,
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
      const payload = block
        .split('\n')
        .filter((line) => line.startsWith('data:'))
        .map((line) => line.slice(5).trimStart())
        .join('\n')
      if (payload) {
        try {
          onMessage(JSON.parse(payload) as T)
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

import { useEffect, useState } from 'react'
import { apiRequest, apiUrl } from '../../api/client'

export type MjpegStreamState = 'idle' | 'connecting' | 'live' | 'offline'

const MAX_BUFFER_BYTES = 2 * 1024 * 1024
const FIRST_FRAME_TIMEOUT_MS = 12_000
const NEXT_FRAME_TIMEOUT_MS = 5_000
const RETRY_DELAY_MS = 2_000

function appendBytes(left: Uint8Array, right: Uint8Array) {
  const joined = new Uint8Array(left.length + right.length)
  joined.set(left)
  joined.set(right, left.length)
  return joined
}

function findMarker(bytes: Uint8Array, first: number, second: number, from = 0) {
  for (let index = from; index < bytes.length - 1; index += 1) {
    if (bytes[index] === first && bytes[index + 1] === second) return index
  }
  return -1
}

type StreamSession = {
  token: string
  expiresAt: string
}

export function useMjpegStream(robotId?: string | number) {
  const [frameUrl, setFrameUrl] = useState<string>()
  const [state, setState] = useState<MjpegStreamState>(robotId == null ? 'idle' : 'connecting')

  useEffect(() => {
    if (robotId == null) {
      setState('idle')
      setFrameUrl(undefined)
      return
    }

    setState('connecting')
    setFrameUrl(undefined)

    const lifecycleController = new AbortController()
    let activeAttempt: AbortController | undefined
    let currentUrl: string | undefined
    let retryTimer: ReturnType<typeof setTimeout> | undefined

    const clearPublishedFrame = () => {
      const previousUrl = currentUrl
      currentUrl = undefined
      setFrameUrl(undefined)
      if (previousUrl) URL.revokeObjectURL(previousUrl)
    }

    const replaceFrame = (jpeg: Uint8Array, attemptController: AbortController) => {
      if (
        lifecycleController.signal.aborted ||
        attemptController.signal.aborted ||
        activeAttempt !== attemptController
      ) return

      const jpegBuffer = new ArrayBuffer(jpeg.byteLength)
      new Uint8Array(jpegBuffer).set(jpeg)
      const nextUrl = URL.createObjectURL(new Blob([jpegBuffer], { type: 'image/jpeg' }))
      const previousUrl = currentUrl
      currentUrl = nextUrl
      setFrameUrl(nextUrl)
      setState('live')
      if (previousUrl) URL.revokeObjectURL(previousUrl)
    }

    const connect = async () => {
      if (lifecycleController.signal.aborted) return
      setState((previous) => (previous === 'live' ? previous : 'connecting'))

      const attemptController = new AbortController()
      activeAttempt = attemptController
      const abortAttempt = () => attemptController.abort()
      lifecycleController.signal.addEventListener('abort', abortAttempt, { once: true })
      let frameWatchdog: ReturnType<typeof setTimeout> | undefined
      const armFrameWatchdog = (timeoutMs: number) => {
        if (frameWatchdog) clearTimeout(frameWatchdog)
        frameWatchdog = setTimeout(() => attemptController.abort(), timeoutMs)
      }
      armFrameWatchdog(FIRST_FRAME_TIMEOUT_MS)

      try {
        const session = await apiRequest<StreamSession>(
          `/api/robots/${robotId}/stream-sessions`,
          { method: 'POST', signal: attemptController.signal },
        )
        const response = await fetch(apiUrl(`/live/robots/${robotId}/stream.mjpg`), {
          headers: {
            Accept: 'multipart/x-mixed-replace',
            'X-Stream-Token': session.token,
          },
          cache: 'no-store',
          signal: attemptController.signal,
        })
        if (!response.ok || !response.body) {
          throw new Error(`MJPEG stream failed (${response.status})`)
        }

        const reader = response.body.getReader()
        let buffer = new Uint8Array()
        while (!attemptController.signal.aborted) {
          const { value, done } = await reader.read()
          if (
            lifecycleController.signal.aborted ||
            activeAttempt !== attemptController
          ) return
          if (attemptController.signal.aborted) {
            throw new Error('MJPEG frame timeout')
          }
          if (done) throw new Error('MJPEG stream closed')
          if (!value) continue

          buffer = appendBytes(buffer, value)
          let start = findMarker(buffer, 0xff, 0xd8)
          while (start >= 0) {
            const end = findMarker(buffer, 0xff, 0xd9, start + 2)
            if (end < 0) break
            replaceFrame(buffer.slice(start, end + 2), attemptController)
            armFrameWatchdog(NEXT_FRAME_TIMEOUT_MS)
            buffer = buffer.slice(end + 2)
            start = findMarker(buffer, 0xff, 0xd8)
          }

          if (buffer.length > MAX_BUFFER_BYTES) buffer = buffer.slice(-2)
        }
        if (!lifecycleController.signal.aborted && activeAttempt === attemptController) {
          throw new Error('MJPEG stream attempt aborted')
        }
      } catch {
        if (lifecycleController.signal.aborted) return
        clearPublishedFrame()
        setState('offline')
        retryTimer = setTimeout(connect, RETRY_DELAY_MS)
      } finally {
        if (frameWatchdog) clearTimeout(frameWatchdog)
        lifecycleController.signal.removeEventListener('abort', abortAttempt)
        if (activeAttempt === attemptController) activeAttempt = undefined
      }
    }

    void connect()
    return () => {
      lifecycleController.abort()
      activeAttempt?.abort()
      if (retryTimer) clearTimeout(retryTimer)
      if (currentUrl) URL.revokeObjectURL(currentUrl)
    }
  }, [robotId])

  return { frameUrl, state }
}

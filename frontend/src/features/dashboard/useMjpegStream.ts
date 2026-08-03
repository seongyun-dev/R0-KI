import { useEffect, useState } from 'react'
import { authenticatedFetch } from '../../api/client'

export type MjpegStreamState = 'idle' | 'connecting' | 'live' | 'offline'

const MAX_BUFFER_BYTES = 2 * 1024 * 1024

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

export function useMjpegStream(path?: string) {
  const [frameUrl, setFrameUrl] = useState<string>()
  const [state, setState] = useState<MjpegStreamState>(path ? 'connecting' : 'idle')

  useEffect(() => {
    if (!path) {
      setState('idle')
      setFrameUrl(undefined)
      return
    }

    setState('connecting')
    setFrameUrl(undefined)

    const controller = new AbortController()
    let currentUrl: string | undefined
    let retryTimer: ReturnType<typeof setTimeout> | undefined

    const replaceFrame = (jpeg: Uint8Array) => {
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
      setState((previous) => (previous === 'live' ? previous : 'connecting'))
      try {
        const response = await authenticatedFetch(new URL(path, window.location.origin).toString(), {
          headers: { Accept: 'multipart/x-mixed-replace' },
          cache: 'no-store',
          signal: controller.signal,
        })
        if (!response.ok || !response.body) {
          throw new Error(`MJPEG stream failed (${response.status})`)
        }

        const reader = response.body.getReader()
        let buffer = new Uint8Array()
        while (!controller.signal.aborted) {
          const { value, done } = await reader.read()
          if (done) throw new Error('MJPEG stream closed')
          if (!value) continue

          buffer = appendBytes(buffer, value)
          let start = findMarker(buffer, 0xff, 0xd8)
          while (start >= 0) {
            const end = findMarker(buffer, 0xff, 0xd9, start + 2)
            if (end < 0) break
            replaceFrame(buffer.slice(start, end + 2))
            buffer = buffer.slice(end + 2)
            start = findMarker(buffer, 0xff, 0xd8)
          }

          if (buffer.length > MAX_BUFFER_BYTES) buffer = buffer.slice(-2)
        }
      } catch {
        if (controller.signal.aborted) return
        setState('offline')
        retryTimer = setTimeout(connect, 2000)
      }
    }

    void connect()
    return () => {
      controller.abort()
      if (retryTimer) clearTimeout(retryTimer)
      if (currentUrl) URL.revokeObjectURL(currentUrl)
    }
  }, [path])

  return { frameUrl, state }
}

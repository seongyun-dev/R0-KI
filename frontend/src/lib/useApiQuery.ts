import { useCallback, useEffect, useState } from 'react'

export type ApiQueryResult<T> = {
  data: T | undefined
  isLoading: boolean
  isError: boolean
  error: Error | null
  refetch: () => void
}

type QueryOptions = {
  enabled?: boolean
  delayMs?: number
}

/** 실제 API와 목업을 같은 { data, isLoading, error, refetch } 형태로 다루는 가벼운 조회 훅. */
export function useApiQuery<T>(
  load: () => Promise<T>,
  deps: unknown[] = [],
  options: QueryOptions = {},
): ApiQueryResult<T> {
  const { enabled = true, delayMs = 0 } = options
  const [version, setVersion] = useState(0)
  const [state, setState] = useState<{
    data: T | undefined
    isLoading: boolean
    error: Error | null
  }>({
    data: undefined,
    isLoading: enabled,
    error: null,
  })

  useEffect(() => {
    if (!enabled) {
      setState({ data: undefined, isLoading: false, error: null })
      return
    }

    const controller = new AbortController()
    let active = true
    let timer: number | undefined
    setState((previous) => ({ ...previous, isLoading: true, error: null }))

    const run = () => {
      load()
        .then((data) => {
          if (active && !controller.signal.aborted) {
            setState({ data, isLoading: false, error: null })
          }
        })
        .catch((reason: unknown) => {
          if (active && !controller.signal.aborted) {
            const error = reason instanceof Error ? reason : new Error('데이터를 불러오지 못했습니다')
            setState({ data: undefined, isLoading: false, error })
          }
        })
    }

    if (delayMs > 0) timer = window.setTimeout(run, delayMs)
    else run()

    return () => {
      active = false
      controller.abort()
      if (timer !== undefined) window.clearTimeout(timer)
    }
    // load 함수는 feature 훅이 deps로 명시한 값만 사용한다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, enabled, delayMs, version])

  const refetch = useCallback(() => setVersion((value) => value + 1), [])

  return {
    ...state,
    isError: Boolean(state.error),
    refetch,
  }
}

import { useCallback, useEffect, useState } from 'react'
import type {
  AnalyticsInsightPeriodType,
  AnalyticsInsightResponse,
} from '../../api/analyticsContracts'
import { statsApi } from '../../api/services'

const POLL_INTERVAL_MS = 3000

export type UseAnalyticsInsightResult = {
  data: AnalyticsInsightResponse | undefined
  /** 최초 응답 전 */
  isLoading: boolean
  /** PENDING/PROCESSING 폴링 중 */
  isPolling: boolean
  isError: boolean
  error: Error | null
  refetch: () => void
}

function isGenerating(status: AnalyticsInsightResponse['generationStatus']) {
  return status === 'PENDING' || status === 'PROCESSING'
}

/**
 * 주/월 AI 인사이트 조회 + 상태 폴링.
 *
 * @param periodKey 있으면 해당 구간, 없으면 직전 완료 구간
 * @param enabled false면 요청하지 않음 (진행 중 기간·분기/연 등)
 */
export function useAnalyticsInsight(
  periodType: AnalyticsInsightPeriodType,
  periodKey?: string,
  enabled = true,
): UseAnalyticsInsightResult {
  const [version, setVersion] = useState(0)
  const [data, setData] = useState<AnalyticsInsightResponse | undefined>()
  const [isLoading, setIsLoading] = useState(Boolean(enabled))
  const [isPolling, setIsPolling] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const refetch = useCallback(() => setVersion((value) => value + 1), [])

  useEffect(() => {
    let disposed = false

    if (!enabled) {
      setData(undefined)
      setIsLoading(false)
      setIsPolling(false)
      setError(null)
      return
    }

    const run = async () => {
      setIsLoading(true)
      setIsPolling(false)
      setError(null)

      try {
        while (!disposed) {
          const result = await statsApi.fetchInsight(periodType, periodKey)
          if (disposed) return

          setData(result)
          setIsLoading(false)

          if (!isGenerating(result.generationStatus)) {
            setIsPolling(false)
            return
          }

          setIsPolling(true)
          await new Promise<void>((resolve) => {
            window.setTimeout(resolve, POLL_INTERVAL_MS)
          })
        }
      } catch (reason) {
        if (disposed) return
        const nextError =
          reason instanceof Error ? reason : new Error('리포트를 불러오지 못했습니다')
        setError(nextError)
        setIsLoading(false)
        setIsPolling(false)
      }
    }

    void run()

    return () => {
      disposed = true
    }
  }, [periodType, periodKey, enabled, version])

  return {
    data,
    isLoading,
    isPolling,
    isError: Boolean(error),
    error,
    refetch,
  }
}

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

async function fetchInsight(
  periodType: AnalyticsInsightPeriodType,
): Promise<AnalyticsInsightResponse> {

  return statsApi.fetchInsight(periodType)
}

/**
 * 직전 완료 주/월 AI 인사이트 조회 + 상태 폴링.
 *
 * - periodType 변경 시 해당 기간 리포트를 다시 조회한다.
 * - PENDING/PROCESSING 이면 3초 간격으로 COMPLETED/FAILED 까지 재조회한다.
 * - UI 연결은 Step 3~4 에서 InsightReportPanel 이 담당한다.
 */
export function useAnalyticsInsight(
  periodType: AnalyticsInsightPeriodType,
): UseAnalyticsInsightResult {
  const [version, setVersion] = useState(0)
  const [data, setData] = useState<AnalyticsInsightResponse | undefined>()
  const [isLoading, setIsLoading] = useState(true)
  const [isPolling, setIsPolling] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const refetch = useCallback(() => setVersion((value) => value + 1), [])

  useEffect(() => {
    let disposed = false

    const run = async () => {
      setIsLoading(true)
      setIsPolling(false)
      setError(null)

      try {
        while (!disposed) {
          const result = await fetchInsight(periodType)
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
  }, [periodType, version])

  return {
    data,
    isLoading,
    isPolling,
    isError: Boolean(error),
    error,
    refetch,
  }
}

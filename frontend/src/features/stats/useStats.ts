import {
  aiInsights,
  dailyEvents,
  handlingStats,
  hourlyEvents,
  statSummary,
  zoneShares,
} from '../../mocks'
import { statsApi } from '../../api/services'
import { env } from '../../config/env'
import { useApiQuery } from '../../lib/useApiQuery'
import { assembleStatsDashboard } from './mapAnalyticsToStats'
import { resolveAnalyticsRange } from './resolveAnalyticsRange'
import type { StatsDashboardData } from './mapAnalyticsToStats'

/**
 * 통계 대시보드 데이터 훅.
 *
 * 역할:
 * - Stats.tsx 에 summary / daily / hourly / handling / zones / insights 를 넘긴다.
 * - VITE_USE_MOCKS=true 이면 기존 목업 유지 (디자인 확인용).
 * - false 이면 백엔드 Analytics API 5호출 → assembleStatsDashboard 매핑.
 *
 * 연결:
 * - period: 화면 드롭다운 → resolveAnalyticsRange → from/to
 * - zone: 1차 미연동 (parking/recycle/danger 목업용). API 쿼리에 넣지 않음.
 */
export function useStats(params: { period?: string; zone?: string } = {}) {
  const period = params.period || 'month'

  return useApiQuery<StatsDashboardData>(
    async () => {
      if (env.useMocks) {
        return {
          summary: statSummary,
          daily: dailyEvents,
          hourly: hourlyEvents,
          handling: handlingStats,
          zones: zoneShares,
          insights: aiInsights,
        }
      }

      // 실연동: period → 기간, 5개 API 병렬 호출 후 화면 형태로 조립
      const range = resolveAnalyticsRange(period)
      const [overview, dailyTrend, hourlyTrend, handling, byZone] =
        await statsApi.fetchDashboard(range)

      return assembleStatsDashboard({
        overview,
        dailyTrend,
        hourlyTrend,
        handling,
        byZone,
      })
    },
    // zone은 UI만 유지하고 의존성에서 빼 두어 불필요한 재요청을 막는다 (1차 미연동)
    [period],
    { delayMs: env.useMocks ? 350 : 0 },
  )
}

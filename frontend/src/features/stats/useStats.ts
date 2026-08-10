
import { statsApi } from '../../api/services'
import { useApiQuery } from '../../lib/useApiQuery'
import { assembleStatsDashboard } from './mapAnalyticsToStats'
import {
  resolveStatsRange,
  resolveTrendBucket,
  type StatsUnit,
} from './resolveAnalyticsRange'
import type { StatsDashboardData } from './mapAnalyticsToStats'

/**
 * 통계 대시보드 데이터 훅.
 *
 * - unit + offset → resolveStatsRange → from/to
 * - zone: parking/recycle → zoneIds 필터
 */
export function useStats(
  params: { unit?: StatsUnit; offset?: number; zone?: string } = {},
) {
  const unit = params.unit ?? 'month'
  const offset = params.offset ?? 0
  const zone = params.zone || 'all'
  const range = resolveStatsRange(unit, offset)

  return useApiQuery<StatsDashboardData>(
    async () => {


      const trendBucket = resolveTrendBucket(unit)
      const [overview, dailyTrend, hourlyTrend, handling, byZone] =
        await statsApi.fetchDashboard(range, zone, { trendBucket })

      return assembleStatsDashboard({
        overview,
        dailyTrend,
        hourlyTrend,
        handling,
        byZone,
      })
    },
    [unit, offset, zone, range.from, range.to],
    { delayMs: 0 },
  )
}

export function useStatsPeriodLabel(unit: StatsUnit, offset: number) {
  return resolveStatsRange(unit, offset).label
}

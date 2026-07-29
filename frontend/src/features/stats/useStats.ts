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
import type {
  AiInsight,
  DailyEventStat,
  HandlingStat,
  HourlyEventStat,
  StatSummary,
  ZoneShareStat,
} from '../../types/domain'

type StatsResponse = {
  summary: StatSummary
  daily: DailyEventStat[]
  hourly: HourlyEventStat[]
  handling: HandlingStat[]
  zones: ZoneShareStat[]
  /** 서버가 문자열 배열만 줄 수도 있다 — 화면에서 정규화 */
  insights: (string | AiInsight)[]
}

/** 통계 대시보드 (1m) — KPI + 추이 + 시간대별 + 처리 현황 + 구역 비율 + AI 인사이트 */
export function useStats(params: { period?: string; zone?: string } = {}) {
  return useApiQuery(
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
      return (await statsApi.get(params)) as StatsResponse
    },
    [params.period, params.zone],
    { delayMs: env.useMocks ? 350 : 0 },
  )
}

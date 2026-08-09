/**
 * 차트 기간(unit+offset) → AI 인사이트 periodType/periodKey.
 *
 * 백엔드 AnalyticsInsightPeriodResolver 와 동일 규칙:
 * - WEEK: ISO week 키 `YYYY-Www`, 월~일
 * - MONTH: `YYYY-MM`
 * - 완료 구간만 API 조회 가능 (periodTo 날짜 < 오늘 KST)
 */

import type { AnalyticsInsightPeriodType } from '../../api/analyticsContracts'
import { resolveStatsRange, type StatsUnit } from './resolveAnalyticsRange'

export type InsightPeriod = {
  periodType: AnalyticsInsightPeriodType
  periodKey: string
  label: string
  from: string
  to: string
  /** false면 진행 중(이번 주/달) — 백엔드가 거절하므로 조회하지 않음 */
  isComplete: boolean
}

function seoulYmd() {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date())
  const get = (type: string) => Number(parts.find((p) => p.type === type)?.value)
  return { year: get('year'), month: get('month'), day: get('day') }
}

function pad(n: number) {
  return String(n).padStart(2, '0')
}

/** range.from 앞 10자(YYYY-MM-DD) → UTC noon 날짜 */
function parseYmd(iso: string) {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number)
  return { year: y, month: m, day: d }
}

/**
 * ISO-8601 week key (WeekFields.ISO).
 * mondayYmd = 해당 주 월요일.
 */
function isoWeekKey(mondayYmd: { year: number; month: number; day: number }) {
  const date = new Date(Date.UTC(mondayYmd.year, mondayYmd.month - 1, mondayYmd.day))
  // 목요일이 속한 연도 = week-based year
  const thursday = new Date(date)
  thursday.setUTCDate(date.getUTCDate() + 3)
  const weekBasedYear = thursday.getUTCFullYear()
  const jan4 = new Date(Date.UTC(weekBasedYear, 0, 4))
  const jan4Dow = (jan4.getUTCDay() + 6) % 7 // Mon=0
  const week1Monday = new Date(jan4)
  week1Monday.setUTCDate(jan4.getUTCDate() - jan4Dow)
  const diffDays = Math.round((date.getTime() - week1Monday.getTime()) / 86400000)
  const week = Math.floor(diffDays / 7) + 1
  return `${weekBasedYear}-W${pad(week)}`
}

function isPeriodComplete(toIso: string) {
  const to = parseYmd(toIso)
  const today = seoulYmd()
  const toNum = to.year * 10000 + to.month * 100 + to.day
  const todayNum = today.year * 10000 + today.month * 100 + today.day
  return toNum < todayNum
}

/** 주/월만. 분기·연은 null */
export function resolveInsightPeriod(
  unit: StatsUnit,
  offset = 0,
): InsightPeriod | null {
  if (unit !== 'week' && unit !== 'month') return null

  const range = resolveStatsRange(unit, offset)
  const from = parseYmd(range.from)
  const periodType: AnalyticsInsightPeriodType = unit === 'week' ? 'WEEK' : 'MONTH'
  const periodKey =
    unit === 'week'
      ? isoWeekKey(from)
      : `${from.year}-${pad(from.month)}`

  return {
    periodType,
    periodKey,
    label: range.label,
    from: range.from,
    to: range.to,
    isComplete: isPeriodComplete(range.to),
  }
}

/**
 * 통계 기간(from/to) 계산 — 주/월/분기/연 + offset 네비게이션.
 *
 * offset 0 = 현재 구간, -1 = 직전, -2 = 그 이전 …
 * 분기·연 추이는 항상 month 버킷 (day 촘촘 라벨 방지).
 * 시간대: Asia/Seoul(+09:00).
 */

export type StatsUnit = 'week' | 'month' | 'quarter' | 'year'

export type AnalyticsRange = {
  from: string
  to: string
  label: string
}

export type TrendBucket = 'day' | 'week' | 'month'

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

function atStart(y: number, m: number, d: number) {
  return `${y}-${pad(m)}-${pad(d)}T00:00:00+09:00`
}

function atEnd(y: number, m: number, d: number) {
  return `${y}-${pad(m)}-${pad(d)}T23:59:59+09:00`
}

function lastDayOfMonth(y: number, m: number) {
  return new Date(Date.UTC(y, m, 0)).getUTCDate()
}

function todayAnchor() {
  const { year, month, day } = seoulYmd()
  return new Date(Date.UTC(year, month - 1, day, 12, 0, 0))
}

function ymdOf(date: Date) {
  return {
    year: date.getUTCFullYear(),
    month: date.getUTCMonth() + 1,
    day: date.getUTCDate(),
  }
}

function formatMd(m: number, d: number) {
  return `${m}/${d}`
}

/**
 * 단위 + offset → from/to/label.
 * @param offset 0=현재, 음수=과거 (양수는 현재로 클램프)
 */
export function resolveStatsRange(unit: StatsUnit = 'month', offset = 0): AnalyticsRange {
  const clamped = Math.min(0, offset)
  const today = todayAnchor()
  const { year, month } = seoulYmd()

  if (unit === 'week') {
    const dow = today.getUTCDay()
    const daysFromMonday = (dow + 6) % 7
    const thisMonday = new Date(today)
    thisMonday.setUTCDate(today.getUTCDate() - daysFromMonday + clamped * 7)
    const sunday = new Date(thisMonday)
    sunday.setUTCDate(thisMonday.getUTCDate() + 6)

    const a = ymdOf(thisMonday)
    const b = ymdOf(sunday)
    const sameYear = a.year === b.year
    const label = sameYear
      ? `${a.year}. ${formatMd(a.month, a.day)}–${formatMd(b.month, b.day)}`
      : `${a.year}. ${formatMd(a.month, a.day)}–${b.year}. ${formatMd(b.month, b.day)}`

    return {
      from: atStart(a.year, a.month, a.day),
      to: atEnd(b.year, b.month, b.day),
      label,
    }
  }

  if (unit === 'quarter') {
    const thisQ = Math.floor((month - 1) / 3) // 0..3
    const index = year * 4 + thisQ + clamped
    const y = Math.floor(index / 4)
    const q = ((index % 4) + 4) % 4 // 안전
    const startMonth = q * 3 + 1
    const endMonth = startMonth + 2
    return {
      from: atStart(y, startMonth, 1),
      to: atEnd(y, endMonth, lastDayOfMonth(y, endMonth)),
      label: `${y}년 ${q + 1}분기`,
    }
  }

  if (unit === 'year') {
    const y = year + clamped
    return {
      from: atStart(y, 1, 1),
      to: atEnd(y, 12, 31),
      label: `${y}년`,
    }
  }

  // month
  const monthIndex = year * 12 + (month - 1) + clamped
  const y = Math.floor(monthIndex / 12)
  const m = ((monthIndex % 12) + 12) % 12 + 1
  return {
    from: atStart(y, m, 1),
    to: atEnd(y, m, lastDayOfMonth(y, m)),
    label: `${y}년 ${m}월`,
  }
}

/**
 * 추이 버킷.
 * - 주/달: day
 * - 분기/연: 무조건 month (라벨 과밀 방지)
 */
export function resolveTrendBucket(unit: StatsUnit = 'month'): TrendBucket {
  if (unit === 'quarter' || unit === 'year') return 'month'
  return 'day'
}

/** @deprecated 프리셋 period 호환 */
export function resolveAnalyticsRange(period = 'month'): AnalyticsRange {
  if (period === 'week') return resolveStatsRange('week', 0)
  if (period === 'quarter') return resolveStatsRange('quarter', 0)
  if (period === 'year') return resolveStatsRange('year', 0)
  return resolveStatsRange('month', 0)
}

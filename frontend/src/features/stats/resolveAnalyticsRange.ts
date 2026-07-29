/**
 * 통계 기간(from/to) 계산.
 *
 * Stats 화면 드롭다운 period → 백엔드 overview/trend/handling/by-zone 공통 쿼리.
 * 시간대는 백엔드와 동일하게 Asia/Seoul(+09:00) wall-clock 문자열을 쓴다.
 *
 * - week: 이번 주 월요일 00:00 ~ 일요일 23:59:59
 * - month: 이번 달 1일 00:00 ~ 말일 23:59:59 (기본)
 * - quarter: 이번 분기 첫날 00:00 ~ 분기 말일 23:59:59
 */

export type AnalyticsRange = {
  from: string
  to: string
}

/** 서울 기준 오늘 연·월·일 */
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

/** 해당 월 말일 */
function lastDayOfMonth(y: number, m: number) {
  return new Date(Date.UTC(y, m, 0)).getUTCDate()
}

/**
 * Stats period 값 → analytics from/to.
 * @param period 'week' | 'month' | 'quarter' | 기타(기본 month)
 */
export function resolveAnalyticsRange(period = 'month'): AnalyticsRange {
  const { year, month, day } = seoulYmd()
  // JS Date: monthIndex 0-based. 요일 계산용(서울 날짜를 UTC 정오로 고정해 요일만 씀)
  const todayUtc = new Date(Date.UTC(year, month - 1, day, 12, 0, 0))
  const dow = todayUtc.getUTCDay() // 0=일 … 6=토
  const daysFromMonday = (dow + 6) % 7

  if (period === 'week') {
    const monday = new Date(todayUtc)
    monday.setUTCDate(day - daysFromMonday)
    const sunday = new Date(monday)
    sunday.setUTCDate(monday.getUTCDate() + 6)
    return {
      from: atStart(monday.getUTCFullYear(), monday.getUTCMonth() + 1, monday.getUTCDate()),
      to: atEnd(sunday.getUTCFullYear(), sunday.getUTCMonth() + 1, sunday.getUTCDate()),
    }
  }

  if (period === 'quarter') {
    const qStartMonth = Math.floor((month - 1) / 3) * 3 + 1
    const qEndMonth = qStartMonth + 2
    return {
      from: atStart(year, qStartMonth, 1),
      to: atEnd(year, qEndMonth, lastDayOfMonth(year, qEndMonth)),
    }
  }

  // month (기본)
  return {
    from: atStart(year, month, 1),
    to: atEnd(year, month, lastDayOfMonth(year, month)),
  }
}

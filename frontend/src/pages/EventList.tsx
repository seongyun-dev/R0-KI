import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { R0KiShell } from '../components/layout/R0KiShell'
import { R0KiDropdown } from '../components/ui/R0KiDropdown'
import { useEvents } from '../features/events/useEvents'
import type {
  EventPeriodCode,
  EventTypeCode,
  ProcessingStatusCode,
} from '../api/contracts'

/* R0-Ki 이벤트 목록 — 시안 R0Kievents 그대로.
   유리 테이블 + 커스텀 드롭다운 4종 필터. 데이터는 기존 useEvents 그대로.
   위험도는 긴급만 --urgent(모노크롬 예외), 나머지는 명도 램프. */

/* 처리 상태 점 색 — 명도 램프 */
const STATE_DOT: Record<string, string> = {
  탐지: 'var(--detect)',
  처리중: 'var(--charge)',
  처리완료: 'var(--offline)',
}
/* 위험도 점 색 (긴급은 .st.u 로 별도 처리) */
const RISK_DOT: Record<string, string> = {
  보통: 'var(--detect)',
  낮음: 'var(--offline)',
}

const TYPE_OPTIONS = [
  { value: 'ILLEGAL_PARKING', label: '불법주차' },
  { value: 'UNREGISTERED_VEHICLE', label: '미등록 차량' },
  { value: 'TRASH_DETECTED', label: '쓰레기' },
  { value: 'RECYCLING_AREA_FULL', label: '분리수거장' },
  { value: 'EMERGENCY', label: '응급상황' },
]

const STATE_OPTIONS = [
  { value: 'DETECTED', label: '탐지' },
  { value: 'PROCESSING', label: '처리중' },
  { value: 'COMPLETED', label: '처리완료' },
]

const PERIOD_OPTIONS = [
  { value: 'ALL', label: '전체' },
  { value: 'TODAY', label: '오늘' },
  { value: 'LAST_7_DAYS', label: '최근 7일' },
]

type EventListFilters = {
  type: EventTypeCode | ''
  status: ProcessingStatusCode | ''
  period: EventPeriodCode | ''
}

const TYPE_VALUES = new Set(TYPE_OPTIONS.map((option) => option.value))
const STATE_VALUES = new Set(STATE_OPTIONS.map((option) => option.value))
const PERIOD_VALUES = new Set(PERIOD_OPTIONS.map((option) => option.value))

function filtersFromSearchParams(params: URLSearchParams): EventListFilters {
  const type = params.get('type') ?? ''
  const status = params.get('status') ?? ''
  const period = params.get('period') ?? ''
  return {
    type: TYPE_VALUES.has(type) ? (type as EventTypeCode) : '',
    status: STATE_VALUES.has(status) ? (status as ProcessingStatusCode) : '',
    period: PERIOD_VALUES.has(period) ? (period as EventPeriodCode) : '',
  }
}

function pageFromSearchParams(params: URLSearchParams) {
  const raw = params.get('page')
  if (!raw) return 0
  const page = Number(raw)
  return Number.isInteger(page) && page >= 0 ? page : 0
}

function buildSearchParams(filters: EventListFilters, page: number) {
  const params = new URLSearchParams()
  if (filters.type) params.set('type', filters.type)
  if (filters.status) params.set('status', filters.status)
  if (filters.period) params.set('period', filters.period)
  if (page > 0) params.set('page', String(page))
  return params
}

function toListSearch(filters: EventListFilters, page: number) {
  const query = buildSearchParams(filters, page).toString()
  return query ? `?${query}` : ''
}

// const RISK_OPTIONS = [
//   { value: 'EMERGENCY', label: '긴급' },
//   { value: 'NORMAL', label: '보통' },
//   { value: 'LOW', label: '낮음' },
// ]

export default function EventList() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const applied = filtersFromSearchParams(searchParams)
  const page = pageFromSearchParams(searchParams)
  const listSearch = toListSearch(applied, page)
  // 입력 중 필터 / 적용된 필터 분리 — 검색 버튼으로 확정
  const [draft, setDraft] = useState<EventListFilters>(applied)

  useEffect(() => {
    setDraft(applied)
  }, [applied.period, applied.status, applied.type, page])

  const {
    data: events,
    isLoading,
    error,
    refetch,
    totalElements,
    totalPages,
    first,
    last,
  } = useEvents({
    type: applied.type || undefined,
    status: applied.status || undefined,
    period: applied.period || undefined,
    page,
    size: 10,
    sort: ['occurredAt,DESC'],
  })

  const rows = events ?? []
  const urgentCount = rows.filter((e) => e.riskLevel === '긴급').length

  const set = (key: keyof typeof draft) => (value: string) =>
    setDraft((prev) => ({ ...prev, [key]: value }))

  return (
    <R0KiShell active="events">
      <div className="pcol">
        <div className="pagehead">
          <div>
            <div className="crumb">
              <Link to="/app">대시보드</Link><i>›</i><b>이벤트 관리</b>
            </div>
            <div className="ptitle">이벤트 목록</div>
          </div>
          <div className="headtools tight">
            <R0KiDropdown allLabel="유형 전체" options={TYPE_OPTIONS} value={draft.type} onChange={set('type')} />
            <R0KiDropdown allLabel="상태 전체" options={STATE_OPTIONS} value={draft.status} onChange={set('status')} />
            <R0KiDropdown allLabel="기간 전체" options={PERIOD_OPTIONS} value={draft.period} onChange={set('period')} />
            <button
              type="button"
              className="btn btn-p"
              onClick={() => setSearchParams(buildSearchParams({ ...draft }, 0))}
            >
              검색
            </button>
          </div>
        </div>

        <div className="glass g2 tblwrap">
          {error ? (
            <div className="tfoot" style={{ paddingTop: 'var(--s5)' }}>
              <span>이벤트를 불러오지 못했습니다</span>
              <button type="button" className="btn btn-s" onClick={refetch}>다시 시도</button>
            </div>
          ) : (
            <>
              <table className="tbl">
                <thead>
                  <tr>
                    <th>이벤트 ID</th>
                    <th>시간</th>
                    <th>유형</th>
                    <th>위치</th>
                    <th>로봇</th>
                    <th>위험도</th>
                    <th>상태</th>
                    <th>담당자</th>
                    <th className="r" />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((e) => (
                    <tr
                      key={e.id}
                      onClick={() =>
                        navigate(`/app/events/${e.id}`, { state: { listSearch } })
                      }
                    >
                      <td className="id">{e.id}</td>
                      <td className="tm">{e.time}</td>
                      <td className="ty">{e.type}</td>
                      <td className="loc">{e.location}</td>
                      <td className="bot">{e.robotId}</td>
                      <td>
                        {e.riskLevel === '긴급' ? (
                          <span className="st u"><i />긴급</span>
                        ) : (
                          <span className="st">
                            <i style={{ background: RISK_DOT[e.riskLevel ?? ''] ?? 'var(--detect)' }} />
                            {e.riskLevel ?? '—'}
                          </span>
                        )}
                      </td>
                      <td>
                        <span className="st">
                          <i style={{ background: STATE_DOT[e.status] ?? 'var(--detect)' }} />
                          {e.status}
                        </span>
                      </td>
                      <td className="who">
                        {e.assignee ?? <span className="dash">—</span>}
                      </td>
                      <td className="r">
                        <button type="button" className="golink">
                          상세
                          <svg viewBox="0 0 24 24"><path d="M5 12h13M12 5l7 7-7 7" /></svg>
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {rows.length === 0 && !isLoading && (
                <div className="empty">
                  <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.2-3.2" /></svg>
                  <span>조건에 맞는 이벤트가 없습니다</span>
                </div>
              )}

              {/* 여기 숫자는 지금 보이는 페이지 기준이다 — 아래 페이지네이션 줄의
                  '전체 N건'(totalElements)과 같은 말로 보이지 않게 범위를 밝힌다 */}
              <div className="tfoot">
                <span>
                  {isLoading
                    ? '불러오는 중…'
                    : rows.length === 0
                      ? '결과 없음'
                      : `이 페이지 ${rows.length}건 · 긴급 ${urgentCount}건`}
                </span>
                <span>최신순</span>
              </div>
              <div
                className="tfoot"
                style={{ justifyContent: 'flex-end', gap: 'var(--s2)' }}
              >
                <button
                  type="button"
                  className="btn btn-s"
                  disabled={first || isLoading}
                  onClick={() => setSearchParams(buildSearchParams(applied, Math.max(0, page - 1)))}
                >
                  이전
                </button>
                <span>
                  {totalPages === 0 ? 0 : page + 1} / {totalPages}
                </span>
                <button
                  type="button"
                  className="btn btn-s"
                  disabled={last || isLoading}
                  onClick={() => setSearchParams(buildSearchParams(applied, page + 1))}
                >
                  다음
                </button>
                <span>전체 {totalElements}건</span>
              </div>
            </>
          )}
        </div>
      </div>
    </R0KiShell>
  )
}

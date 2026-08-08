import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { R0KiShell } from '../components/layout/R0KiShell'
import { R0KiDropdown } from '../components/ui/R0KiDropdown'
import {
  formatDateTimeLabel,
  useResidentFilterOptions,
  useResidents,
} from '../features/residents/useResidents'

/* R0-Ki 입주민 관리 — 이벤트/알림 목록과 같은 유리 테이블 레이아웃.

   불법주차 SMS 는 등록 차량이 있는 세대에만 나간다. 그래서 현장에서 가장 잦은 흐름은
   "번호판을 보고 세대를 찾는 것"이라, 검색창은 차량번호까지 함께 훑는다. */

const PAGE_SIZE = 20

const NOTIFICATION_OPTIONS = [
  { value: 'true', label: '알림 수신' },
  { value: 'false', label: '알림 차단' },
]

const NOTIFICATION_VALUES = new Set(NOTIFICATION_OPTIONS.map((option) => option.value))

type ResidentFilters = {
  keyword: string
  buildingNumber: string
  notificationEnabled: string
}

function filtersFromSearchParams(params: URLSearchParams): ResidentFilters {
  const notificationEnabled = params.get('notificationEnabled') ?? ''
  return {
    keyword: params.get('keyword') ?? '',
    buildingNumber: params.get('building') ?? '',
    notificationEnabled: NOTIFICATION_VALUES.has(notificationEnabled) ? notificationEnabled : '',
  }
}

function pageFromSearchParams(params: URLSearchParams) {
  const raw = params.get('page')
  if (!raw) return 0
  const page = Number(raw)
  return Number.isInteger(page) && page >= 0 ? page : 0
}

function buildSearchParams(filters: ResidentFilters, page: number) {
  const params = new URLSearchParams()
  if (filters.keyword) params.set('keyword', filters.keyword)
  if (filters.buildingNumber) params.set('building', filters.buildingNumber)
  if (filters.notificationEnabled) {
    params.set('notificationEnabled', filters.notificationEnabled)
  }
  if (page > 0) params.set('page', String(page))
  return params
}

export default function ResidentList() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const applied = filtersFromSearchParams(searchParams)
  const page = pageFromSearchParams(searchParams)
  const [openFilter, setOpenFilter] = useState<'building' | 'notification' | null>(null)
  // 검색어는 엔터를 눌렀을 때만 URL에 반영한다 — 한 글자마다 조회하면 서버를 두드린다
  const [keywordDraft, setKeywordDraft] = useState(applied.keyword)

  const { data: buildingOptions } = useResidentFilterOptions()

  const {
    data: residents,
    isLoading,
    error,
    refetch,
    totalElements,
    totalPages,
    first,
    last,
  } = useResidents({
    keyword: applied.keyword || undefined,
    buildingNumber: applied.buildingNumber || undefined,
    notificationEnabled:
      applied.notificationEnabled === '' ? undefined : applied.notificationEnabled === 'true',
    page,
    size: PAGE_SIZE,
  })

  const rows = residents ?? []
  const noVehicleCount = rows.filter((r) => r.vehicleCount === 0).length

  const applyFilter = (key: keyof ResidentFilters, value: string) => {
    setSearchParams(buildSearchParams({ ...applied, [key]: value }, 0))
  }

  const onSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    applyFilter('keyword', keywordDraft.trim())
  }

  return (
    <R0KiShell active="residents">
      <div className="pcol">
        <div className="pagehead">
          <div>
            <div className="crumb">
              <Link to="/app">대시보드</Link><i>›</i><b>입주민 관리</b>
            </div>
            <div className="ptitle">입주민 목록</div>
          </div>
          <div className="headtools tight">
            <form onSubmit={onSearch}>
              <input
                className="au-in"
                value={keywordDraft}
                onChange={(event) => setKeywordDraft(event.target.value)}
                placeholder="이름 · 연락처 · 차량번호"
                aria-label="입주민 검색"
                autoComplete="off"
                style={{ minWidth: '15rem' }}
              />
            </form>
            <R0KiDropdown
              allLabel="동 전체"
              options={(buildingOptions?.buildingNumbers ?? []).map((value) => ({
                value,
                label: `${value}동`,
              }))}
              value={applied.buildingNumber}
              onChange={(value) => applyFilter('buildingNumber', value)}
              open={openFilter === 'building'}
              onOpenChange={(open) => setOpenFilter(open ? 'building' : null)}
            />
            <R0KiDropdown
              allLabel="알림 전체"
              options={NOTIFICATION_OPTIONS}
              value={applied.notificationEnabled}
              onChange={(value) => applyFilter('notificationEnabled', value)}
              open={openFilter === 'notification'}
              onOpenChange={(open) => setOpenFilter(open ? 'notification' : null)}
            />
            <Link to="/app/residents/new" className="btn btn-p btn-add">
              입주민 등록
              <svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14" /></svg>
            </Link>
          </div>
        </div>

        {/* 유리 껍데기와 스크롤러를 나눈다 — .g2 의 안쪽 링/면광은 absolute 라
            스크롤 컨테이너와 같은 엘리먼트에 두면 목록 중간에 가로선으로 딸려 온다 */}
        <div className="glass g2 tblshell">
          <div className="tblwrap">
            {error ? (
              <div className="tfoot" style={{ paddingTop: 'var(--s5)' }}>
                <span>입주민을 불러오지 못했습니다</span>
                <button type="button" className="btn btn-s" onClick={refetch}>다시 시도</button>
              </div>
            ) : (
              <>
                <table className="tbl">
                  <thead>
                    <tr>
                      <th>동/호수</th>
                      <th>이름</th>
                      <th>연락처</th>
                      <th>등록 차량</th>
                      <th>알림 수신</th>
                      <th>최근 발송</th>
                      <th className="r" />
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((resident) => (
                      <tr
                        key={resident.residentId}
                        onClick={() => navigate(`/app/residents/${resident.residentId}`)}
                      >
                        <td className="loc">
                          {resident.buildingNumber}동 {resident.unitNumber}호
                        </td>
                        <td className="who">{resident.name}</td>
                        <td className="num">{resident.maskedPhoneNumber}</td>
                        <td className="num">
                          {resident.vehicleCount === 0 ? (
                            <span className="dash">미등록</span>
                          ) : (
                            <>
                              {resident.representativeLicensePlate}
                              {resident.vehicleCount > 1 && ` 외 ${resident.vehicleCount - 1}대`}
                            </>
                          )}
                        </td>
                        <td>
                          {resident.notificationEnabled ? (
                            <span className="st">
                              <i style={{ background: 'var(--offline)' }} />
                              수신
                            </span>
                          ) : (
                            <span className="st u"><i />차단</span>
                          )}
                        </td>
                        <td className="tm">{formatDateTimeLabel(resident.lastNotifiedAt)}</td>
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
                    <svg viewBox="0 0 24 24">
                      <circle cx="12" cy="8" r="4" />
                      <path d="M4 21c0-4 3.6-6.5 8-6.5s8 2.5 8 6.5" />
                    </svg>
                    <span>조건에 맞는 입주민이 없습니다</span>
                  </div>
                )}

                <div className="tfoot">
                  <span>
                    {isLoading
                      ? '불러오는 중…'
                      : rows.length === 0
                        ? '결과 없음'
                        : `이 페이지 ${rows.length}세대${
                            noVehicleCount > 0 ? ` · 차량 미등록 ${noVehicleCount}세대` : ''
                          }`}
                  </span>
                  <span>동·호수순</span>
                </div>
                <div className="tfoot" style={{ justifyContent: 'flex-end', gap: 'var(--s2)' }}>
                  <button
                    type="button"
                    className="btn btn-s"
                    disabled={first || isLoading}
                    onClick={() =>
                      setSearchParams(buildSearchParams(applied, Math.max(0, page - 1)))
                    }
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
                  <span>전체 {totalElements}세대</span>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </R0KiShell>
  )
}

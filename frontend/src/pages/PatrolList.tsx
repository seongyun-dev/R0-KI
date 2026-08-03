import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { R0KiShell } from '../components/layout/R0KiShell'
import { usePatrols } from '../features/patrol/usePatrols'
import { useRobots } from '../features/robots/useRobot'
import { useAuthStore } from '../features/auth/useAuthStore'
import { env } from '../config/env'
import type { Patrol } from '../types/domain'

/* R0-Ki 순찰 이력 (목록) — 시안 R0Kipatrol 그대로.
   유리 테이블: 순찰 ID · 로봇 · 시작 · 종료 · 경로(구역 순서) · 이벤트 건수.
   데이터는 기존 usePatrols 그대로 (완료 순찰만 기록/표시). */

const PERIOD_LABEL: Record<string, string> = {
  all: '기간 전체',
  today: '오늘',
  '7d': '최근 7일',
  '30d': '최근 30일',
}

export default function PatrolList() {
  const navigate = useNavigate()
  const sessionRobotId = useAuthStore((state) => state.robotId)
  const selectedRobotId = env.useMocks ? 'R-01' : sessionRobotId ?? env.defaultRobotId
  const { data: robots } = useRobots()
  const [period, setPeriod] = useState('all')
  const [applied, setApplied] = useState('all')
  const [page, setPage] = useState(0)
  const {
    data: patrols,
    isLoading,
    error,
    refetch,
    totalElements,
    totalPages,
    first,
    last,
  } = usePatrols({
    robotId: selectedRobotId,
    period: applied,
    status: 'COMPLETED',
    page,
    size: 10,
    sort: ['startedAt,DESC'],
  })

  // 완료된 순찰만 기록/표시 (진행중 등 제외)
  const rows = (patrols ?? []).filter((p) => p.status === '완료')
  // 로봇 이름 — 서버 응답의 robotName 우선, 없으면 목록에서 조회
  const nameById = new Map((robots ?? []).map((r) => [r.id, r.name]))
  const robotLabel = (p: Patrol) => p.robotName ?? nameById.get(p.robotId) ?? p.robotId

  return (
    <R0KiShell active="patrol">
      <div className="pcol">
        <div className="pagehead">
          <div>
            <div className="crumb">
              <Link to="/app">대시보드</Link><i>›</i><b>순찰 관리</b>
            </div>
            <div className="ptitle">순찰 이력</div>
          </div>
          <form
            className="headtools"
            onSubmit={(e) => {
              e.preventDefault()
              setPage(0)
              setApplied(period)
            }}
          >
            <select
              className="sel"
              aria-label="기간 선택"
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
            >
              <option value="all">기간 전체</option>
              <option value="today">오늘</option>
              <option value="7d">최근 7일</option>
              <option value="30d">최근 30일</option>
            </select>
            <button type="submit" className="btn btn-p">검색</button>
          </form>
        </div>

        <div className="glass g2 tblwrap">
          {error ? (
            <div className="tfoot" style={{ paddingTop: 'var(--s5)' }}>
              <span>순찰 이력을 불러오지 못했습니다</span>
              <button type="button" className="btn btn-s" onClick={refetch}>다시 시도</button>
            </div>
          ) : (
            <>
              <table className="tbl">
                <thead>
                  <tr>
                    <th>순찰 ID</th>
                    <th>로봇</th>
                    <th>시작</th>
                    <th>종료</th>
                    <th>순찰 경로 (구역 순서)</th>
                    <th className="r">이벤트</th>
                    <th className="r" />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((p) => (
                    <tr key={p.id} onClick={() => navigate(`/app/patrol/${p.id}`)}>
                      <td className="id">{p.id}</td>
                      <td className="bot">{robotLabel(p)}</td>
                      <td className="tm">{p.date}<b>{p.start}</b></td>
                      <td className="tm"><b>{p.end ?? '-'}</b></td>
                      <td>
                        <span className="route">
                          {p.routeZones.map((zone, i) => (
                            <span key={`${zone}-${i}`}>
                              {i > 0 && <i>→ </i>}
                              {zone}
                            </span>
                          ))}
                        </span>
                      </td>
                      <td className="r"><span className="cnt">{p.eventCount}</span></td>
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
              <div className="tfoot">
                {/* 지금 보이는 페이지 기준 — 아래 '전체 N건'(totalElements)과 구분한다 */}
                <span>{isLoading ? '불러오는 중…' : rows.length === 0 ? '조건에 맞는 순찰 이력이 없습니다' : `이 페이지 ${rows.length}건`}</span>
                <span>{PERIOD_LABEL[applied] ?? '기간 전체'}</span>
              </div>
              <div
                className="tfoot"
                style={{ justifyContent: 'flex-end', gap: 'var(--s2)' }}
              >
                <button
                  type="button"
                  className="btn btn-s"
                  disabled={first || isLoading}
                  onClick={() => setPage((current) => Math.max(0, current - 1))}
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
                  onClick={() => setPage((current) => current + 1)}
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

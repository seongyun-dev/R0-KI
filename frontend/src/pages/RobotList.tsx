import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { R0KiShell } from '../components/layout/R0KiShell'
import { RobotEditDrawer } from '../features/robots/RobotEditDrawer'
import { useDeleteRobot, useRobots, useRobotStats, useUpdateRobot } from '../features/robots/useRobot'
import type { Robot } from '../types/domain'

/* R0-Ki 로봇 목록 — 시안 R0Ki-robots-detail 그대로.
   유리 KPI 3장 + 유리 테이블(배터리 막대). 데이터/뮤테이션은 기존 훅 그대로. */

/* 로봇 상태 점 색 — 명도 램프 */
const STATUS_DOT: Record<string, string> = {
  순찰중: 'var(--patrol)',
  대기: 'var(--offline)',
  충전중: 'var(--charge)',
  오류: 'var(--alert)',
  오프라인: 'var(--offline)',
}

export default function RobotList() {
  const navigate = useNavigate()
  const [page, setPage] = useState(0)
  const {
    data: robots,
    isLoading,
    error,
    refetch,
    totalElements,
    totalPages,
    first,
    last,
  } = useRobots({
    page,
    size: 10,
    sort: ['robotId,ASC'],
  })
  const { data: stats } = useRobotStats()
  const updateRobot = useUpdateRobot()
  const deleteRobot = useDeleteRobot()
  const [editing, setEditing] = useState<Robot | null>(null)
  // 수정 드로어 저장 결과(목업 — 서버 연동 시 mutation으로 교체)
  const [patches, setPatches] = useState<Record<string, Partial<Robot>>>({})
  // 토스트
  const [toast, setToast] = useState<string>()

  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(undefined), 2600)
    return () => clearTimeout(t)
  }, [toast])

  const rows = (robots ?? []).map((r) => ({ ...r, ...patches[r.id] }))

  // KPI는 단지 전체 현황 통계(GET /api/robots/stats) 기준. 목록은 페이지네이션되므로 rows로 계산하지 않는다.
  const kpis = [
    { label: '전체 로봇', value: stats?.totalCount ?? rows.length },
    { label: '순찰 중', value: stats?.patrollingCount ?? 0 },
    { label: '대기 · 충전 중', value: stats?.idleOrChargingCount ?? 0 },
  ]

  return (
    <R0KiShell active="robots">
      <div className="pcol">
        <div className="pagehead">
          <div>
            <div className="crumb">
              <Link to="/app">대시보드</Link><i>›</i><b>로봇 관리</b>
            </div>
            <div className="ptitle">로봇 목록</div>
          </div>
          <div className="headtools">
            <Link to="/app/robots/new" className="btn btn-p btn-add">
              <svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14" /></svg>
              로봇 등록
            </Link>
          </div>
        </div>

        {/* KPI: 전체 로봇 / 순찰 중 / 대기·충전 중 */}
        <div className="kpis">
          {kpis.map((k) => (
            <div className="glass g2 kpi" key={k.label}>
              <span className="k">{k.label}</span>
              <span className="v">{k.value}<em>대</em></span>
            </div>
          ))}
        </div>

        <div className="glass g2 tblwrap">
          {error ? (
            <div className="tfoot" style={{ paddingTop: 'var(--s5)' }}>
              <span>로봇 목록을 불러오지 못했습니다</span>
              <button type="button" className="btn btn-s" onClick={refetch}>다시 시도</button>
            </div>
          ) : (
            <>
              <table className="tbl">
                <thead>
                  <tr>
                    <th>로봇명</th>
                    <th>상태</th>
                    <th>배터리</th>
                    <th>현재 위치</th>
                    <th>최근 순찰</th>
                    <th className="r" />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.id} onClick={() => navigate(`/app/robots/${r.id}`)}>
                      <td className="id">{r.name}</td>
                      <td>
                        <span className="st">
                          <i style={{ background: STATUS_DOT[r.status] ?? 'var(--detect)' }} />
                          {r.status}
                        </span>
                      </td>
                      <td>
                        <span className="bat">
                          <span className="bar"><i style={{ width: `${r.battery}%` }} /></span>
                          <span className="pct">{r.battery}%</span>
                        </span>
                      </td>
                      <td className="loc">{r.location ?? '—'}</td>
                      <td className="tm">{r.lastPatrol ?? '—'}</td>
                      <td className="r">
                        <span className="rowacts">
                          <button type="button" className="golink">
                            상세
                            <svg viewBox="0 0 24 24"><path d="M5 12h13M12 5l7 7-7 7" /></svg>
                          </button>
                          <button
                            type="button"
                            className="linkbtn"
                            onClick={(e) => {
                              e.stopPropagation()
                              setEditing(r)
                            }}
                          >
                            수정
                          </button>
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {rows.length === 0 && !isLoading && (
                <div className="empty">
                  <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.2-3.2" /></svg>
                  <span>등록된 로봇이 없습니다</span>
                </div>
              )}

              <div className="tfoot">
                <span>{isLoading ? '불러오는 중…' : `전체 ${rows.length}대`}</span>
                <span>등록순</span>
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
                <span>전체 {totalElements}대</span>
              </div>
            </>
          )}
        </div>
      </div>

      {editing && (
        <RobotEditDrawer
          open={Boolean(editing)}
          robot={{ ...editing, ...patches[editing.id] }}
          onClose={() => setEditing(null)}
          onSave={async ({ name }) => {
            try {
              await updateRobot.mutateAsync({
                robotId: editing.backendId ?? editing.id,
                robotName: name,
              })
              setPatches((prev) => ({ ...prev, [editing.id]: { name } }))
              setToast('저장되었습니다')
            } catch (reason) {
              setToast(reason instanceof Error ? reason.message : '로봇 수정에 실패했습니다')
              throw reason
            }
          }}
          onDelete={async () => {
            try {
              await deleteRobot.mutateAsync({ robotId: editing.backendId ?? editing.id })
              setToast('로봇이 삭제되었습니다')
              refetch()
            } catch (reason) {
              setToast(reason instanceof Error ? reason.message : '로봇 삭제에 실패했습니다')
              throw reason
            }
          }}
        />
      )}

      {/* 토스트 */}
      <div className={`toast${toast ? ' on' : ''}`} role="status" aria-live="polite">
        <svg viewBox="0 0 24 24"><path d="M4 12.5 9.5 18 20 6.5" /></svg>
        <span>{toast}</span>
      </div>
    </R0KiShell>
  )
}

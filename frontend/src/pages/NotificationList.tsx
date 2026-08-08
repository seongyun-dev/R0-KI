import { Link, useNavigate } from 'react-router-dom'
import { R0KiShell } from '../components/layout/R0KiShell'
import { useNotifications } from '../features/notifications/useNotifications'

/* R0-Ki 알림 기록 — 이벤트 목록과 같은 유리 테이블 레이아웃.
   상태 필터 없이 발송 내역 전체를 최신순으로만 보여준다. */

/* 발송 상태 점 색 — 명도 램프 (실패는 .st.u 로 별도 처리) */
const STATUS_DOT: Record<string, string> = {
  발송완료: 'var(--offline)',
  발송대기: 'var(--charge)',
}

export default function NotificationList() {
  const navigate = useNavigate()
  const { data, isLoading, error, refetch } = useNotifications()

  const rows = data ?? []
  const failedCount = rows.filter((n) => n.status === '발송실패').length

  return (
    <R0KiShell active="notifications">
      <div className="pcol">
        <div className="pagehead">
          <div>
            <div className="crumb">
              <Link to="/app">대시보드</Link><i>›</i><b>알림</b>
            </div>
            <div className="ptitle">알림 기록</div>
          </div>
          <div className="headtools tight">
            <button type="button" className="btn btn-s" onClick={refetch}>새로고침</button>
          </div>
        </div>

        {/* 유리 껍데기와 스크롤러를 나눈다 — .g2 의 안쪽 링/면광은 absolute 라
            스크롤 컨테이너와 같은 엘리먼트에 두면 목록 중간에 가로선으로 딸려 온다 */}
        <div className="glass g2 tblshell">
          <div className="tblwrap">
            {error ? (
              <div className="tfoot" style={{ paddingTop: 'var(--s5)' }}>
                <span>알림을 불러오지 못했습니다</span>
                <button type="button" className="btn btn-s" onClick={refetch}>다시 시도</button>
              </div>
            ) : (
              <>
                <table className="tbl">
                  <thead>
                    <tr>
                      <th>알림 ID</th>
                      <th>발송 시각</th>
                      <th>이벤트 유형</th>
                      <th>수신자</th>
                      <th>동/호수</th>
                      <th>이벤트 ID</th>
                      <th>발송 상태</th>
                      <th className="r" />
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((n) => (
                      <tr key={n.id} onClick={() => navigate(`/app/notifications/${n.id}`)}>
                        <td className="id">{n.id}</td>
                        <td className="tm">{n.sentAtLabel}</td>
                        <td className="ty">{n.eventType}</td>
                        <td className="who">{n.recipientName}</td>
                        <td className="loc">{n.address}</td>
                        <td className="bot">{n.eventId}</td>
                        <td>
                          {n.status === '발송실패' ? (
                            <span className="st u"><i />발송실패</span>
                          ) : (
                            <span className="st">
                              <i style={{ background: STATUS_DOT[n.status] ?? 'var(--detect)' }} />
                              {n.status}
                            </span>
                          )}
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
                    <svg viewBox="0 0 24 24">
                      <path d="M18 9a6 6 0 1 0-12 0c0 6-2 7-2 7h16s-2-1-2-7" />
                      <path d="M13.7 20a2 2 0 0 1-3.4 0" />
                    </svg>
                    <span>발송된 알림이 없습니다</span>
                  </div>
                )}

                <div className="tfoot">
                  <span>
                    {isLoading
                      ? '불러오는 중…'
                      : rows.length === 0
                        ? '결과 없음'
                        : `전체 ${rows.length}건${failedCount > 0 ? ` · 실패 ${failedCount}건` : ''}`}
                  </span>
                  <span>최신순</span>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </R0KiShell>
  )
}

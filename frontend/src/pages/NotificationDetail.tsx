import { Link, useParams } from 'react-router-dom'
import { R0KiShell } from '../components/layout/R0KiShell'
import { useNotification } from '../features/notifications/useNotifications'

/* R0-Ki 알림 상세 — 이벤트 상세와 같은 2단 유리 레이아웃.
   좌: 입주민에게 나간 메시지 원문 / 우: 알림 정보 + 연결된 이벤트로 이동. */

const STATUS_DOT: Record<string, string> = {
  발송완료: 'var(--offline)',
  발송대기: 'var(--charge)',
}

function StatusChip({ status }: { status: string }) {
  if (status === '발송실패') return <span className="st u"><i />발송실패</span>
  return (
    <span className="st">
      <i style={{ background: STATUS_DOT[status] ?? 'var(--detect)' }} />
      {status}
    </span>
  )
}

export default function NotificationDetail() {
  const { id } = useParams()
  const { data: notification, isLoading, error, refetch } = useNotification(id)

  return (
    <R0KiShell active="notifications">
      <div className="pcol">
        <div className="pagehead">
          <div>
            <div className="crumb">
              <Link to="/app">대시보드</Link><i>›</i>
              <Link to="/app/notifications">알림</Link><i>›</i>
              <b>{notification?.id ?? id}</b>
            </div>
            <div className="ptitle row">
              알림 상세
              {notification && (
                <>
                  <span className="sub">{notification.id}</span>
                  <StatusChip status={notification.status} />
                </>
              )}
            </div>
          </div>
        </div>

        {error ? (
          <div className="glass g2 aisum">
            <div className="zh2"><span className="zn">알림을 불러오지 못했습니다</span></div>
            <button type="button" className="btn btn-s" onClick={refetch}>다시 시도</button>
          </div>
        ) : !notification ? (
          <div className="glass g2 aisum">
            <div className="zh2">
              <span className="zn">{isLoading ? '불러오는 중…' : `알림(${id})을 찾을 수 없습니다`}</span>
            </div>
            {!isLoading && <Link to="/app/notifications" className="btn btn-s">목록으로</Link>}
          </div>
        ) : (
          <div className="egrid">
            {/* 발송 메시지 원문 */}
            <div className="glass g2 dcol" style={{ padding: 'var(--s5)' }}>
              <div className="zh2">
                <span className="zn">알림 내용</span>
                <span className="zsub">입주민 발송 메시지 · {notification.eventType}</span>
              </div>
              <div className="ntmsg">
                <div className="tt">{notification.title}</div>
                <p className="bd">
                  {notification.content.trim() || '발송 본문이 없습니다'}
                </p>
                <div className="ft">
                  <span>{notification.recipientName} · {notification.address}</span>
                  <span className="num">{notification.sentAtLabel}</span>
                </div>
              </div>
            </div>

            {/* 알림 정보 */}
            <div className="glass g2 dcol" style={{ padding: 'var(--s5)' }}>
              <div className="zh2"><span className="zn">알림 정보</span></div>

              <div className="info">
                <div className="ir">
                  <span className="k">알림 ID</span>
                  <span className="v num">{notification.id}</span>
                </div>
                <div className="ir">
                  <span className="k">이벤트 유형</span>
                  <span className="v">{notification.eventType}</span>
                </div>
                <div className="ir">
                  <span className="k">발생 시각</span>
                  <span className="v num">{notification.occurredAtLabel}</span>
                </div>
                <div className="ir">
                  <span className="k">위치</span>
                  <span className="v">{notification.location}</span>
                </div>
                {notification.licensePlate && (
                  <div className="ir">
                    <span className="k">차량번호</span>
                    <span className="v num">{notification.licensePlate}</span>
                  </div>
                )}
                <div className="ir">
                  <span className="k">수신자</span>
                  <span className="v">{notification.recipientName}</span>
                </div>
                <div className="ir">
                  <span className="k">동/호수</span>
                  <span className="v">{notification.address}</span>
                </div>
                <div className="ir">
                  <span className="k">연락처</span>
                  <span className="v num">{notification.recipientPhone}</span>
                </div>
                <div className="ir">
                  <span className="k">발송 시각</span>
                  <span className="v num">{notification.sentAtLabel}</span>
                </div>
                <div className="ir">
                  <span className="k">발송 상태</span>
                  <span className="v"><StatusChip status={notification.status} /></span>
                </div>
              </div>

              <div className="actwrap">
                <div className="actk">연결된 이벤트 — {notification.eventId}</div>
                <div className="ntact">
                  <Link to="/app/notifications" className="btn btn-s">목록으로</Link>
                  <Link to={`/app/events/${notification.eventId}`} className="btn btn-p">
                    이벤트 상세 보기
                  </Link>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </R0KiShell>
  )
}

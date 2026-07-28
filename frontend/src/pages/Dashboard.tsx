import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { R0KiLiveCam } from '../features/dashboard/R0KiLiveCam'
import { R0KiPatrolMap } from '../features/dashboard/R0KiPatrolMap'
import { EmergencyAlertModal } from '../features/dashboard/EmergencyAlertModal'
import { useEmergencyAlert, isEmergencySeen, markEmergencySeen } from '../features/dashboard/useEmergencyAlert'
import { useEvents } from '../features/events/useEvents'
import { useRobots } from '../features/robots/useRobot'
import type { PatrolEvent } from '../types/domain'
import '../styles/r0ki.css'

/* R0-Ki · AURA GLASS 대시보드 (리디자인 시안 그대로)
   상단바(주 메뉴·알림·시계·야간모드) + 순찰 지도 + 실시간 탐지 영상 + 최근 순찰 이력.
   데이터는 기존 훅(useEvents/useRobots) 연결 — API 연동 시 값만 바뀐다. */

type Theme = 'crystal' | 'nocturne'
const THEME_KEY = 'r0ki-theme'

function useTheme() {
  const [theme, setTheme] = useState<Theme>(() =>
    localStorage.getItem(THEME_KEY) === 'nocturne' ? 'nocturne' : 'crystal',
  )
  const toggle = () => {
    setTheme((prev) => {
      const next = prev === 'crystal' ? 'nocturne' : 'crystal'
      localStorage.setItem(THEME_KEY, next)
      return next
    })
  }
  return { theme, toggle }
}

/** 시계 — 실제 한국시간, 1초 갱신 */
function useClockText() {
  const [text, setText] = useState(() => formatClock(new Date()))
  useEffect(() => {
    const t = setInterval(() => setText(formatClock(new Date())), 1000)
    return () => clearInterval(t)
  }, [])
  return text
}
function formatClock(d: Date) {
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

/* 이력 상태점 색 — 명도 램프 (처리완료=순찰, 그 외 감지) */
function dotColor(e: PatrolEvent) {
  if (e.status === '처리완료') return 'var(--patrol)'
  return 'var(--detect)'
}

const NAV_ITEMS = [
  { label: '대시보드', to: '/app', active: true },
  { label: '순찰 관리', to: '/app/patrol' },
  { label: '이벤트 관리', to: '/app/events' },
  { label: '로봇 관리', to: '/app/robots' },
  { label: '통계', to: '/app/stats' },
]

export default function Dashboard() {
  const navigate = useNavigate()
  const { theme, toggle } = useTheme()
  const clock = useClockText()
  const { data: events } = useEvents()
  const { data: robots } = useRobots()

  // 긴급(발견 즉시 기록) — 목록 맨 위 고정 / 정상(일괄 기록) — 아래 그룹
  const urgentEvents = (events ?? []).filter((e) => e.riskLevel === '긴급')
  const normalEvents = (events ?? []).filter((e) => e.riskLevel !== '긴급')
  const hasUrgent = urgentEvents.length > 0

  // 상단바 상태칩 — 첫 로봇 기준 (백엔드 연동 시 그대로 값만 교체)
  const lead = (robots ?? [])[0]

  // 긴급 알림 모달 — push 도착 시에만 (기존 동작 유지)
  const [alertEvent, setAlertEvent] = useState<PatrolEvent | null>(null)
  useEmergencyAlert((event) => {
    if (!isEmergencySeen(event.id)) setAlertEvent(event)
  })
  const dismissAlert = () => {
    if (alertEvent) markEmergencySeen(alertEvent.id)
    setAlertEvent(null)
  }

  return (
    <div className="r0ki" data-theme={theme}>
      <div className="wrap">
        <div className="stage">
          <div className="scene" />

          {/* ── 상단바 ── */}
          <div className="topbar glass g2" style={{ borderRadius: 'var(--r-pill)' }}>
            <div className="brand"><span className="core" /> R0-Ki</div>
            <nav className="nav" aria-label="주 메뉴">
              {NAV_ITEMS.map((item) =>
                item.active ? (
                  <span key={item.label} className="nv" aria-pressed="true">{item.label}</span>
                ) : (
                  <Link key={item.label} to={item.to} className="nv">{item.label}</Link>
                ),
              )}
            </nav>
            <div className="sp" />
            {lead && (
              <span className="statchip">
                <span className={hasUrgent ? 'd live' : 'd'} style={{ background: hasUrgent ? 'var(--urgent)' : 'var(--patrol)' }} />
                {hasUrgent ? `${lead.name} 긴급 대응 중` : `${lead.name} ${lead.status}`}
                <b>배터리 {lead.battery}%</b>
              </span>
            )}
            <Link to="/app/events" className="alarmbtn" aria-label={`긴급 알림 ${urgentEvents.length}건`}>
              알림{urgentEvents.length > 0 && <span className="badge num">{urgentEvents.length}</span>}
            </Link>
            <div className="clock num">
              {clock}<small>한국시간</small>
            </div>
            <button type="button" className="themebtn" onClick={toggle}>
              {theme === 'crystal' ? '야간 모드' : '주간 모드'}
            </button>
          </div>

          {/* ── HMI: 지도 + (영상 / 이력) ── */}
          <div className="hmi">
            <div className="mapzone glass g2">
              <div className="bigmap">
                <R0KiPatrolMap
                  urgent={hasUrgent ? { label: `응급상황 ${urgentEvents[0]?.time ?? ''}` } : null}
                  robotName={lead ? `R0-Ki ${lead.name}` : 'R0-Ki 1호기'}
                />
              </div>
            </div>

            <div className="side">
              {/* 실시간 탐지 영상 */}
              <div className="zone glass g2">
                <div className="zh">
                  <span className="zl">실시간 탐지 영상</span>
                  <span className="chip">
                    <span className={hasUrgent ? 'd live' : 'd'} style={{ background: hasUrgent ? 'var(--alert)' : 'var(--patrol)' }} />
                    {hasUrgent ? '긴급 녹화' : '실시간'}
                    <span className="t num">{clock}</span>
                  </span>
                </div>
                <R0KiLiveCam urgent={hasUrgent} />
                <div className="camnow">
                  {hasUrgent && (
                    <span className="cn cnu"><i className="dot" style={{ background: 'var(--urgent)' }} />쓰러짐 <b>{urgentEvents.length}</b></span>
                  )}
                  <span className="cn"><i className="dot" style={{ background: 'var(--detect)' }} />출입문 <b>1</b></span>
                  <span className="cn cnr">정확도 96%</span>
                </div>
              </div>

              {/* 최근 순찰 이력 */}
              <div className="zone glass g2 histzone">
                <div className="zh">
                  <span className="zl">최근 순찰 이력</span>
                  <span className="chip"><span className="d" style={{ background: 'var(--graphic)' }} />최신순</span>
                </div>

                <div className="hist">
                  {urgentEvents.length > 0 && (
                    <>
                      <div className="hgrp hgrp-u">긴급 이벤트 · 발견 즉시 기록</div>
                      {urgentEvents.map((e) => (
                        <Link key={e.id} to={`/app/events/${e.id}`} className="hr urgent">
                          <span className="tm">{e.time}</span>
                          <span className="hb" />
                          <span className="hc">
                            <span className="hrow">
                              <span className="ht">{e.type}{e.subType ? ` · ${e.subType}` : ''}</span>
                              <span className="ubadge">긴급</span>
                            </span>
                            <span className="hs">{e.location}</span>
                          </span>
                        </Link>
                      ))}
                    </>
                  )}

                  <div className="hgrp">순찰 기록 · 최신순</div>
                  {normalEvents.map((e) => (
                    <Link key={e.id} to={`/app/events/${e.id}`} className="hr">
                      <span className="tm">{e.time}</span>
                      <span className="hb" style={{ background: dotColor(e) }} />
                      <span className="hc">
                        <span className="ht">{e.type}{e.status === '처리완료' ? ' · 처리 완료' : ' 감지'}</span>
                        <span className="hs">{e.location} · {e.robotId}</span>
                      </span>
                    </Link>
                  ))}
                  {(events ?? []).length === 0 && (
                    <div className="hgrp">기록된 이력이 없습니다</div>
                  )}
                </div>

                {/* 다음 순찰 지점 — 하단 고정 */}
                <div className="nextwrap">
                  <div className="zl" style={{ marginBottom: 'var(--s3)' }}>다음 순찰 지점</div>
                  <div className="next">
                    <div>
                      <div className="next-n">{hasUrgent ? '현장 대기 중 · 관제 확인 요청' : '정상 순찰 진행 중'}</div>
                      <div className="next-m">{hasUrgent ? '순찰 일시 정지' : '다음 지점으로 이동'}</div>
                    </div>
                    <div className="next-v num">7<span className="u">/12</span></div>
                  </div>
                  <div className="prog"><i style={{ width: '58%' }} /></div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 긴급 알림 모달 (기존 push 동작 유지) */}
      {alertEvent && (
        <EmergencyAlertModal
          open={Boolean(alertEvent)}
          event={alertEvent}
          onClose={dismissAlert}
          onConfirm={() => {
            const id = alertEvent.id
            dismissAlert()
            navigate(`/app/events/${id}`)
          }}
        />
      )}
    </div>
  )
}

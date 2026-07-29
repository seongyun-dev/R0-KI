import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { R0KiShell, useClockText } from '../components/layout/R0KiShell'
import { R0KiLiveCam } from '../features/dashboard/R0KiLiveCam'
import { R0KiPatrolMap } from '../features/dashboard/R0KiPatrolMap'
import { ComplexMap } from '../features/dashboard/ComplexMap'
import { useComplexMap } from '../features/dashboard/useComplexMap'
import { EmergencyAlertModal } from '../features/dashboard/EmergencyAlertModal'
import { useEmergencyAlert, isEmergencySeen, markEmergencySeen } from '../features/dashboard/useEmergencyAlert'
import { useEvents } from '../features/events/useEvents'
import { useRobots } from '../features/robots/useRobot'
import type { PatrolEvent } from '../types/domain'

/* R0-Ki · AURA GLASS 대시보드 (리디자인 시안 그대로)
   공용 셸(R0KiShell: 상단바·테마·시계) + 순찰 지도 + 실시간 탐지 영상 + 최근 순찰 이력.
   데이터는 기존 훅(useEvents/useRobots) 연결 — API 연동 시 값만 바뀐다. */

/* 이력 상태점 색 — 명도 램프 (처리완료=순찰, 그 외 감지) */
function dotColor(e: PatrolEvent) {
  if (e.status === '처리완료') return 'var(--patrol)'
  return 'var(--detect)'
}

/* 로봇 상태 색 — 상태 팔레트(--st-*). 색상만 다르고 톤은 같은 계열 */
const STATUS_COLOR: Record<string, string> = {
  순찰중: 'var(--st-patrol)',
  대기: 'var(--st-idle)',
  충전중: 'var(--st-charge)',
  오류: 'var(--urgent)',
  오프라인: 'var(--st-idle)',
}
const statusColor = (status: string) => STATUS_COLOR[status] ?? 'var(--st-idle)'

/* R0-Ki 미니 로봇 — 로봇 요약 칩용 아이콘. 안테나 + 바이저(LED 눈) + 바퀴 */
function MiniBot() {
  return (
    <svg className="mini" viewBox="0 0 26 26" aria-hidden>
      <line className="ant" x1="13" y1="4.8" x2="13" y2="7.6" />
      <circle className="tip" cx="13" cy="3.4" r="1.6" />
      <rect className="body" x="4.6" y="7.6" width="16.8" height="12.2" rx="5.4" />
      <rect className="visor" x="7.5" y="10.4" width="11" height="4.6" rx="2.3" />
      <circle className="led" cx="10.7" cy="12.7" r="1.15" />
      <circle className="led" cx="15.3" cy="12.7" r="1.15" />
      <circle className="wheel" cx="9.3" cy="21.6" r="1.9" />
      <circle className="wheel" cx="16.7" cy="21.6" r="1.9" />
    </svg>
  )
}

export default function Dashboard() {
  const navigate = useNavigate()
  const clock = useClockText()
  const { data: events } = useEvents()
  const { data: robots } = useRobots()
  const { data: mapData } = useComplexMap()

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
    <>
      <R0KiShell
        active="dashboard"
        statusChip={
          lead ? (
            <span className="statchip">
              <span className={hasUrgent ? 'd live' : 'd'} style={{ background: hasUrgent ? 'var(--urgent)' : 'var(--patrol)' }} />
              {hasUrgent ? `${lead.name} 긴급 대응 중` : `${lead.name} ${lead.status}`}
              <b>
                배터리 {lead.battery != null ? `${lead.battery}%` : '확인 불가'}
              </b>
            </span>
          ) : undefined
        }
      >
        {/* ── HMI: 지도 + (영상 / 이력) ── */}
        <div className="hmi">
          <div className="mapzone glass g2">
            <div className="bigmap">
              {mapData ? (
                <ComplexMap
                  map={mapData.map}
                  robot={mapData.robot}
                  pins={mapData.pins}
                  checkpoints={mapData.checkpoints}
                />
              ) : (
                <R0KiPatrolMap
                  urgent={hasUrgent ? { label: `응급상황 ${urgentEvents[0]?.time ?? ''}` } : null}
                  robotName={lead ? `R0-Ki ${lead.name}` : 'R0-Ki 1호기'}
                />
              )}
            </div>

            {/* 로봇 요약 — 지도 아래 한 줄. 이름·상태·배터리, 클릭 시 로봇 상세로 */}
            {(robots ?? []).length > 0 && (
              <div className="botlist">
                {(robots ?? []).map((r) => (
                  <Link key={r.id} to={`/app/robots/${r.id}`} className="botitem">
                    <MiniBot />
                    <span className="d" style={{ background: statusColor(r.status) }} />
                    <span className="nm">{r.name}</span>
                    <span className="st" style={{ color: statusColor(r.status) }}>{r.status}</span>
                    <span className="bar" aria-hidden>
                      <i
                        style={{
                          width: `${r.battery}%`,
                          ...(r.battery <= 25 ? { background: 'var(--urgent)' } : null),
                        }}
                      />
                    </span>
                    <b className="pct num">{r.battery}%</b>
                  </Link>
                ))}
              </div>
            )}
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
            </div>
          </div>
        </div>
      </R0KiShell>

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
    </>
  )
}

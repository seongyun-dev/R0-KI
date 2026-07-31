import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { R0KiShell, useClockText } from '../components/layout/R0KiShell'
import { R0KiLiveCam } from '../features/dashboard/R0KiLiveCam'
import { R0KiPatrolMap } from '../features/dashboard/R0KiPatrolMap'
import { ComplexMap } from '../features/dashboard/ComplexMap'
import { robotMapPosition } from '../features/dashboard/robotMapPosition'
import { useComplexMap } from '../features/dashboard/useComplexMap'
import { EmergencyAlertModal } from '../features/dashboard/EmergencyAlertModal'
import { useEmergencyAlert, isEmergencySeen, markEmergencySeen } from '../features/dashboard/useEmergencyAlert'
import { PatrolCompleteModal } from '../features/dashboard/PatrolCompleteModal'
import {
  usePatrolComplete,
  isPatrolDoneSeen,
  markPatrolDoneSeen,
} from '../features/dashboard/usePatrolComplete'
import { useEvents } from '../features/events/useEvents'
import { useRobots } from '../features/robots/useRobot'
import type { Patrol, PatrolEvent } from '../types/domain'

/* R0-Ki · AURA GLASS 대시보드 (리디자인 시안 그대로)
   공용 셸(R0KiShell: 상단바·테마·시계) + 순찰 지도 + 실시간 탐지 영상 + 이벤트 이력.
   데이터는 기존 훅(useEvents/useRobots) 연결 — API 연동 시 값만 바뀐다. */

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
  const { data: events, isLoading: eventsLoading, refetch: refetchEvents } = useEvents()
  const { data: robots } = useRobots()
  const { data: mapData } = useComplexMap()

  /* 이벤트 이력 — 아직 처리하지 않은 '탐지' 상태만 띄운다 (처리중·처리완료 제외).
     긴급(발견 즉시 기록)은 목록 맨 위 고정 / 나머지는 아래 그룹 */
  const detectedEvents = (events ?? []).filter((e) => e.status === '탐지')
  const urgentEvents = detectedEvents.filter((e) => e.riskLevel === '긴급')
  const normalEvents = detectedEvents.filter((e) => e.riskLevel !== '긴급')
  const hasUrgent = urgentEvents.length > 0

  /* 탐지 영상 아래 요약 — 전부 실데이터에서 뽑는다.
     예전엔 "출입문 1 / 정확도 96%"가 리터럴로 박혀 있어 상시 같은 값이 떴다.
     근거가 없는 값은 아예 표시하지 않는다(관제 화면에서 고정 숫자는 오독을 부른다). */
  // 긴급 세부 유형 — subType(“쓰러짐 의심”)이 있으면 그걸, 없으면 이벤트 유형
  const urgentLabel = urgentEvents[0]?.subType ?? urgentEvents[0]?.type
  // 긴급 외 탐지 중 가장 많은 유형 한 건
  const topNormal = Object.entries(
    normalEvents.reduce<Record<string, number>>((acc, e) => {
      acc[e.type] = (acc[e.type] ?? 0) + 1
      return acc
    }, {}),
  ).sort((a, b) => b[1] - a[1])[0]
  // 평균 신뢰도 — confidence 가 있는 건만
  const confidences = detectedEvents
    .map((e) => e.confidence)
    .filter((v): v is number => typeof v === 'number')
  const avgConfidence = confidences.length
    ? Math.round(confidences.reduce((sum, v) => sum + v, 0) / confidences.length)
    : undefined

  // 상단바 상태칩 — 첫 로봇 기준 (백엔드 연동 시 그대로 값만 교체)
  const lead = (robots ?? [])[0]

  /* 지도에 띄울 로봇 — 하단 로봇 목록에서 고른다.
     기본값은 순찰중인 로봇(없으면 첫 로봇). 순찰중이면 위치 + 이동 경로,
     대기·충전중이면 마지막 위치만 그린다. */
  const [pickedRobotId, setPickedRobotId] = useState<string>()
  // 순찰 중 로봇 전체 보기 — 켜면 개별 선택 대신 순찰 중인 로봇을 모두 띄운다
  const [showAllPatrolling, setShowAllPatrolling] = useState(false)
  const robotList = robots ?? []
  const patrollingRobots = robotList.filter((r) => r.status === '순찰중')
  const selectedRobot =
    robotList.find((r) => r.id === pickedRobotId) ?? patrollingRobots[0] ?? robotList[0]
  const isPatrolling = showAllPatrolling || selectedRobot?.status === '순찰중'
  const mapRobot = robotMapPosition(selectedRobot, mapData?.robot)
  const mapRobots = patrollingRobots
    .map((r) => robotMapPosition(r, mapData?.robot))
    .filter((r): r is NonNullable<typeof r> => Boolean(r))

  const pickRobot = (id: string) => {
    setShowAllPatrolling(false)
    setPickedRobotId(id)
  }

  // 긴급 알림 모달 — push 도착 시에만 (기존 동작 유지)
  const [alertEvent, setAlertEvent] = useState<PatrolEvent | null>(null)
  useEmergencyAlert((event) => {
    if (!isEmergencySeen(event.id)) setAlertEvent(event)
  })
  const dismissAlert = () => {
    if (alertEvent) markEmergencySeen(alertEvent.id)
    setAlertEvent(null)
  }

  /* 순찰 완료 모달 — 순찰이 끝나면 뜨고, [확인] 을 누르면 이벤트 이력을 다시 불러온다
     (순찰 중 탐지된 이벤트가 이력에 반영되도록) */
  const [donePatrol, setDonePatrol] = useState<Patrol | null>(null)
  usePatrolComplete((patrol) => {
    if (!isPatrolDoneSeen(patrol.id)) setDonePatrol(patrol)
  })
  const confirmPatrolDone = () => {
    if (donePatrol) markPatrolDoneSeen(donePatrol.id)
    setDonePatrol(null)
    refetchEvents()
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
                  robot={showAllPatrolling ? undefined : mapRobot}
                  robots={showAllPatrolling ? mapRobots : undefined}
                  pins={mapData.pins}
                  checkpoints={mapData.checkpoints}
                  patrolling={isPatrolling}
                  bottomRight={
                    patrollingRobots.length > 0 ? (
                      <button
                        type="button"
                        className="botall"
                        aria-pressed={showAllPatrolling}
                        onClick={() => setShowAllPatrolling(true)}
                      >
                        <svg viewBox="0 0 24 24" aria-hidden>
                          <circle cx="7" cy="8" r="2.6" />
                          <circle cx="17" cy="8" r="2.6" />
                          <circle cx="12" cy="16.5" r="2.6" />
                        </svg>
                        순찰 중 로봇 전체 보기
                      </button>
                    ) : undefined
                  }
                />
              ) : (
                <R0KiPatrolMap
                  urgent={hasUrgent ? { label: `응급상황 ${urgentEvents[0]?.time ?? ''}` } : null}
                  robotName={lead ? `R0-Ki ${lead.name}` : 'R0-Ki 1호기'}
                />
              )}
            </div>

            {/* 로봇 요약 — 지도 아래 한 줄. 클릭하면 그 로봇을 지도에 띄운다
                (순찰중: 위치 + 이동 경로 / 대기·충전중: 마지막 위치만) */}
            {robotList.length > 0 && (
              <div className="botlist">
                {robotList.map((r) => {
                  const battery = r.battery
                  const hasBattery = battery != null
                  const picked = !showAllPatrolling && r.id === selectedRobot?.id

                  return (
                    <button
                      key={r.id}
                      type="button"
                      className="botitem"
                      aria-pressed={picked}
                      aria-label={`${r.name} ${r.status} — 지도에 ${r.status === '순찰중' ? '위치와 이동 경로' : '마지막 위치'} 표시`}
                      onClick={() => pickRobot(r.id)}
                    >
                      <MiniBot />
                      <span className="d" style={{ background: statusColor(r.status) }} />
                      <span className="nm">{r.name}</span>
                      <span className="st" style={{ color: statusColor(r.status) }}>{r.status}</span>
                      <span
                        className={`bar${hasBattery ? '' : ' unknown'}`}
                        aria-label={hasBattery ? `배터리 ${battery}%` : '배터리 잔량 미수신'}
                        role="img"
                      >
                        {battery != null && (
                          <i
                            style={{
                              width: `${battery}%`,
                              ...(battery <= 25 ? { background: 'var(--urgent)' } : null),
                            }}
                          />
                        )}
                      </span>
                      <b className={`pct${hasBattery ? ' num' : ' unknown'}`}>
                        {hasBattery ? `${battery}%` : '--%'}
                      </b>
                    </button>
                  )
                })}
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
                {hasUrgent && urgentLabel && (
                  <span className="cn cnu"><i className="dot" style={{ background: 'var(--urgent)' }} />{urgentLabel} <b>{urgentEvents.length}</b></span>
                )}
                {topNormal && (
                  <span className="cn"><i className="dot" style={{ background: 'var(--detect)' }} />{topNormal[0]} <b>{topNormal[1]}</b></span>
                )}
                {avgConfidence != null && <span className="cn cnr">평균 신뢰도 {avgConfidence}%</span>}
              </div>
            </div>

            {/* 이벤트 이력 */}
            <div className="zone glass g2 histzone">
              <div className="zh">
                <span className="zl">이벤트 이력</span>
                <span className="zhtools">
                  <button
                    type="button"
                    className="zrefresh"
                    onClick={refetchEvents}
                    disabled={eventsLoading}
                    aria-label="이벤트 이력 새로고침"
                  >
                    <svg viewBox="0 0 24 24" aria-hidden>
                      <path d="M20 11.5a8 8 0 1 1-2.6-5.4" />
                      <path d="M20 4v5h-5" />
                    </svg>
                  </button>
                  <span className="chip"><span className="d" style={{ background: 'var(--graphic)' }} />최신순</span>
                </span>
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

                <div className="hgrp">탐지 이벤트 · 최신순</div>
                {normalEvents.map((e) => (
                  <Link key={e.id} to={`/app/events/${e.id}`} className="hr">
                    <span className="tm">{e.time}</span>
                    <span className="hb" style={{ background: 'var(--detect)' }} />
                    <span className="hc">
                      <span className="ht">{e.type} 탐지</span>
                      <span className="hs">{e.location} · {e.robotId}</span>
                    </span>
                  </Link>
                ))}
                {detectedEvents.length === 0 && (
                  <div className="hgrp">탐지된 이벤트가 없습니다</div>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* 순찰 완료 모달 — 확인 시 이벤트 이력 새로고침.
            긴급 알림이 떠 있으면 그쪽을 먼저 처리하도록 뒤로 미룬다.
            r0ki CSS 는 .r0ki 하위로만 스코프되므로 반드시 셸 안에서 렌더한다 */}
        {donePatrol && !alertEvent && (
          <PatrolCompleteModal patrol={donePatrol} onConfirm={confirmPatrolDone} />
        )}
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

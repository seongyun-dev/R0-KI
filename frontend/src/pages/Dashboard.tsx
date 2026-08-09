import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { R0KiShell, useClockText } from '../components/layout/R0KiShell'
import { R0KiLiveCam } from '../features/dashboard/R0KiLiveCam'
import { R0KiPatrolMap } from '../features/dashboard/R0KiPatrolMap'
import { MonitoringMap } from '../features/dashboard/MonitoringMap'
import { worldToDashboardGrid } from '../features/dashboard/mapCoordinateMetadata'
import { robotMapPosition } from '../features/dashboard/robotMapPosition'
import { useComplexMap } from '../features/dashboard/useComplexMap'
import { useRobotLocations } from '../features/dashboard/useRobotLocations'
import { useEmergencyEventStore } from '../features/dashboard/useEmergencyEventStore'
import { useSelectedRobotLocation } from '../features/dashboard/useSelectedRobotLocation'
import { PatrolCompleteModal } from '../features/dashboard/PatrolCompleteModal'
import { PatrolStartModal } from '../features/dashboard/PatrolStartModal'
import { PatrolStopModal } from '../features/dashboard/PatrolStopModal'
import {
  usePatrolComplete,
  isPatrolDoneSeen,
  markPatrolDoneSeen,
} from '../features/dashboard/usePatrolComplete'
import { useEvents } from '../features/events/useEvents'
import { useRobots } from '../features/robots/useRobot'
import { robotStatusLabel } from '../api/mappers'
import { patrolsApi } from '../api/services'
import type { PatrolCompletedSseEvent } from '../api/contracts'
import type { ComplexMapData, Robot } from '../types/domain'

const PATROL_START_CONFIRM_TIMEOUT_MS = 16_000

type PendingPatrolStart = {
  patrolId: number
  robotId: string
  robotName: string
  requestedAt: number
}

function emergencyPoint(x: number, y: number, map: ComplexMapData) {
  return worldToDashboardGrid(map, { x, y })
}

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
  const clock = useClockText()
  const { data: events, isLoading: eventsLoading, refetch: refetchEvents } = useEvents()
  const { data: robots, refetch: refetchRobots } = useRobots()
  const { data: mapData } = useComplexMap()
  const emergencyEvents = useEmergencyEventStore((state) => state.events)
  const { locations: liveRobotLocations, statuses: liveRobotStatuses } =
    useRobotLocations(mapData?.map)
  const terminalStatusSignature = Object.entries(liveRobotStatuses)
    .filter(([, status]) => status === 'IDLE' || status === 'OFFLINE' || status === 'ERROR')
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([robotId, status]) => `${robotId}:${status}`)
    .join('|')

  useEffect(() => {
    if (terminalStatusSignature) void refetchRobots()
  }, [terminalStatusSignature, refetchRobots])

  const emergencyPins = mapData
    ? emergencyEvents.flatMap((event) => {
        if (
          event.mapId == null ||
          String(event.mapId) !== String(mapData.map.mapId) ||
          event.x == null ||
          event.y == null
        ) return []
        const point = emergencyPoint(event.x, event.y, mapData.map)
        return point
          ? [{
              id: event.id,
              label: event.subType ?? event.type,
              detail: `${event.time} · ${event.location}`,
              ...point,
              tone: 'danger' as const,
            }]
          : []
      })
    : []

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
  const rawStatusForRobot = (robot: Robot) =>
    liveRobotStatuses[String(robot.backendId ?? robot.id)]
  const hasLivePatrolStatus = (robot: Robot) => {
    const status = rawStatusForRobot(robot)
    return status === 'PATROLLING' || status === 'OBSTACLE_STOP'
  }
  const robotList = (robots ?? []).map((robot) => {
    const liveStatus = rawStatusForRobot(robot)
    return liveStatus ? { ...robot, status: robotStatusLabel(liveStatus) } : robot
  })
  const patrollingRobots = robotList.filter(
    (robot) => robot.status === '순찰중' || hasLivePatrolStatus(robot),
  )
  const selectedRobot =
    robotList.find((r) => r.id === pickedRobotId) ?? patrollingRobots[0] ?? robotList[0]
  const selectedRobotBackendId = selectedRobot?.backendId ?? selectedRobot?.id
  const selectedRobotLiveStatus = selectedRobotBackendId == null
    ? undefined
    : liveRobotStatuses[String(selectedRobotBackendId)]
  const isSelectedRobotLivePatrolling =
    selectedRobotLiveStatus === 'PATROLLING' || selectedRobotLiveStatus === 'OBSTACLE_STOP'
  const shouldStreamSelectedRobot = isSelectedRobotLivePatrolling
  const { data: selectedLocation } = useSelectedRobotLocation(
    selectedRobotBackendId,
    mapData?.map,
  )
  const currentSelectedLocation =
    selectedLocation?.robot.id === String(selectedRobotBackendId) ? selectedLocation : undefined
  const selectedLiveLocation = selectedRobot
    ? liveRobotLocations.find((location) =>
        location.id === String(selectedRobotBackendId),
      )
    : undefined
  const selectedLocationFromApi = currentSelectedLocation?.robot
  const mapRobot = selectedLocationFromApi
    ? {
        ...selectedLocationFromApi,
        ...(selectedLiveLocation
          ? {
              x: selectedLiveLocation.x,
              y: selectedLiveLocation.y,
              worldX: selectedLiveLocation.worldX,
              worldY: selectedLiveLocation.worldY,
              ...(selectedLiveLocation.heading == null
                ? {}
                : { heading: selectedLiveLocation.heading }),
              updatedAt: selectedLiveLocation.updatedAt,
            }
          : {}),
      }
    : selectedLiveLocation ?? robotMapPosition(selectedRobot, mapData?.robot)
  const isPatrolling =
    (showAllPatrolling && patrollingRobots.length > 0) ||
    isSelectedRobotLivePatrolling ||
    (selectedRobotLiveStatus == null && (
      currentSelectedLocation?.showRoute || selectedRobot?.status === '순찰중'
    ))
  const mapRobots = patrollingRobots
    .map((robot) =>
      liveRobotLocations.find((location) =>
        location.id === String(robot.backendId ?? robot.id),
      ) ?? robotMapPosition(robot, mapData?.robot),
    )
    .filter((r): r is NonNullable<typeof r> => Boolean(r))

  /* 순찰 시작 — 대기 로봇을 누르면 뜨는 확인 모달. 시작 뒤 되돌리는 버튼은 두지 않기로 했으므로
     실패는 모달에 남겨 다시 시도할 수 있게 하고, 성공했을 때만 닫는다. */
  const [patrolTarget, setPatrolTarget] = useState<Robot | null>(null)
  const [startingPatrol, setStartingPatrol] = useState(false)
  const [patrolError, setPatrolError] = useState<string>()
  const [pendingPatrolStart, setPendingPatrolStart] = useState<PendingPatrolStart>()
  const [stopTarget, setStopTarget] = useState<Robot | null>(null)
  const [stoppingPatrol, setStoppingPatrol] = useState(false)
  const [stopError, setStopError] = useState<string>()
  const [toast, setToast] = useState<string>()

  const pendingPatrolIdForRobot = (robot: Robot) => {
    const robotId = String(robot.backendId ?? robot.id)
    return pendingPatrolStart?.robotId === robotId ? pendingPatrolStart.patrolId : undefined
  }
  const effectiveActivePatrolId = (robot: Robot) =>
    robot.activePatrolId ?? pendingPatrolIdForRobot(robot)
  const canStopRobot = (robot: Robot) =>
    hasLivePatrolStatus(robot) || effectiveActivePatrolId(robot) != null

  // 결과 알림 — 고령 사용자 기준이라 로봇 상세(2.6초)보다 길게 띄운다
  useEffect(() => {
    if (!toast) return
    const timer = setTimeout(() => setToast(undefined), 4200)
    return () => clearTimeout(timer)
  }, [toast])

  const pendingPatrolStatus = pendingPatrolStart
    ? liveRobotStatuses[pendingPatrolStart.robotId]
    : undefined

  useEffect(() => {
    if (!pendingPatrolStart) return

    if (pendingPatrolStatus === 'PATROLLING' || pendingPatrolStatus === 'OBSTACLE_STOP') {
      setToast(`${pendingPatrolStart.robotName} 순찰 시작을 확인했습니다.`)
      setPendingPatrolStart(undefined)
      void refetchRobots()
      return
    }

    if (pendingPatrolStatus === 'OFFLINE' || pendingPatrolStatus === 'ERROR') {
      setToast(`${pendingPatrolStart.robotName} 시작을 확인하지 못했습니다. 로봇 상태를 확인해 주세요.`)
      setPendingPatrolStart(undefined)
      void refetchRobots()
      return
    }

    let cancelled = false
    const remaining = Math.max(
      0,
      pendingPatrolStart.requestedAt + PATROL_START_CONFIRM_TIMEOUT_MS - Date.now(),
    )
    const timer = window.setTimeout(() => {
      void patrolsApi.detail(pendingPatrolStart.patrolId)
        .then((detail) => {
          if (cancelled) return
          setToast(
            detail.patrolStatus === 'FAILED'
              ? `${pendingPatrolStart.robotName} 순찰 시작에 실패했습니다. 장비 상태를 확인해 주세요.`
              : `${pendingPatrolStart.robotName} 시작 응답을 확인하지 못했습니다. 안전 상태를 확인해 주세요.`,
          )
        })
        .catch(() => {
          if (!cancelled) {
            setToast(`${pendingPatrolStart.robotName} 시작 결과를 확인하지 못했습니다. 안전 상태를 확인해 주세요.`)
          }
        })
        .finally(() => {
          if (cancelled) return
          setPendingPatrolStart(undefined)
          void refetchRobots()
        })
    }, remaining)

    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [pendingPatrolStart, pendingPatrolStatus, refetchRobots])

  const startPatrol = async () => {
    if (!patrolTarget || startingPatrol || pendingPatrolStart) return
    const parsed = Number(patrolTarget.backendId ?? patrolTarget.id)
    if (!Number.isFinite(parsed)) {
      setPatrolError('로봇 번호를 확인할 수 없어 순찰을 시작하지 못했습니다.')
      return
    }

    setStartingPatrol(true)
    setPatrolError(undefined)
    try {
      const targetName = patrolTarget.name
      const response = await patrolsApi.start({ robotId: parsed })
      setPendingPatrolStart({
        patrolId: response.patrolId,
        robotId: String(response.robotId),
        robotName: targetName,
        requestedAt: Date.now(),
      })
      setToast(`${targetName} 순찰 시작 요청을 접수했습니다. 로봇 응답을 기다립니다.`)
      setPatrolTarget(null)
      void refetchRobots()
    } catch (error) {
      setPatrolError(error instanceof Error ? error.message : '순찰 시작에 실패했습니다.')
    } finally {
      setStartingPatrol(false)
    }
  }

  const stopPatrol = async () => {
    if (!stopTarget || stoppingPatrol) return
    if (stopTarget.activePatrolId == null) {
      setStopError('진행 중인 순찰 번호를 확인할 수 없습니다. 로봇 목록을 새로고침해 주세요.')
      return
    }

    setStoppingPatrol(true)
    setStopError(undefined)
    try {
      // API 성공은 STOP_PATROL 접수이며, 최종 STOPPED 전환은 로봇의 성공 ACK가 처리한다.
      await patrolsApi.stop(stopTarget.activePatrolId)
      setToast(`${stopTarget.name} 순찰 종료를 요청했습니다.`)
      if (pendingPatrolStart?.patrolId === stopTarget.activePatrolId) {
        setPendingPatrolStart(undefined)
      }
      setStopTarget(null)
      void refetchRobots()
    } catch (error) {
      setStopError(error instanceof Error ? error.message : '순찰 종료 요청에 실패했습니다.')
    } finally {
      setStoppingPatrol(false)
    }
  }

  /* 로봇 칩 클릭 — 지도 선택과 함께 대기는 시작 확인, 순찰중은 종료 확인 모달을 연다.
     순찰 ID가 누락된 경우에도 종료 버튼 자체는 보여주고, 확인 시 모달에서 원인을 안내한다. */
  const pickRobot = (robot: Robot) => {
    setShowAllPatrolling(false)
    setPickedRobotId(robot.id)
    if (canStopRobot(robot)) {
      const activePatrolId = effectiveActivePatrolId(robot)
      setPatrolTarget(null)
      setStopError(
        activePatrolId == null
          ? '진행 중인 순찰 번호를 확인할 수 없습니다. 백엔드 연결과 순찰 기록을 확인해 주세요.'
          : undefined,
      )
      setStopTarget({ ...robot, activePatrolId })
    } else if (robot.status === '대기') {
      setPatrolError(undefined)
      setPatrolTarget(robot)
    }
  }

  /* 순찰 완료 모달 — 순찰이 끝나면 뜨고, [확인] 을 누르면 이벤트 이력을 다시 불러온다
     (순찰 중 탐지된 이벤트가 이력에 반영되도록) */
  const [donePatrol, setDonePatrol] = useState<PatrolCompletedSseEvent | null>(null)
  usePatrolComplete((patrol) => {
    if (!isPatrolDoneSeen(String(patrol.patrolId))) setDonePatrol(patrol)
    void refetchRobots()
  })
  const confirmPatrolDone = () => {
    if (donePatrol) markPatrolDoneSeen(String(donePatrol.patrolId))
    setDonePatrol(null)
    refetchEvents()
  }

  return (
    <>
      <R0KiShell
        active="dashboard"
        /* 로봇 이름은 길이 제한이 없어 상단바를 밀어낸다(로그아웃이 잘려 나갔다).
           이름만 따로 떼어 말줄임하고, 상태·배터리는 항상 온전히 남긴다. */
        statusChip={
          lead ? (
            <span className="statchip" title={`${lead.name} ${lead.status}`}>
              <span className={hasUrgent ? 'd live' : 'd'} style={{ background: hasUrgent ? 'var(--urgent)' : 'var(--patrol)' }} />
              <span className="nm">{lead.name}</span>
              <span className="stt">{hasUrgent ? '긴급 대응 중' : lead.status}</span>
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
                <MonitoringMap
                  map={mapData.map}
                  robot={showAllPatrolling ? undefined : mapRobot}
                  robots={showAllPatrolling ? mapRobots : undefined}
                  pins={[...mapData.pins, ...emergencyPins]}
                  checkpoints={mapData.checkpoints}
                  patrolling={isPatrolling}
                  bottomRight={
                    <>
                      <Link className="mapsetup-mapbtn" to="/app/test/map-setup">
                        지도/순찰 경로 재설정
                      </Link>
                      {patrollingRobots.length > 0 && (
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
                      )}
                    </>
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
                  const stoppable = canStopRobot(r)

                  return (
                    <button
                      key={r.id}
                      type="button"
                      className="botitem"
                      aria-pressed={picked}
                      aria-label={
                        stoppable
                          ? `${r.name} ${r.status} — 지도에 위치와 이동 경로 표시, 순찰 종료 확인창 열기`
                          : r.status === '대기'
                            ? `${r.name} 대기 — 지도에 마지막 위치 표시, 순찰 시작 확인창 열기`
                            : `${r.name} ${r.status} — 지도에 마지막 위치 표시`
                      }
                      onClick={() => pickRobot(r)}
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
                      {/* 대기 로봇에만 붙는 안내 — 누르면 순찰이 시작된다는 걸 누르기 전에 보여준다.
                          아이콘만 두면 뜻이 전달되지 않으므로 글자를 함께 쓴다 */}
                      {r.status === '대기' && !stoppable && (
                        <span className="go" aria-hidden>
                          <svg viewBox="0 0 24 24"><path d="M8 5.5v13l11-6.5z" /></svg>
                          순찰 시작
                        </span>
                      )}
                      {stoppable && (
                        <span className="go stop" aria-hidden>
                          <svg viewBox="0 0 24 24"><rect x="6" y="6" width="12" height="12" rx="1" /></svg>
                          순찰 종료
                        </span>
                      )}
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
              <R0KiLiveCam
                urgent={hasUrgent}
                clockText={clock}
                robotId={shouldStreamSelectedRobot ? selectedRobotBackendId : undefined}
              />
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
        {donePatrol && (
          <PatrolCompleteModal patrol={donePatrol} onConfirm={confirmPatrolDone} />
        )}

        {/* 순찰 시작 확인 — 대기 로봇 칩을 눌렀을 때 */}
        {patrolTarget && (
          <PatrolStartModal
            robot={patrolTarget}
            starting={startingPatrol}
            error={patrolError}
            onCancel={() => {
              if (startingPatrol) return
              setPatrolTarget(null)
              setPatrolError(undefined)
            }}
            onConfirm={() => void startPatrol()}
          />
        )}

        {/* 순찰 종료 확인 — 순찰중 로봇 칩을 눌렀을 때 */}
        {stopTarget && (
          <PatrolStopModal
            robot={stopTarget}
            stopping={stoppingPatrol}
            error={stopError}
            onCancel={() => {
              if (stoppingPatrol) return
              setStopTarget(null)
              setStopError(undefined)
            }}
            onConfirm={() => void stopPatrol()}
          />
        )}

        <div className={`toast${toast ? ' on' : ''}`} role="status" aria-live="polite">
          <svg viewBox="0 0 24 24"><path d="M4 12.5 9.5 18 20 6.5" /></svg>
          <span>{toast}</span>
        </div>
      </R0KiShell>
    </>
  )
}

import { Suspense, lazy, useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { type ProjectedAnchor, layoutLeader } from '../components/robot/rokiLeaders'
import { R0KiShell } from '../components/layout/R0KiShell'
import { PatrolStartModal } from '../features/dashboard/PatrolStartModal'
import { PatrolStopModal } from '../features/dashboard/PatrolStopModal'
import { useComplexMap } from '../features/dashboard/useComplexMap'
import { useRobotLocations } from '../features/dashboard/useRobotLocations'
import { RobotEditDrawer } from '../features/robots/RobotEditDrawer'
import { useDeleteRobot, useRobot, useUpdateRobot } from '../features/robots/useRobot'
import { robotStatusLabel } from '../api/mappers'
import { patrolsApi } from '../api/services'
import type { Robot } from '../types/domain'

/* R0-Ki 로봇 상세 — 시안 R0Ki-robots-detail 무대형(rd-*) 그대로.
   중앙 로봇 히어로 + 타원 광원 받침 + 부위 콜아웃(지시선) + 궤도 카드.
   한 화면 고정. 순찰 시작/종료·상태 반영은 대시보드와 같은 SSE·ACK 흐름. */

// three.js 청크 분리 — 상세 진입 시 지연 로드 (기존 3D 로봇 모델 재사용)
const RobotDiagnosticView = lazy(() =>
  import('../components/robot/RobotDiagnosticView').then((m) => ({ default: m.RobotDiagnosticView })),
)

const PATROL_START_CONFIRM_TIMEOUT_MS = 16_000

type PendingPatrolStart = {
  patrolId: number
  robotId: string
  robotName: string
  requestedAt: number
}

/* 상태 점 색 — 명도 램프 */
const STATUS_DOT: Record<string, string> = {
  순찰중: 'var(--patrol)',
  대기: 'var(--offline)',
  충전중: 'var(--charge)',
  오류: 'var(--alert)',
  오프라인: 'var(--offline)',
  중단: 'var(--alert)',
  정상: 'var(--patrol)',
  점검필요: 'var(--detect)',
  완료: 'var(--offline)',
  진행중: 'var(--patrol)',
  실패: 'var(--alert)',
}
const dot = (label: string) => STATUS_DOT[label] ?? 'var(--detect)'

const PATROL_STATUS_LABEL: Record<string, string> = {
  IN_PROGRESS: '진행중',
  COMPLETED: '완료',
  STOPPED: '중단',
  FAILED: '실패',
}

function patrolTime(value: string | null) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleTimeString('ko-KR', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

/* 부위 콜아웃 박스 자리 — parts 순서(카메라/라이다/휠모터/구동부)와 1:1 대응.
   박스는 로봇에서 멀찍이 떨어뜨려 고정하고, 부위까지 잇는 지시선은 3D 좌표를
   투영해 SVG로 그린다 — 로봇이 회전하므로 CSS 고정 좌표로는 부위를 따라갈 수 없다. */
const PART_SLOTS = ['l c-cam', 'r c-lidar', 'r c-motor', 'l c-drive']

export default function RobotDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const robotId = id ?? 'R-01'
  const { data: loaded, isLoading, error, refetch } = useRobot(robotId)
  const { data: mapData } = useComplexMap()
  const { statuses: liveRobotStatuses } = useRobotLocations(mapData?.map)
  const updateRobot = useUpdateRobot()
  const deleteRobot = useDeleteRobot()
  const [drawerOpen, setDrawerOpen] = useState(false)
  // 수정 드로어 저장 결과(목업 — 서버 연동 시 mutation으로 교체)
  const [patch, setPatch] = useState<Partial<Robot> | null>(null)
  const [toast, setToast] = useState<string>()
  const [startModalOpen, setStartModalOpen] = useState(false)
  const [startingPatrol, setStartingPatrol] = useState(false)
  const [patrolError, setPatrolError] = useState<string>()
  const [pendingPatrolStart, setPendingPatrolStart] = useState<PendingPatrolStart>()
  const [stopModalOpen, setStopModalOpen] = useState(false)
  const [stoppingPatrol, setStoppingPatrol] = useState(false)
  const [stopError, setStopError] = useState<string>()

  // 지시선 — 3D 뷰가 넘겨준 부위 좌표로 매 프레임 SVG를 직접 갱신한다.
  // 상태로 두면 초당 30번 리렌더가 돌아 무대 전체가 다시 그려진다.
  const frameRef = useRef<HTMLDivElement>(null)
  const leadRefs = useRef<(SVGGElement | null)[]>([])
  const boxRefs = useRef<(HTMLDivElement | null)[]>([])

  const handleAnchors = useCallback((anchors: ProjectedAnchor[]) => {
    const frame = frameRef.current
    const canvas = frame?.querySelector<HTMLElement>('.rd-3d')
    if (!frame || !canvas) return
    const fr = frame.getBoundingClientRect()
    const cr = canvas.getBoundingClientRect()

    anchors.forEach((a, i) => {
      const g = leadRefs.current[i]
      const box = boxRefs.current[i]
      if (!g || !box) return

      const l = layoutLeader(a, fr, cr, box.getBoundingClientRect())
      const line = g.firstElementChild as SVGLineElement | null
      const dotEl = g.lastElementChild as SVGCircleElement | null
      line?.setAttribute('x1', String(l.x1))
      line?.setAttribute('y1', String(l.y1))
      line?.setAttribute('x2', String(l.x2))
      line?.setAttribute('y2', String(l.y2))
      dotEl?.setAttribute('cx', String(l.x2))
      dotEl?.setAttribute('cy', String(l.y2))
      g.style.opacity = String(l.opacity)
    })
  }, [])

  // 결과 알림 — 대시보드와 같이 고령 사용자 기준으로 길게 띄운다
  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(undefined), 4200)
    return () => clearTimeout(t)
  }, [toast])

  const baseRobot: Robot | undefined = loaded ? { ...loaded, ...patch } : undefined
  const robotKey = baseRobot ? String(baseRobot.backendId ?? baseRobot.id) : undefined
  const liveStatus = robotKey ? liveRobotStatuses[robotKey] : undefined
  const robot: Robot | undefined = baseRobot
    ? liveStatus
      ? { ...baseRobot, status: robotStatusLabel(liveStatus) }
      : baseRobot
    : undefined

  const parsedRobotId = Number(robot?.backendId ?? robot?.id)
  const patrolRobotId = Number.isFinite(parsedRobotId) ? parsedRobotId : undefined
  const recent = robot?.recentPatrols?.slice(0, 3) ?? []
  const inProgressPatrolId = robot?.recentPatrols?.find(
    (patrol) => patrol.patrolStatus === 'IN_PROGRESS',
  )?.patrolId
  const pendingPatrolId =
    pendingPatrolStart && robotKey && pendingPatrolStart.robotId === robotKey
      ? pendingPatrolStart.patrolId
      : undefined
  const effectiveActivePatrolId =
    robot?.activePatrolId ?? pendingPatrolId ?? inProgressPatrolId
  const hasLivePatrolStatus =
    liveStatus === 'PATROLLING' || liveStatus === 'OBSTACLE_STOP'
  const isPatrolling =
    hasLivePatrolStatus
    || robot?.status === '순찰중'
    || robot?.status === '중단'
    || pendingPatrolStart != null
  const canStop = hasLivePatrolStatus || effectiveActivePatrolId != null
  const canStart =
    robot != null
    && patrolRobotId != null
    && !canStop
    && robot.status === '대기'
    && !pendingPatrolStart
    && !startingPatrol

  useEffect(() => {
    if (liveStatus !== 'IDLE' && liveStatus !== 'OFFLINE' && liveStatus !== 'ERROR') return
    void refetch()
  }, [liveStatus, refetch])

  const pendingPatrolStatus = pendingPatrolStart
    ? liveRobotStatuses[pendingPatrolStart.robotId]
    : undefined

  useEffect(() => {
    if (!pendingPatrolStart) return

    if (pendingPatrolStatus === 'PATROLLING' || pendingPatrolStatus === 'OBSTACLE_STOP') {
      setToast(`${pendingPatrolStart.robotName} 순찰 시작을 확인했습니다.`)
      setPendingPatrolStart(undefined)
      void refetch()
      return
    }

    if (pendingPatrolStatus === 'OFFLINE' || pendingPatrolStatus === 'ERROR') {
      setToast(`${pendingPatrolStart.robotName} 시작을 확인하지 못했습니다. 로봇 상태를 확인해 주세요.`)
      setPendingPatrolStart(undefined)
      void refetch()
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
          void refetch()
        })
    }, remaining)

    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [pendingPatrolStart, pendingPatrolStatus, refetch])

  const startPatrol = async () => {
    if (!robot || startingPatrol || pendingPatrolStart) return
    if (patrolRobotId == null) {
      setPatrolError('로봇 번호를 확인할 수 없어 순찰을 시작하지 못했습니다.')
      return
    }

    setStartingPatrol(true)
    setPatrolError(undefined)
    try {
      const targetName = robot.name
      const response = await patrolsApi.start({ robotId: patrolRobotId })
      setPendingPatrolStart({
        patrolId: response.patrolId,
        robotId: String(response.robotId),
        robotName: targetName,
        requestedAt: Date.now(),
      })
      setToast(`${targetName} 순찰 시작 요청을 접수했습니다. 로봇 응답을 기다립니다.`)
      setStartModalOpen(false)
      void refetch()
    } catch (reason) {
      setPatrolError(reason instanceof Error ? reason.message : '순찰 시작에 실패했습니다.')
    } finally {
      setStartingPatrol(false)
    }
  }

  const stopPatrol = async () => {
    if (!robot || stoppingPatrol) return
    if (effectiveActivePatrolId == null) {
      setStopError('진행 중인 순찰 번호를 확인할 수 없습니다. 로봇 정보를 새로고침해 주세요.')
      return
    }

    setStoppingPatrol(true)
    setStopError(undefined)
    try {
      await patrolsApi.stop(effectiveActivePatrolId)
      setToast(`${robot.name} 순찰 종료를 요청했습니다.`)
      if (pendingPatrolStart?.patrolId === effectiveActivePatrolId) {
        setPendingPatrolStart(undefined)
      }
      setStopModalOpen(false)
      void refetch()
    } catch (reason) {
      setStopError(reason instanceof Error ? reason.message : '순찰 종료 요청에 실패했습니다.')
    } finally {
      setStoppingPatrol(false)
    }
  }

  const openStartModal = () => {
    if (!canStart) return
    setPatrolError(undefined)
    setStartModalOpen(true)
  }

  const openStopModal = () => {
    if (!robot || !canStop) return
    setStopError(
      effectiveActivePatrolId == null
        ? '진행 중인 순찰 번호를 확인할 수 없습니다. 백엔드 연결과 순찰 기록을 확인해 주세요.'
        : undefined,
    )
    setStopModalOpen(true)
  }

  return (
    <R0KiShell active="robots">
      <div className="pcol">
        <div className="pagehead">
          <div>
            <div className="crumb">
              <Link to="/app">대시보드</Link><i>›</i>
              <Link to="/app/robots">로봇 관리</Link><i>›</i>
              <b>{robot?.name ?? robotId}</b>
            </div>
            <div className="ptitle row">
              로봇 상세
              {robot && (
                <>
                  <span className="sub">{robot.name}</span>
                  <span className="st">
                    <i style={{ background: dot(robot.status) }} />
                    {robot.status}
                  </span>
                </>
              )}
            </div>
          </div>
          <div className="headtools">
            {robot && (
              <button type="button" className="btn btn-s" onClick={() => setDrawerOpen(true)}>수정</button>
            )}
            {canStop ? (
              <button
                type="button"
                className="btn btn-p btn-add"
                disabled={stoppingPatrol}
                onClick={openStopModal}
              >
                <svg viewBox="0 0 24 24"><rect x="6" y="6" width="12" height="12" rx="1" /></svg>
                {stoppingPatrol ? '종료 요청 중…' : '순찰 종료'}
              </button>
            ) : (
              <button
                type="button"
                className="btn btn-p btn-add"
                disabled={!canStart || startingPatrol || pendingPatrolStart != null}
                onClick={openStartModal}
              >
                <svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14" /></svg>
                {startingPatrol || pendingPatrolStart
                  ? '시작 중…'
                  : isPatrolling
                    ? '순찰 중'
                    : '순찰 시작'}
              </button>
            )}
          </div>
        </div>

        {error ? (
          <div className="glass g2 aisum">
            <div className="zh2"><span className="zn">로봇 정보를 불러오지 못했습니다</span></div>
            <button type="button" className="btn btn-s" onClick={refetch}>다시 시도</button>
          </div>
        ) : !robot ? (
          <div className="glass g2 aisum">
            <div className="zh2">
              <span className="zn">{isLoading ? '불러오는 중…' : `로봇(${robotId})을 찾을 수 없습니다`}</span>
            </div>
            {!isLoading && <Link to="/app/robots" className="btn btn-s">목록으로</Link>}
          </div>
        ) : (
          <div className="glass g2 rd-stage">
            {/* 상단 중앙: 진단 이브로우 */}
            <div className="rd-eyebrow">실시간 진단<span className="sep" /><span className="sub">부위별 자가 점검</span></div>

            {/* 좌상단: 히어로 식별 블록 (상태 리포트) */}
            <div className="rd-hero">
              <span className="rd-glabel">상태 리포트</span>
              <span className="k">현재 상태</span>
              <span className="st"><i style={{ background: dot(robot.status) }} />{robot.status}</span>
              <div className="rule" />
              <span className="k">배터리 잔량</span>
              <div className="rd-batt">
                {robot.battery != null ? (
                  <>
                    <span className="v">{robot.battery}</span>
                    <span className="u">%</span>
                  </>
                ) : (
                  <>
                    <span className="v unknown" aria-label="배터리 잔량 미수신">--</span>
                    <span className="u">%</span>
                  </>
                )}
              </div>
            </div>

            {/* 좌하: 누적 지표 */}
            <div className="rd-left">
              {/* 누적 주행거리는 백엔드 로봇 상세 응답에 없다 — 값이 생기면 그때 다시 뜬다.
                  항상 '—km'인 카드를 세워두면 자리만 차지하고 고장처럼 보인다. */}
              {robot.odometerKm != null && (
                <div className="rd-card">
                  <span className="ico">
                    <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8.4" /><path d="m15.2 8.8-2.7 5.7-5.7 2.7 2.7-5.7z" /></svg>
                  </span>
                  <span className="txt">
                    <span className="k">누적 주행</span>
                    <span className="v num">{robot.odometerKm}km</span>
                  </span>
                </div>
              )}
              <div className="rd-card">
                <span className="ico">
                  <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 12h3.8l2.7-6.6 4 13.2 2.7-6.6H21" /></svg>
                </span>
                <span className="txt">
                  <span className="k">이번 주 가동률</span>
                  <span className="v num">{robot.weeklyUptime ?? '—'}%</span>
                </span>
              </div>
            </div>

            {/* 중앙: 로봇 무대 */}
            <div className="rd-bot">
              <div className="rd-frame" ref={frameRef}>
                <div className="rd-plinth" aria-hidden="true" />
                <Suspense fallback={null}>
                  <RobotDiagnosticView className="rd-3d" onAnchors={handleAnchors} />
                </Suspense>

                {/* 지시선 — viewBox 없이 두면 SVG 사용자 단위가 CSS px과 1:1이라
                    handleAnchors 가 계산한 프레임 기준 px을 그대로 쓸 수 있다 */}
                <svg className="rd-leads" aria-hidden="true">
                  {robot.parts.slice(0, 4).map((part, i) => (
                    <g
                      key={part.name}
                      ref={(el) => {
                        leadRefs.current[i] = el
                      }}
                      className={part.status !== '정상' ? 'warn' : undefined}
                    >
                      <line x1="0" y1="0" x2="0" y2="0" />
                      <circle cx="0" cy="0" r="3.5" />
                    </g>
                  ))}
                </svg>

                {robot.parts.slice(0, 4).map((part, i) => (
                  <div
                    key={part.name}
                    className={`rd-cal ${PART_SLOTS[i]}${part.status !== '정상' ? ' warn' : ''}`}
                  >
                    <div
                      className="box"
                      ref={(el) => {
                        boxRefs.current[i] = el
                      }}
                    >
                      <span className="n">{part.name}</span>
                      <span className="st"><i style={{ background: dot(part.status) }} />{part.status}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* 우측 레일: 최근 순찰 기록 (세로) */}
            <div className="rd-right">
              <span className="rd-glabel">최근 순찰 기록</span>
              {recent.map((p) => {
                const status = PATROL_STATUS_LABEL[p.patrolStatus] ?? p.patrolStatus
                const eventText =
                  p.detectedEventCount > 0
                    ? `이벤트 ${p.detectedEventCount}건`
                    : '탐지 이벤트 없음'
                return (
                  <div
                    className="rd-log"
                    key={p.patrolId}
                    role="link"
                    tabIndex={0}
                    onClick={() => navigate(`/app/patrol/${p.patrolId}`)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        navigate(`/app/patrol/${p.patrolId}`)
                      }
                    }}
                  >
                    <span className="ico">
                      <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8.5" /><path d="M12 7.4V12l3.1 2" /></svg>
                    </span>
                    <span className="txt">
                      <span className="top">
                        <span className="t">
                          {patrolTime(p.startedAt)}–{p.endedAt ? patrolTime(p.endedAt) : '진행중'}
                        </span>
                        <span className="st"><i style={{ background: dot(status) }} />{status}</span>
                      </span>
                      <span className="m">{eventText}</span>
                    </span>
                  </div>
                )
              })}
              {recent.length === 0 && (
                <div className="rd-log">
                  <span className="txt"><span className="m">순찰 기록이 없습니다</span></span>
                </div>
              )}
              <Link to="/app/patrol" className="btn btn-p btn-add rd-all">
                전체 이력
                <svg viewBox="0 0 24 24"><path d="M5 12h13M12 5l7 7-7 7" /></svg>
              </Link>
            </div>

            {/* 하단 레일: 로봇 프로필 (가로) */}
            <div className="rd-foot">
              <span className="lbl">로봇 프로필</span>
              <div className="rd-card">
                <span className="ico">
                  <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4.5" y="8" width="15" height="11.5" rx="3.4" /><path d="M12 8V4.6" /><circle cx="12" cy="3.6" r="1.3" /><path d="M9.3 13.2h.01M14.7 13.2h.01" /></svg>
                </span>
                <span className="txt">
                  <span className="k">로봇명</span>
                  <span className="v num">{robot.name}</span>
                </span>
              </div>
              <div className="rd-card">
                <span className="ico">
                  <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5.2" width="18" height="13.6" rx="3.2" /><path d="M7 10.2h4.2M7 14h7.6" /></svg>
                </span>
                <span className="txt">
                  <span className="k">등록번호</span>
                  <span className="v num">{robot.registrationNo}</span>
                </span>
              </div>
              <div className="rd-card">
                <span className="ico">
                  <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3.2" y="5" width="17.6" height="16" rx="3.2" /><path d="M3.2 10.2h17.6M8.2 3v4M15.8 3v4" /></svg>
                </span>
                <span className="txt">
                  <span className="k">도입일</span>
                  <span className="v num">{robot.introducedAt}</span>
                </span>
              </div>
            </div>
          </div>
        )}
      </div>

      {robot && (
        <RobotEditDrawer
          open={drawerOpen}
          robot={robot}
          onClose={() => setDrawerOpen(false)}
          onSave={async ({ name }) => {
            try {
              await updateRobot.mutateAsync({
                robotId: robot.backendId ?? robot.id,
                robotName: name,
              })
              setPatch({ name })
              setToast('저장되었습니다')
            } catch (reason) {
              setToast(reason instanceof Error ? reason.message : '로봇 수정에 실패했습니다')
              throw reason
            }
          }}
          onDelete={async () => {
            try {
              await deleteRobot.mutateAsync({ robotId: robot.backendId ?? robot.id })
              navigate('/app/robots')
            } catch (reason) {
              setToast(reason instanceof Error ? reason.message : '로봇 삭제에 실패했습니다')
              throw reason
            }
          }}
        />
      )}

      {robot && startModalOpen && (
        <PatrolStartModal
          robot={robot}
          starting={startingPatrol}
          error={patrolError}
          onCancel={() => {
            if (startingPatrol) return
            setStartModalOpen(false)
            setPatrolError(undefined)
          }}
          onConfirm={() => void startPatrol()}
        />
      )}

      {robot && stopModalOpen && (
        <PatrolStopModal
          robot={robot}
          stopping={stoppingPatrol}
          error={stopError}
          onCancel={() => {
            if (stoppingPatrol) return
            setStopModalOpen(false)
            setStopError(undefined)
          }}
          onConfirm={() => void stopPatrol()}
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

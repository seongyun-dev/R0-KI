import { Link, useNavigate, useParams } from 'react-router-dom'
import { R0KiShell } from '../components/layout/R0KiShell'
import { useToast } from '../components/ui'
import { usePatrol } from '../features/patrol/usePatrols'
import type { Patrol, PatrolPoint } from '../types/domain'

/* R0-Ki 순찰 상세 — 시안 R0Kipatrol 그대로.
   이동 경로 지도(구역 웨이포인트 동적 배치) + 순찰 지점 기록(타임라인) + AI 요약.
   한 화면 고정 — 타임라인만 내부 스크롤. 데이터는 기존 usePatrol 그대로. */

/* 순찰 상태 배지 색 — 명도 램프 (시안: 완료=offline 톤) */
const PATROL_ST: Record<string, string> = {
  완료: 'var(--offline)',
  진행중: 'var(--patrol)',
  중단: 'var(--charge)',
  실패: 'var(--alert)',
}

/* 타임라인 점·배지 색 — 명도 램프 (시안 매핑) */
const POINT_ST: Record<string, string> = {
  이상무: 'var(--patrol)',
  처리완료: 'var(--charge)',
  탐지: 'var(--detect)',
  처리중: 'var(--detect)',
}
const pointColor = (s: string) => POINT_ST[s] ?? 'var(--patrol)'

/** "09:12" → 분 (정렬용) */
function timeMin(t: string) {
  const [h = 0, m = 0] = t.split(':').map(Number)
  return h * 60 + m
}

/* ── 이동 경로 지도 — routeZones 를 지그재그 웨이포인트로 동적 배치 ── */
function RouteMapSvg({ patrol }: { patrol: Patrol }) {
  const zones = patrol.routeZones.filter((z) => z !== '경로 정보 없음')
  if (zones.length < 2) {
    return (
      <svg viewBox="0 0 900 480" preserveAspectRatio="xMidYMid meet" aria-label="순찰 이동 경로">
        <text x="450" y="240">경로 정보 없음</text>
      </svg>
    )
  }

  // 중간 지점 시각 — 순찰 지점 기록에서 같은 구역명을 찾아 매칭
  const timeAt = (zone: string, index: number) => {
    if (index === 0) return patrol.start
    if (index === zones.length - 1) return patrol.end ?? ''
    const hit = (patrol.points ?? []).find(
      (p) => p.location.includes(zone) || zone.includes(p.location),
    )
    return hit?.time ?? ''
  }

  const n = zones.length
  const pts = zones.map((zone, i) => {
    const x = 110 + (i * 730) / (n - 1)
    const isEnd = i === 0 || i === n - 1
    const y = isEnd ? 340 : i % 2 === 1 ? 170 : 330
    return { zone, x, y, isEnd, time: timeAt(zone, i) }
  })
  const path = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x} ${p.y}`).join(' ')

  return (
    <svg viewBox="0 0 900 480" preserveAspectRatio="xMidYMid meet" aria-label="순찰 이동 경로">
      <g stroke="currentColor" opacity=".09" strokeWidth="1">
        <path d="M0 60H900M0 120H900M0 180H900M0 240H900M0 300H900M0 360H900M0 420H900" />
        <path d="M75 0V480M150 0V480M225 0V480M300 0V480M375 0V480M450 0V480M525 0V480M600 0V480M675 0V480M750 0V480M825 0V480" />
      </g>
      <path
        d={path}
        fill="none" stroke="var(--graphic)" strokeWidth="3.4" strokeLinecap="round"
        strokeLinejoin="round" strokeDasharray="11 9" opacity=".75"
      />
      {pts.map((p, i) => {
        const below = p.y >= 300
        const labelY = below ? p.y + 42 : p.y - 34
        const timeY = below ? p.y + 62 : p.y - 54
        return (
          <g key={`${p.zone}-${i}`}>
            {p.isEnd ? (
              <>
                <circle cx={p.x} cy={p.y} r="13" fill="var(--graphic)" />
                <circle cx={p.x} cy={p.y} r="13" fill="none" stroke="#fff" strokeOpacity=".9" strokeWidth="3" />
              </>
            ) : (
              <>
                <circle cx={p.x} cy={p.y} r="11" fill="none" stroke="var(--graphic)" strokeWidth="3.4" />
                <circle cx={p.x} cy={p.y} r="4" fill="var(--graphic)" />
              </>
            )}
            <text x={p.x} y={labelY}>{p.zone}</text>
            {p.time && <text className="rt" x={p.x} y={timeY}>{p.time}</text>}
          </g>
        )
      })}
    </svg>
  )
}

/* ── 타임라인 행 ── */
function TimelineRow({ point, onGo }: { point: PatrolPoint; onGo?: () => void }) {
  const color = pointColor(point.status)
  return (
    <div className="tl">
      <span className="d" style={{ background: color }} />
      <span className="t">{point.time}</span>
      <span className="c">
        <span className="n">
          {point.type}
          <em>{point.location}</em>
        </span>
        {point.note && <span className="m">{point.note}</span>}
      </span>
      <span className="a">
        <span className="st"><i style={{ background: color }} />{point.status}</span>
        {onGo && (
          <button type="button" className="arrow" aria-label="이벤트 상세로" onClick={onGo}>
            <svg viewBox="0 0 24 24"><path d="M5 12h13M12 5l7 7-7 7" /></svg>
          </button>
        )}
      </span>
    </div>
  )
}

export default function PatrolDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const { data: patrol, isLoading, error, refetch } = usePatrol(id)

  // 시안은 최신순 (복귀가 맨 위)
  const points = [...(patrol?.points ?? [])].sort((a, b) => timeMin(b.time) - timeMin(a.time))
  const anomalies = points.filter((p) => p.eventId).length

  return (
    <R0KiShell active="patrol">
      <div className="pcol">
        <div className="pagehead">
          <div>
            <div className="crumb">
              <Link to="/app">대시보드</Link><i>›</i>
              <Link to="/app/patrol">순찰 관리</Link><i>›</i>
              <b>{patrol?.id ?? id}</b>
            </div>
            <div className="ptitle">
              순찰 상세
              {patrol && (
                <>
                  <span className="sub">{patrol.id} · {patrol.robotName ?? patrol.robotId}</span>
                  <span className="st" style={{ marginLeft: 12, verticalAlign: 4 }}>
                    <i style={{ background: PATROL_ST[patrol.status] ?? 'var(--patrol)' }} />
                    {patrol.status}
                  </span>
                </>
              )}
            </div>
          </div>
          <div className="headtools">
            <button type="button" className="btn btn-s" onClick={() => toast('✓ 재순찰이 요청되었습니다')}>
              재순찰 요청
            </button>
            <button type="button" className="btn btn-p" onClick={() => window.print()}>
              PDF 다운로드
            </button>
          </div>
        </div>

        {error ? (
          <div className="glass g2 aisum">
            <div className="zh2"><span className="zn">순찰 이력을 불러오지 못했습니다</span></div>
            <button type="button" className="btn btn-s" onClick={refetch}>다시 시도</button>
          </div>
        ) : !patrol ? (
          <div className="glass g2 aisum">
            <div className="zh2">
              <span className="zn">{isLoading ? '불러오는 중…' : `순찰 이력(${id})을 찾을 수 없습니다`}</span>
            </div>
            {!isLoading && (
              <Link to="/app/patrol" className="btn btn-s">목록으로</Link>
            )}
          </div>
        ) : (
          <>
            <div className="dgrid">
              {/* 이동 경로 지도 */}
              <div className="glass g2 dcol" style={{ padding: 'var(--s5)' }}>
                <div className="zh2">
                  <span className="zn">이동 경로 지도</span>
                  <span className="zsub">{patrol.routeSummary ?? patrol.routeZones.join(' → ')}</span>
                </div>
                <div className="rmap">
                  <RouteMapSvg patrol={patrol} />
                </div>
              </div>

              {/* 순찰 지점 기록 */}
              <div className="glass g2 dcol" style={{ padding: 'var(--s5)' }}>
                <div className="zh2">
                  <span className="zn">순찰 지점 기록</span>
                  <span className="zsub">
                    최신순 · 전체 경유지 {points.length}곳{anomalies > 0 ? ` · 이상 ${anomalies}건` : ''}
                  </span>
                </div>
                <div className="tline">
                  {points.length === 0 ? (
                    <div className="tfoot" style={{ paddingTop: 'var(--s5)' }}>
                      <span>기록된 타임라인이 없습니다</span>
                    </div>
                  ) : (
                    points.map((point, i) => (
                      <TimelineRow
                        key={`${point.time}-${i}`}
                        point={point}
                        onGo={point.eventId ? () => navigate(`/app/events/${point.eventId}`) : undefined}
                      />
                    ))
                  )}
                </div>
              </div>
            </div>

            {/* AI 요약 */}
            <div className="glass g2 aisum">
              <div className="zh2"><span className="zn">AI 요약</span></div>
              <p className="q">
                {patrol.report?.aiSummary ?? '보고서가 아직 생성되지 않았습니다. 순찰이 완료되면 AI 보고서가 자동 생성됩니다.'}
              </p>
            </div>
          </>
        )}
      </div>
    </R0KiShell>
  )
}

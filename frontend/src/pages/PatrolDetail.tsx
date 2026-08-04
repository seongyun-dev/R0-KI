import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import type { MapDetailResponse, ZoneCreateResponse } from '../api/contracts'
import { mapApi, patrolsApi } from '../api/services'
import { env } from '../config/env'
import { R0KiShell } from '../components/layout/R0KiShell'
import { useToast } from '../components/ui'
import { usePatrol } from '../features/patrol/usePatrols'
import { useAuthStore } from '../features/auth/useAuthStore'
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
function RouteMapSvg({
  patrol,
  mapImageUrl,
  mapDetail,
  checkpointZones,
}: {
  patrol: Patrol
  mapImageUrl?: string
  mapDetail?: MapDetailResponse
  checkpointZones: ZoneCreateResponse[]
}) {
  const zones = patrol.routeZones.filter((z) => z !== '경로 정보 없음')
  if (
    zones.length < 2 &&
    (patrol.routePoints?.length ?? 0) < 2 &&
    checkpointZones.length === 0 &&
    !(patrol.points ?? []).some(
      (point) => point.eventId != null && point.x != null && point.y != null,
    )
  ) {
    return (
      <svg viewBox="0 0 900 480" preserveAspectRatio="xMidYMid meet" aria-label="순찰 이동 경로">
        {mapImageUrl && (
          <image
            href={mapImageUrl}
            x="0"
            y="0"
            width="900"
            height="480"
            preserveAspectRatio="xMidYMid meet"
          />
        )}
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

  const n = Math.max(zones.length, 2)
  const pts = zones.map((zone, i) => {
    const x = 110 + (i * 730) / (n - 1)
    const isEnd = i === 0 || i === n - 1
    const y = isEnd ? 340 : i % 2 === 1 ? 170 : 330
    return { zone, x, y, isEnd, time: timeAt(zone, i) }
  })
  const path = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x} ${p.y}`).join(' ')
  const routePoints = patrol.routePoints ?? []
  const xValues = routePoints.map((point) => point.x)
  const yValues = routePoints.map((point) => point.y)
  const minX = Math.min(...xValues)
  const maxX = Math.max(...xValues)
  const minY = Math.min(...yValues)
  const maxY = Math.max(...yValues)
  const routePadding = 36
  const resolution = Number(mapDetail?.resolution)
  const originX = Number(mapDetail?.originX)
  const originY = Number(mapDetail?.originY)
  const mapWidth = Number(mapDetail?.width)
  const mapHeight = Number(mapDetail?.height)
  const hasMapCoordinates =
    Number.isFinite(resolution) && resolution > 0 &&
    Number.isFinite(originX) && Number.isFinite(originY) &&
    Number.isFinite(mapWidth) && mapWidth > 0 &&
    Number.isFinite(mapHeight) && mapHeight > 0
  const imageScale = hasMapCoordinates ? Math.min(900 / mapWidth, 480 / mapHeight) : 1
  const imageOffsetX = hasMapCoordinates ? (900 - mapWidth * imageScale) / 2 : 0
  const imageOffsetY = hasMapCoordinates ? (480 - mapHeight * imageScale) / 2 : 0
  const toScreenPoint = (x: number, y: number) => ({
    x: imageOffsetX + ((x - originX) / resolution) * imageScale,
    y: imageOffsetY + (mapHeight - (y - originY) / resolution) * imageScale,
  })
  const actualPoints = routePoints.map((point) => hasMapCoordinates
    ? toScreenPoint(point.x, point.y)
    : {
        x: minX === maxX
          ? 450
          : routePadding + ((point.x - minX) / (maxX - minX)) * (900 - routePadding * 2),
        y: minY === maxY
          ? 240
          : routePadding + ((maxY - point.y) / (maxY - minY)) * (480 - routePadding * 2),
      })
  const actualPath = actualPoints
    .map((point, index) => `${index === 0 ? 'M' : 'L'}${point.x} ${point.y}`)
    .join(' ')

  return (
    <svg viewBox="0 0 900 480" preserveAspectRatio="xMidYMid meet" aria-label="순찰 이동 경로">
      {mapImageUrl && (
        <image
          href={mapImageUrl}
          x="0"
          y="0"
          width="900"
          height="480"
          preserveAspectRatio="xMidYMid meet"
        />
      )}
      <g stroke="currentColor" opacity=".09" strokeWidth="1">
        <path d="M0 60H900M0 120H900M0 180H900M0 240H900M0 300H900M0 360H900M0 420H900" />
        <path d="M75 0V480M150 0V480M225 0V480M300 0V480M375 0V480M450 0V480M525 0V480M600 0V480M675 0V480M750 0V480M825 0V480" />
      </g>
      {hasMapCoordinates && checkpointZones.map((zone) => {
        const topLeft = toScreenPoint(Number(zone.minX), Number(zone.maxY))
        const bottomRight = toScreenPoint(Number(zone.maxX), Number(zone.minY))
        const width = Math.max(4, bottomRight.x - topLeft.x)
        const height = Math.max(4, bottomRight.y - topLeft.y)
        const centerX = topLeft.x + width / 2
        const centerY = topLeft.y + height / 2
        return (
          <g key={String(zone.zoneId)}>
            <rect
              x={topLeft.x}
              y={topLeft.y}
              width={width}
              height={height}
              rx="5"
              fill="var(--graphic)"
              fillOpacity=".12"
              stroke="var(--graphic)"
              strokeWidth="2"
              strokeDasharray="6 4"
            />
            <circle cx={centerX} cy={centerY} r="6" fill="var(--graphic)" />
            <text x={centerX} y={topLeft.y - 8}>{zone.name}</text>
          </g>
        )
      })}
      <path
        d={path}
        fill="none" stroke="var(--graphic)" strokeWidth="3.4" strokeLinecap="round"
        strokeLinejoin="round" strokeDasharray="11 9" opacity=".75"
      />
      {actualPoints.length >= 2 && (
        <>
          <path
            d={actualPath}
            fill="none"
            stroke="var(--graphic)"
            strokeWidth="5"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeDasharray="10 8"
          />
          <circle cx={actualPoints[0].x} cy={actualPoints[0].y} r="8" fill="var(--patrol)" />
          <circle
            cx={actualPoints[actualPoints.length - 1].x}
            cy={actualPoints[actualPoints.length - 1].y}
            r="8"
            fill="var(--detect)"
          />
        </>
      )}
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
      {hasMapCoordinates && (patrol.points ?? [])
        .filter(
          (point) =>
            point.eventId != null &&
            point.x != null && Number.isFinite(point.x) &&
            point.y != null && Number.isFinite(point.y),
        )
        .map((point) => {
          const position = toScreenPoint(point.x!, point.y!)
          return (
            <g key={`event-${point.eventId}`}>
              <circle
                cx={position.x}
                cy={position.y}
                r="13"
                fill="none"
                stroke="var(--detect)"
                strokeWidth="4"
              />
              <text
                x={position.x}
                y={position.y - 22}
                style={{ fill: 'var(--detect)', fontWeight: 800 }}
              >
                {point.type}
              </text>
              <title>{`${point.time} · ${point.type} · ${point.location}`}</title>
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
  const mapId = useAuthStore((state) => state.mapId) ?? env.defaultMapId
  const [mapImageUrl, setMapImageUrl] = useState<string>()
  const [mapDetail, setMapDetail] = useState<MapDetailResponse>()
  const [checkpointZones, setCheckpointZones] = useState<ZoneCreateResponse[]>([])
  const [isDownloadingPdf, setIsDownloadingPdf] = useState(false)

  const handlePdfDownload = async () => {
    if (!id || isDownloadingPdf) return

    setIsDownloadingPdf(true)
    try {
      const pdf = await patrolsApi.downloadPdf(id)
      const objectUrl = URL.createObjectURL(pdf)
      const link = document.createElement('a')
      link.href = objectUrl
      link.download = `patrol-report-${id}.pdf`
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(objectUrl)
      toast('PDF 보고서를 다운로드했습니다.')
    } catch (reason) {
      console.error('PDF 보고서 다운로드에 실패했습니다.', reason)
      toast('PDF 보고서 다운로드에 실패했습니다.')
    } finally {
      setIsDownloadingPdf(false)
    }
  }

  useEffect(() => {
    if (!mapId && !patrol?.mapUrl) {
      setMapImageUrl(undefined)
      setMapDetail(undefined)
      setCheckpointZones([])
      return
    }

    const controller = new AbortController()
    let objectUrl: string | undefined

    const detailPromise = mapId
      ? Promise.all([mapApi.detail(mapId), mapApi.zones(mapId)])
          .then(([detail, zones]) => {
            setCheckpointZones(zones)
            return detail
          })
      : Promise.resolve(undefined)

    detailPromise
      .then(async (detail) => {
        setMapDetail(detail)
        const mapUrl = detail?.mapUrl ?? patrol?.mapUrl
        if (!mapUrl) return undefined
        return mapApi.file(mapUrl, controller.signal)
      })
      .then((blob) => {
        if (!blob) return
        objectUrl = URL.createObjectURL(blob)
        setMapImageUrl(objectUrl)
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          console.error('순찰 지도를 불러오지 못했습니다.', reason)
        }
      })

    return () => {
      controller.abort()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [mapId, patrol?.mapUrl])

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
            <button
              type="button"
              className="btn btn-p"
              disabled={!patrol || isDownloadingPdf}
              onClick={handlePdfDownload}
            >
              {isDownloadingPdf ? 'PDF 생성 중...' : 'PDF 다운로드'}
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
                  <RouteMapSvg
                    patrol={patrol}
                    mapImageUrl={mapImageUrl}
                    mapDetail={mapDetail}
                    checkpointZones={checkpointZones}
                  />
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

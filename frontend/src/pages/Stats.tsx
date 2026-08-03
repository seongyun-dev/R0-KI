import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { R0KiShell } from '../components/layout/R0KiShell'
import { R0KiDropdown } from '../components/ui/R0KiDropdown'
import { InsightReportPanel } from '../features/stats/InsightReportPanel'
import { RAMP } from '../features/stats/chartTheme'
import { EventTrendChart } from '../features/stats/EventTrendChart'
import { HandlingChart, HANDLING_OPACITIES } from '../features/stats/HandlingChart'
import { HourlyTypeChart, HOURLY_SERIES } from '../features/stats/HourlyTypeChart'
import { ZonePieChart } from '../features/stats/ZonePieChart'
import { useStats } from '../features/stats/useStats'
import { downloadCsv } from '../lib/downloadCsv'

/* R0-Ki 통계 — 시안 R0Ki-stats 그대로.
   3단 관제 구성: 좌 KPI 스택 / 중앙 주력 차트 2단 / 우 보조 패널 / 하단 AI 인사이트.
   한 화면 고정. 데이터·CSV 내보내기는 기존 훅/로직 그대로. */

// 기본값(이번 달/전체)은 allLabel 로 두어 미선택 상태로 보이게 한다
// period → resolveAnalyticsRange → analytics from/to (디자인은 그대로, 기간만 API에 반영)
const PERIOD_OPTIONS = [
  { value: 'week', label: '이번 주' },
  { value: 'quarter', label: '이번 분기' },
]
// 구역 드롭다운은 화면 값을 zoneId(checkpoint_id) 목록으로 변환해 API 필터에 반영한다.
// (현재는 zoneName 키워드 기반 매핑: parking=주차, recycle=분리수거, danger=위험)
const ZONE_OPTIONS = [
  { value: 'parking', label: '구역: 주차장' },
  { value: 'recycle', label: '구역: 분리수거장' },
  { value: 'danger', label: '구역: 위험구역' },
]

export default function Stats() {
  const [period, setPeriod] = useState('')
  const [zone, setZone] = useState('')
  const { data, isLoading, error, refetch } = useStats({
    period: period || 'month',
    zone: zone || 'all',
  })
  // 토스트
  const [toast, setToast] = useState<string>()

  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(undefined), 2600)
    return () => clearTimeout(t)
  }, [toast])

  const onExport = () => {
    if (!data) return
    const rows: (string | number)[][] = [
      ['구분', '항목', '값'],
      ['KPI', '총 순찰 횟수', data.summary.totalPatrols],
      ['KPI', '총 이벤트', data.summary.totalEvents],
      ['KPI', '평균 처리시간(분)', data.summary.avgHandleMin],
      // 가동률은 백엔드 analytics 응답에 없어 항상 0이 나간다 — 받는 사람이
      // "가동률 0%"로 읽으므로 열을 빼둔다. 값이 생기면 다시 넣는다.
      [],
      ['일자별 이벤트 추이', '일자', '건수'],
      ...data.daily.map((d) => ['', d.date, d.count]),
      [],
      ['시간대별 이벤트(유형별)', '시간대', '주차', '쓰레기'],
      ...data.hourly.map((h) => ['', h.slot, h.주차, h.쓰레기]),
      [],
      ['처리 현황', '항목', '처리(건)', '미처리(건)', '처리율(%)'],
      ...data.handling.map((h) => ['', h.label, h.handled, h.pending, h.handledPct]),
      [],
      ['구역별 이벤트 비율', '구역', '건수', '비율(%)'],
      ...data.zones.map((z) => ['', z.zone, z.count, z.pct]),
    ]
    downloadCsv('patrol-stats.csv', rows)
    setToast('CSV를 내보냈습니다')
  }

  // 일자별 추이 메타 — 07/15 6건 · 전일 −4건 ▼
  const last = data?.daily[data.daily.length - 1]
  const prev = data?.daily[data.daily.length - 2]
  const diff = last && prev ? last.count - prev.count : 0

  // 시간대별 피크 — 15-18시 20건
  const hourly = (data?.hourly ?? []).map((h) => ({ ...h, total: h.주차 + h.쓰레기 }))
  const peak = hourly.length ? hourly.reduce((a, b) => (b.total > a.total ? b : a)) : undefined

  const zoneTotal = (data?.zones ?? []).reduce((s, z) => s + z.count, 0)

  // KPI — 증감 화살표는 색이 아니라 방향으로 (모노크롬 규칙)
  const kpis = data
    ? [
        { k: '총 순찰 횟수', v: data.summary.totalPatrols, u: '회', d: data.summary.deltas?.patrols, ar: '▲' },
        { k: '총 이벤트', v: data.summary.totalEvents, u: '건', d: data.summary.deltas?.events, ar: '▲' },
        { k: '평균 처리시간', v: data.summary.avgHandleMin, u: '분', d: data.summary.deltas?.handle, ar: '▼' },
      ]
    : []

  return (
    <R0KiShell active="stats">
      <div className="pcol">
        <div className="pagehead">
          <div>
            <div className="crumb">
              <Link to="/app">대시보드</Link><i>›</i><b>통계</b>
            </div>
            <div className="ptitle">기간별 통계 &amp; 인사이트</div>
          </div>
          <div className="headtools tight">
            <R0KiDropdown allLabel="이번 달" options={PERIOD_OPTIONS} value={period} onChange={setPeriod} />
            <R0KiDropdown allLabel="구역: 전체" options={ZONE_OPTIONS} value={zone} onChange={setZone} />
            <button type="button" className="btn btn-s btn-add" onClick={onExport} disabled={!data}>
              <svg viewBox="0 0 24 24"><path d="M12 3v12M7.5 10.5 12 15l4.5-4.5M4 19h16" /></svg>
              CSV 내보내기
            </button>
          </div>
        </div>

        {error ? (
          <div className="glass g2 aisum">
            <div className="zh2"><span className="zn">통계를 불러오지 못했습니다</span></div>
            <button type="button" className="btn btn-s" onClick={refetch}>다시 시도</button>
          </div>
        ) : !data ? (
          <div className="glass g2 aisum">
            <div className="zh2">
              <span className="zn">{isLoading ? '불러오는 중…' : '통계 데이터가 없습니다'}</span>
            </div>
          </div>
        ) : (
          <div className="st-grid">
            {/* ── 좌: KPI 스택 ── */}
            <div className="st-col c1">
              {kpis.map((k) => (
                <div className="st-kpi" key={k.k}>
                  <div className="st-kb">
                    <span className="k">{k.k}</span>
                    <span className="v">{k.v}<span className="u">{k.u}</span></span>
                    {k.d && <span className="d"><span className="ar" aria-hidden>{k.ar}</span>{k.d}</span>}
                  </div>
                </div>
              ))}
            </div>

            {/* ── 중앙: 주력 차트 2단 ── */}
            <div className="st-col c2">
              <div className="glass g2 st-panel" style={{ flex: 1.22 }}>
                <div className="st-head">
                  <span className="bul" /><span className="ttl">일자별 이벤트 추이</span>
                  {last && (
                    <span className="meta">
                      <b>{last.date}</b> {last.count}건 · 전일 {diff > 0 ? `+${diff}` : diff}건{' '}
                      {diff > 0 ? '▲' : diff < 0 ? '▼' : ''}
                    </span>
                  )}
                </div>
                <div className="st-rule" />
                <EventTrendChart data={data.daily} />
              </div>

              <div className="glass g2 st-panel">
                <div className="st-head">
                  <span className="bul" /><span className="ttl">시간대별 이벤트 발생</span>
                  <span className="sub">유형별</span>
                  {peak && <span className="meta"><b>{peak.slot}</b> {peak.total}건</span>}
                </div>
                <div className="st-leg">
                  {HOURLY_SERIES.map((s) => (
                    <span key={s.key}>
                      <i style={{ background: 'var(--graphic)', opacity: s.opacity }} />{s.key}
                    </span>
                  ))}
                </div>
                <HourlyTypeChart data={data.hourly} />
              </div>
            </div>

            {/* ── 우: 보조 패널 ── */}
            <div className="st-col c3">
              <div className="glass g2 st-panel">
                <div className="st-head">
                  <span className="bul" /><span className="ttl">구역별 이벤트 비율</span>
                  <span className="meta"><b>{zoneTotal}</b>건 전체</span>
                </div>
                <div className="st-rule" />
                <div className="st-donut">
                  <ZonePieChart data={data.zones} />
                  <div className="st-rank">
                    {data.zones.map((z, i) => (
                      <div className="st-rk" key={z.zone}>
                        <i style={{ opacity: RAMP[i % RAMP.length] }} />
                        <span className="n">{z.zone}</span>
                        <span className="c">{z.count}건</span>
                        <span className="p">{z.pct}%</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              <div className="glass g2 st-panel" style={{ flex: 1.1 }}>
                <div className="st-head">
                  <span className="bul" /><span className="ttl">처리 현황</span>
                  <span className="sub">100% 기준</span>
                </div>
                <div className="st-leg">
                  <span><i style={{ background: 'var(--graphic)', opacity: HANDLING_OPACITIES.처리 }} />처리</span>
                  <span><i style={{ background: 'var(--graphic)' }} />미처리</span>
                </div>
                <HandlingChart data={data.handling} />
              </div>
            </div>

            {/* ── 하단: 백엔드 AI 인사이트 리포트 (지난 완료 주/월) ── */}
            <InsightReportPanel />
          </div>
        )}

        {(error || !data) && <InsightReportPanel />}
      </div>

      {/* 토스트 */}
      <div className={`toast${toast ? ' on' : ''}`} role="status" aria-live="polite">
        <svg viewBox="0 0 24 24"><path d="M4 12.5 9.5 18 20 6.5" /></svg>
        <span>{toast}</span>
      </div>
    </R0KiShell>
  )
}

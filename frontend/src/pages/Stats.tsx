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
import { useStats, useStatsPeriodLabel } from '../features/stats/useStats'
import type { StatsUnit } from '../features/stats/resolveAnalyticsRange'
import { downloadCsv } from '../lib/downloadCsv'

/* R0-Ki 통계 — 시안 R0Ki-stats 그대로.
   기간: 주/월 단위 + 화살표로 과거 구간 이동 (차트만, AI 리포트는 독립). */

const UNIT_OPTIONS = [
  { value: 'week', label: '주 단위' },
  { value: 'quarter', label: '분기 단위' },
  { value: 'year', label: '연 단위' },
]

const ZONE_OPTIONS = [
  { value: 'parking', label: '구역: 주차장' },
  { value: 'recycle', label: '구역: 분리수거장' },
]

export default function Stats() {
  // '' = 달 단위(기본)
  const [unitKey, setUnitKey] = useState('')
  const unit: StatsUnit =
    unitKey === 'week' || unitKey === 'quarter' || unitKey === 'year'
      ? unitKey
      : 'month'
  // 0 = 이번 주/달, -1 = 직전, … (미래로 가지 않음)
  const [offset, setOffset] = useState(0)
  const [zone, setZone] = useState('')
  const periodLabel = useStatsPeriodLabel(unit, offset)
  const { data, isLoading, error, refetch } = useStats({
    unit,
    offset,
    zone: zone || 'all',
  })
  const [toast, setToast] = useState<string>()

  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(undefined), 2600)
    return () => clearTimeout(t)
  }, [toast])

  // 단위가 바뀌면 이번 구간(offset 0)으로 리셋
  const onUnitChange = (value: string) => {
    setUnitKey(value)
    setOffset(0)
  }

  const onExport = () => {
    if (!data) return
    const rows: (string | number)[][] = [
      ['구분', '항목', '값'],
      ['기간', periodLabel, ''],
      ['KPI', '총 순찰 횟수', data.summary.totalPatrols],
      ['KPI', '총 이벤트', data.summary.totalEvents],
      ['KPI', '평균 처리시간(분)', data.summary.avgHandleMin],
      [],
      ['이벤트 추이', '기간', '건수'],
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

  const last = data?.daily[data.daily.length - 1]
  const prev = data?.daily[data.daily.length - 2]
  const diff = last && prev ? last.count - prev.count : 0
  const useMonthTrend = unit === 'quarter' || unit === 'year'
  const trendTitle = useMonthTrend ? '월별 이벤트 추이' : '이벤트 추이'
  const trendPrevLabel = useMonthTrend ? '전월' : '전일'

  const hourly = (data?.hourly ?? []).map((h) => ({ ...h, total: h.주차 + h.쓰레기 }))
  const peak = hourly.length ? hourly.reduce((a, b) => (b.total > a.total ? b : a)) : undefined
  const zoneTotal = (data?.zones ?? []).reduce((s, z) => s + z.count, 0)

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
            <R0KiDropdown
              allLabel="달 단위"
              options={UNIT_OPTIONS}
              value={unitKey}
              onChange={onUnitChange}
            />
            <button
              type="button"
              className="btn btn-s btn-add"
              aria-label="이전 기간"
              onClick={() => setOffset((v) => v - 1)}
            >
              <svg viewBox="0 0 24 24"><path d="M15 5.5 8.5 12 15 18.5" /></svg>
            </button>
            <span className="st-head" style={{ marginBottom: 0, minWidth: '9.5rem', justifyContent: 'center' }}>
              <span className="ttl" style={{ fontSize: 13.5 }}>{periodLabel}</span>
            </span>
            <button
              type="button"
              className="btn btn-s btn-add"
              aria-label="다음 기간"
              disabled={offset >= 0}
              onClick={() => setOffset((v) => Math.min(0, v + 1))}
            >
              <svg viewBox="0 0 24 24"><path d="M9 5.5 15.5 12 9 18.5" /></svg>
            </button>
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

            <div className="st-col c2">
              <div className="glass g2 st-panel" style={{ flex: 1.22 }}>
                <div className="st-head">
                  <span className="bul" /><span className="ttl">{trendTitle}</span>
                  {last && (
                    <span className="meta">
                      <b>{last.date}</b> {last.count}건 · {trendPrevLabel} {diff > 0 ? `+${diff}` : diff}건{' '}
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

            <InsightReportPanel />
          </div>
        )}

        {(error || !data) && <InsightReportPanel />}
      </div>

      <div className={`toast${toast ? ' on' : ''}`} role="status" aria-live="polite">
        <svg viewBox="0 0 24 24"><path d="M4 12.5 9.5 18 20 6.5" /></svg>
        <span>{toast}</span>
      </div>
    </R0KiShell>
  )
}

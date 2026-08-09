import type { CSSProperties } from 'react'
import { RAMP } from './chartTheme'
import { EventTrendChart } from './EventTrendChart'
import { HandlingChart } from './HandlingChart'
import { HourlyTypeChart } from './HourlyTypeChart'
import { ZonePieChart } from './ZonePieChart'
import type { ParsedInsightSection } from './parseInsightMarkdown'
import type {
  DailyEventStat,
  HandlingStat,
  HourlyEventStat,
  StatSummary,
  ZoneShareStat,
} from '../../types/domain'

export type StatsPdfInsight = {
  periodLabel: string
  periodKey?: string
  periodRange?: string
  sections: ParsedInsightSection[]
  emptyMessage?: string
}

const FONT =
  '"Pretendard", "Noto Sans KR", "Apple SD Gothic Neo", "Malgun Gothic", sans-serif'

export type StatsPdfDocumentProps = {
  periodLabel: string
  periodKey?: string
  trendTitle: string
  trendPrevLabel: string
  summary: StatSummary
  daily: DailyEventStat[]
  hourly: HourlyEventStat[]
  zones: ZoneShareStat[]
  handling: HandlingStat[]
  insight?: StatsPdfInsight
}

/** 차트 섹션 요약 문구 */
function buildPdfCaptions(input: {
  daily: DailyEventStat[]
  hourly: HourlyEventStat[]
  zones: ZoneShareStat[]
  handling: HandlingStat[]
  summary: StatSummary
  trendPrevLabel: string
}) {
  const { daily, hourly, zones, handling, summary, trendPrevLabel } = input
  const totalEvents = summary.totalEvents
  const peakDay = daily.reduce<(DailyEventStat | undefined)>(
    (best, row) => (!best || row.count > best.count ? row : best),
    undefined,
  )
  const delta = summary.deltas?.events
  const trendParts = [
    `총 ${totalEvents}건`,
    delta ? `${trendPrevLabel} 대비 ${delta.replace(/^이전 대비\s*/, '')}` : undefined,
    peakDay && peakDay.count > 0 ? `최다 발생일 ${peakDay.date}` : undefined,
  ].filter(Boolean)

  const hourlyRows = hourly.map((h) => ({ ...h, total: h.주차 + h.쓰레기 }))
  const hourlyTotal = hourlyRows.reduce((s, h) => s + h.total, 0)
  const peakHour = hourlyRows.reduce<(typeof hourlyRows)[number] | undefined>(
    (best, row) => (!best || row.total > best.total ? row : best),
    undefined,
  )
  const peakHourPct =
    peakHour && hourlyTotal > 0 ? Math.round((peakHour.total * 100) / hourlyTotal) : 0
  const hourlyCaption = peakHour
    ? `${peakHour.slot} 최다 · 전체의 ${peakHourPct}%`
    : '시간대별 데이터 없음'

  const topZone = [...zones].sort((a, b) => b.count - a.count)[0]
  const zoneCaption = topZone
    ? `${topZone.zone} 최다 · ${topZone.count}건, ${topZone.pct}%`
    : '구역별 데이터 없음'

  const overall = handling.find((h) => h.label === '전체') ?? handling[0]
  const handlingCaption = overall
    ? `처리 ${overall.handled}건 · 미처리 ${overall.pending}건 · 처리율 ${overall.handledPct}%`
    : '처리 현황 데이터 없음'

  return {
    trend: trendParts.join(' · '),
    hourly: hourlyCaption,
    zone: zoneCaption,
    handling: handlingCaption,
  }
}

const sectionStyle: CSSProperties = {
  background: '#ffffff',
  border: '1px solid #d7dee8',
  borderRadius: 12,
  padding: '18px 20px 16px',
  margin: 0,
  boxSizing: 'border-box',
  breakInside: 'avoid',
  pageBreakInside: 'avoid',
}

const titleStyle: CSSProperties = {
  margin: '0 0 12px',
  fontSize: 15,
  fontWeight: 700,
  letterSpacing: '-0.01em',
  color: '#142033',
  fontFamily: FONT,
}

const captionStyle: CSSProperties = {
  margin: '12px 0 0',
  fontSize: 13,
  fontWeight: 600,
  lineHeight: 1.5,
  color: '#3b4a5f',
  fontFamily: FONT,
}

const chartBoxStyle: CSSProperties = {
  width: '100%',
  height: 300,
  position: 'relative',
}

/**
 * PDF 전용 문서 — 화면 레이아웃과 분리.
 * 각 .pdf-section 은 통째로 다음 페이지로 넘어갈 수 있는 단위.
 * 긴 sr-only 표는 넣지 않는다 (차트 includeA11yTable=false).
 */
export function StatsPdfDocument({
  periodLabel,
  periodKey,
  trendTitle,
  trendPrevLabel,
  summary,
  daily,
  hourly,
  zones,
  handling,
  insight,
}: StatsPdfDocumentProps) {
  const captions = buildPdfCaptions({
    daily,
    hourly,
    zones,
    handling,
    summary,
    trendPrevLabel,
  })
  const zoneTotal = zones.reduce((s, z) => s + z.count, 0)

  return (
    <div
      className="stats-pdf-root"
      style={{
        width: 794,
        padding: 0,
        margin: 0,
        background: '#ffffff',
        color: '#142033',
        fontFamily: FONT,
        boxSizing: 'border-box',
      }}
    >
      <style>{`
        .stats-pdf-root .st-chart {
          height: 100% !important;
          width: 100% !important;
          flex: none !important;
          min-height: 0 !important;
          overflow: visible !important;
        }
        .stats-pdf-root .st-dc .v { color: var(--text-1); }
        .stats-pdf-root .st-dc .k { color: var(--text-3); }
      `}</style>
      <section className="pdf-section" style={sectionStyle}>
        <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.08em', color: '#0876CA' }}>
          PATROL STATS REPORT
        </div>
        <h1 style={{ margin: '6px 0 10px', fontSize: 22, fontWeight: 700, letterSpacing: '-0.02em' }}>
          기간별 통계 & 인사이트
        </h1>
        <div style={{ fontSize: 13, lineHeight: 1.55, color: '#4a5b70' }}>
          <div>
            <b>기간</b> · {periodLabel}
          </div>
          {periodKey ? (
            <div>
              <b>키</b> · {periodKey}
            </div>
          ) : null}
          <div>
            <b>생성</b> · {new Date().toLocaleString('ko-KR')}
          </div>
        </div>
      </section>

      <section className="pdf-section" style={{ ...sectionStyle, marginTop: 12 }}>
        <h2 style={titleStyle}>{trendTitle}</h2>
        <div className="pdf-chart" style={chartBoxStyle}>
          <EventTrendChart
            data={daily}
            gradientId="pdfTrendFill"
            includeA11yTable={false}
          />
        </div>
        <p style={captionStyle}>{captions.trend}</p>
      </section>

      <section className="pdf-section" style={{ ...sectionStyle, marginTop: 12 }}>
        <h2 style={titleStyle}>시간대별 발생</h2>
        <div className="pdf-chart" style={chartBoxStyle}>
          <HourlyTypeChart data={hourly} includeA11yTable={false} />
        </div>
        <p style={captionStyle}>{captions.hourly}</p>
      </section>

      <section className="pdf-section" style={{ ...sectionStyle, marginTop: 12 }}>
        <h2 style={titleStyle}>구역별 발생</h2>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 16,
            minHeight: 220,
          }}
        >
          <div className="pdf-chart" style={{ width: 200, height: 200, flex: 'none', position: 'relative' }}>
            <ZonePieChart data={zones} includeA11yTable={false} />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            {zones.map((z, i) => (
              <div
                key={z.zone}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  padding: '7px 0',
                  borderBottom: '1px solid #e6ebf2',
                  fontSize: 13.5,
                }}
              >
                <i
                  style={{
                    width: 10,
                    height: 10,
                    borderRadius: 3,
                    background: 'var(--graphic)',
                    opacity: RAMP[i % RAMP.length],
                    flex: 'none',
                  }}
                />
                <span style={{ flex: 1, fontWeight: 600, color: '#3b4a5f' }}>{z.zone}</span>
                <span style={{ fontFamily: 'var(--mono)', fontWeight: 700 }}>{z.count}건</span>
                <span style={{ fontFamily: 'var(--mono)', color: '#6b7c90', width: 40, textAlign: 'right' }}>
                  {z.pct}%
                </span>
              </div>
            ))}
            <div style={{ marginTop: 8, fontSize: 12.5, color: '#6b7c90' }}>전체 {zoneTotal}건</div>
          </div>
        </div>
        <p style={captionStyle}>{captions.zone}</p>
      </section>

      <section className="pdf-section" style={{ ...sectionStyle, marginTop: 12 }}>
        <h2 style={titleStyle}>처리 현황</h2>
        <div className="pdf-chart" style={{ ...chartBoxStyle, height: 220 }}>
          <HandlingChart data={handling} includeA11yTable={false} />
        </div>
        <p style={captionStyle}>{captions.handling}</p>
      </section>

      {insight ? (
        <>
          <section className="pdf-section" style={{ ...sectionStyle, marginTop: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.08em', color: '#0876CA' }}>
              AI ANALYSIS REPORT
            </div>
            <h2 style={{ ...titleStyle, fontSize: 20, marginTop: 6 }}>AI 분석 보고서</h2>
            <div style={{ fontSize: 13, lineHeight: 1.55, color: '#4a5b70' }}>
              <div>
                <b>대상 기간</b> ·{' '}
                {[insight.periodLabel, insight.periodKey ? `(${insight.periodKey})` : '', insight.periodRange]
                  .filter(Boolean)
                  .join(' · ')}
              </div>
            </div>
          </section>
          {insight.sections.length === 0 ? (
            <section className="pdf-section" style={{ ...sectionStyle, marginTop: 12 }}>
              <p style={{ margin: 0, fontSize: 14, color: '#5a6b80', lineHeight: 1.6 }}>
                {insight.emptyMessage ?? '표시할 AI 리포트가 없습니다.'}
              </p>
            </section>
          ) : (
            insight.sections.map((section, index) => (
              <section
                key={`${section.title}-${index}`}
                className="pdf-section"
                style={{ ...sectionStyle, marginTop: 12 }}
              >
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'baseline',
                    gap: 10,
                    marginBottom: 10,
                    borderBottom: '1px solid #e6ebf2',
                    paddingBottom: 8,
                  }}
                >
                  <span style={{ fontSize: 12, fontWeight: 700, color: '#0876CA' }}>
                    {String(index + 1).padStart(2, '0')}
                  </span>
                  <h3 style={{ margin: 0, fontSize: 15, fontWeight: 700 }}>{section.title}</h3>
                </div>
                <ul style={{ margin: 0, paddingLeft: 18 }}>
                  {section.body
                    .split('\n')
                    .map((line) => line.trim())
                    .filter(Boolean)
                    .map((line) => (
                      <li
                        key={line}
                        style={{ marginBottom: 8, fontSize: 13.5, lineHeight: 1.6, color: '#243246' }}
                      >
                        {line}
                      </li>
                    ))}
                </ul>
              </section>
            ))
          )}
        </>
      ) : null}
    </div>
  )
}

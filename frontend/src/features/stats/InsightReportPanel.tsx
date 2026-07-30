import { useState } from 'react'
import type { AnalyticsInsightPeriodType } from '../../api/analyticsContracts'
import { R0KiDropdown } from '../../components/ui/R0KiDropdown'
import { parseInsightMarkdown } from './parseInsightMarkdown'
import { useAnalyticsInsight } from './useAnalyticsInsight'

const REPORT_PERIOD_OPTIONS = [{ value: 'month', label: '월간 리포트' }]

function toPeriodType(period: string): AnalyticsInsightPeriodType {
  return period === 'month' ? 'MONTH' : 'WEEK'
}

function formatPeriodRange(from: string, to: string) {
  const start = new Date(from)
  const end = new Date(to)
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return ''

  const fmt = (date: Date) =>
    `${date.getMonth() + 1}/${date.getDate()}`
  return `${fmt(start)}~${fmt(end)}`
}

function statusMessage(
  status: string | undefined,
  isLoading: boolean,
  isPolling: boolean,
  periodType: AnalyticsInsightPeriodType,
) {
  if (isLoading) return '리포트를 불러오는 중입니다.'
  if (status === 'PENDING') return '리포트 생성을 준비하고 있습니다.'
  if (status === 'PROCESSING' || isPolling) {
    return periodType === 'WEEK'
      ? '지난 주 데이터를 분석 중입니다. 잠시만 기다려 주세요.'
      : '지난 달 데이터를 분석 중입니다. 잠시만 기다려 주세요.'
  }
  if (status === 'FAILED') return '리포트 생성에 실패했습니다.'
  if (status === 'COMPLETED') return '리포트 내용을 표시할 수 없습니다.'
  return '표시할 리포트가 없습니다.'
}

/**
 * 통계 페이지 하단 AI 리포트 패널.
 *
 * - head(st-head) 레이아웃은 Stats 시안 그대로 유지
 * - 주/월 전환은 R0KiDropdown 사용
 * - 본문은 insightContent 마크다운 → st-in 카드로 렌더
 */
export function InsightReportPanel() {
  const [period, setPeriod] = useState('')
  const periodType = toPeriodType(period)
  const { data, isLoading, isPolling, isError, error, refetch } =
    useAnalyticsInsight(periodType)

  const sections =
    data?.generationStatus === 'COMPLETED' && data.insightContent
      ? parseInsightMarkdown(data.insightContent)
      : []

  const showReport = data?.generationStatus === 'COMPLETED' && sections.length > 0
  const showStatus =
    !showReport ||
    (data?.generationStatus === 'COMPLETED' && sections.length === 0)

  return (
    <div className="glass g2 st-ai">
      <div className="st-head">
        <span className="bul" />
        <span className="ttl">AI 리포트</span>
        <R0KiDropdown
          allLabel="주간 리포트"
          options={REPORT_PERIOD_OPTIONS}
          value={period}
          onChange={setPeriod}
        />
        <span className="meta">
          {data ? (
            <>
              <b>{data.periodKey}</b> {formatPeriodRange(data.periodFrom, data.periodTo)}
            </>
          ) : (
            '지난 완료 기간'
          )}
        </span>
      </div>

      {showStatus && (
        <div className="st-ins" style={{ gridTemplateColumns: '1fr' }}>
          <article className="st-in">
            <div className="hd">
              <span className="tt">
                {statusMessage(data?.generationStatus, isLoading, isPolling, periodType)}
              </span>
            </div>
            {isError && (
              <>
                <p className="bd">{error?.message ?? '리포트를 불러오지 못했습니다.'}</p>
                <button type="button" className="btn btn-s" onClick={refetch}>
                  다시 시도
                </button>
              </>
            )}
            {data?.generationStatus === 'FAILED' && !isError && (
              <button type="button" className="btn btn-s" onClick={refetch}>
                다시 시도
              </button>
            )}
          </article>
        </div>
      )}

      {showReport && (
        <div className="st-ins">
          {sections.map((section, index) => (
            <article key={section.title} className="st-in">
              <div className="hd">
                <span className="no num">{String(index + 1).padStart(2, '0')}</span>
                <span className="tt">{section.title}</span>
              </div>
              <p className="bd" style={{ whiteSpace: 'pre-line' }}>
                {section.body}
              </p>
            </article>
          ))}
        </div>
      )}
    </div>
  )
}

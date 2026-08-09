import type { AnalyticsInsightPeriodType, AnalyticsInsightResponse } from '../../api/analyticsContracts'
import { parseInsightMarkdown } from './parseInsightMarkdown'
import type { InsightPeriod } from './resolveInsightPeriod'

export function formatInsightPeriodRange(from: string, to: string) {
  const start = new Date(from)
  const end = new Date(to)
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return ''

  const fmt = (date: Date) => `${date.getMonth() + 1}/${date.getDate()}`
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
      ? '해당 주 데이터를 분석 중입니다. 잠시만 기다려 주세요.'
      : '해당 달 데이터를 분석 중입니다. 잠시만 기다려 주세요.'
  }
  if (status === 'FAILED') return '리포트 생성에 실패했습니다.'
  if (status === 'COMPLETED') return '리포트 내용을 표시할 수 없습니다.'
  return '표시할 리포트가 없습니다.'
}

export type InsightReportPanelProps = {
  insightPeriod: InsightPeriod | null
  data?: AnalyticsInsightResponse
  isLoading?: boolean
  isPolling?: boolean
  isError?: boolean
  error?: Error | null
  onRetry?: () => void
}

/**
 * 통계 페이지 하단 AI 리포트 패널.
 * 조회는 부모(Stats)가 담당하고, 여기서는 표시만 한다.
 */
export function InsightReportPanel({
  insightPeriod,
  data,
  isLoading = false,
  isPolling = false,
  isError = false,
  error = null,
  onRetry,
}: InsightReportPanelProps) {
  const periodType = insightPeriod?.periodType ?? 'WEEK'

  const sections =
    data?.generationStatus === 'COMPLETED' && data.insightContent
      ? parseInsightMarkdown(data.insightContent)
      : []

  const showReport = data?.generationStatus === 'COMPLETED' && sections.length > 0
  const showStatus = !showReport

  return (
    <div className="glass g2 st-ai">
      <div className="st-head">
        <span className="bul" />
        <span className="ttl">AI 리포트</span>
        <span className="sub">
          {insightPeriod
            ? insightPeriod.periodType === 'WEEK'
              ? '주간'
              : '월간'
            : '주/월만'}
        </span>
        <span className="meta">
          {insightPeriod ? (
            <>
              <b>{insightPeriod.periodKey}</b> {insightPeriod.label}
              {data ? ` · ${formatInsightPeriodRange(data.periodFrom, data.periodTo)}` : ''}
            </>
          ) : (
            '주·월 단위에서만 제공'
          )}
        </span>
      </div>

      {!insightPeriod ? (
        <div className="st-ins" style={{ gridTemplateColumns: '1fr' }}>
          <article className="st-in">
            <div className="hd">
              <span className="tt">분기·연 단위에는 AI 리포트가 없습니다</span>
            </div>
            <p className="bd">주 단위 또는 월 단위로 전환해 주세요.</p>
          </article>
        </div>
      ) : !insightPeriod.isComplete ? (
        <div className="st-ins" style={{ gridTemplateColumns: '1fr' }}>
          <article className="st-in">
            <div className="hd">
              <span className="tt">기간이 끝난 뒤 리포트가 제공됩니다</span>
            </div>
            <p className="bd">
              진행 중인 {insightPeriod.periodType === 'WEEK' ? '주' : '달'}에는 AI 리포트를
              생성하지 않습니다. 화살표로 지난 완료 기간을 선택해 주세요.
            </p>
          </article>
        </div>
      ) : showStatus ? (
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
                {onRetry && (
                  <button type="button" className="btn btn-s" onClick={onRetry}>
                    다시 시도
                  </button>
                )}
              </>
            )}
            {data?.generationStatus === 'FAILED' && !isError && onRetry && (
              <button type="button" className="btn btn-s" onClick={onRetry}>
                다시 시도
              </button>
            )}
          </article>
        </div>
      ) : null}

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

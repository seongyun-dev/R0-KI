import type { AiInsight } from '../../types/domain'

/* AI 인사이트 — 리포트 형식.
   종합 요약 문단(st-sum) + 번호·제목·권장 조치가 붙은 소견 카드(st-in) 2열.
   서버가 문자열 배열만 주는 경우를 대비해 body로 정규화한다. */

const normalize = (item: string | AiInsight): AiInsight =>
  typeof item === 'string' ? { title: 'AI 분석', body: item } : item

export function AiInsights({
  overview,
  insights,
}: {
  /** 종합 요약 문단 — 통계 수치로 화면에서 조립 */
  overview?: string
  insights: (string | AiInsight)[]
}) {
  return (
    <>
      {overview && <p className="st-sum">{overview}</p>}
      <div className="st-ins">
        {insights.map(normalize).map((it, i) => (
          <article key={it.title + it.body} className="st-in">
            <div className="hd">
              <span className="no num">{String(i + 1).padStart(2, '0')}</span>
              <b className="tt">{it.title}</b>
              {it.action && <span className="act">권장 · {it.action}</span>}
            </div>
            <p className="bd">{it.body}</p>
          </article>
        ))}
      </div>
    </>
  )
}

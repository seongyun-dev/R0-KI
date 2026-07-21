import type { CSSProperties } from 'react'
import { CheckIcon } from '../../components/icons'
import { Eyebrow } from '../../components/ui'
import { cn } from '../../lib/cn'

// 카피는 landing_1p.html 해결하는 문제 4종. solvedBy = 이 문제를 푸는 기능(기능 섹션과 연결)
const problems = [
  {
    no: '01',
    tag: '감지 지연',
    title: '순찰과 순찰 사이가 비어 있습니다',
    desc: '사람이 도는 몇 차례 회차 사이에 일어난 일은, 누군가 신고할 때까지 아무도 모릅니다.',
    solvedBy: '24시간 자율 순찰로 공백을 없앱니다',
  },
  {
    no: '02',
    tag: '기록 휘발',
    title: '수기 일지에는 요약만 남습니다',
    desc: '누가 언제 어디를 돌았는지가 기억과 필체에 의존하고, 며칠만 지나도 확인할 방법이 없습니다.',
    solvedBy: '회차별 경로와 시각이 자동으로 남습니다',
  },
  {
    no: '03',
    tag: '증거 부재',
    title: '사고 뒤에야 영상을 되감습니다',
    desc: '고정 CCTV는 찍힌 곳만 남기고, 필요한 장면을 찾는 일은 사람이 몇 시간씩 돌려봐야 합니다.',
    solvedBy: '탐지 순간의 스냅샷이 바로 붙습니다',
  },
  {
    no: '04',
    tag: '반복 노동',
    title: '같은 경로, 같은 양식이 매일 반복됩니다',
    desc: '정해진 길을 걷고 정해진 칸을 채우는 시간이, 정작 사람이 판단해야 할 일을 밀어냅니다.',
    solvedBy: '스케줄 순찰과 자동 작성이 대신합니다',
  },
]

export type ProblemSectionProps = {
  /** 로봇이 지금 처리 중인 문제 (-1이면 아직 시작 전) */
  active?: number
  /** 처리 완료한 문제 수 */
  solved?: number
}

/**
 * 해결하는 문제 — 로봇이 문제 지점을 하나씩 찾아가 처리한다.
 * active/solved를 주지 않으면(모바일·모션 최소화) 전부 펼친 정적 그리드로 표시.
 */
export function ProblemSection({ active = -1, solved = -1 }: ProblemSectionProps) {
  const narrative = solved >= 0

  return (
    <section id="problem">
      <div className="shell sec-pad">
        <div className="center-head">
          <span data-reveal="up" style={{ '--ry': '10px' } as CSSProperties}>
            <Eyebrow bordered>해결하는 문제</Eyebrow>
          </span>
          <h2 className="sec-h2" data-reveal="line" data-delay="120">
            <span className="line"><span className="inner">지금 단지 순찰은 사람의 시간에 묶여 있습니다</span></span>
          </h2>
          <p className="prob-sub" data-reveal="up" data-delay="240" style={{ '--ry': '10px' } as CSSProperties}>
            {narrative
              ? '로봇이 네 곳의 문제 지점을 차례로 처리합니다.'
              : '순찰이 도는 동안만 단지가 보이고, 남는 기록은 사람이 기억한 만큼입니다.'}
          </p>
        </div>

        <ul className="prob-grid">
          {problems.map((p, i) => {
            const isSolved = narrative && i < solved
            // 로봇이 향하고 있는 = 첫 미해결 문제
            const isActive = narrative && !isSolved && i === active
            return (
              <li
                key={p.no}
                data-reveal={narrative ? undefined : 'up'}
                data-delay={i * 90}
                style={{ '--ry': '30px' } as CSSProperties}
              >
                <article
                  className={cn(
                    'prob-card',
                    narrative && 'is-narrative',
                    isActive && 'is-active',
                    isSolved && 'is-solved',
                  )}
                >
                  <span className="prob-tag font-mono">
                    [ {p.no} · {p.tag} ]
                  </span>
                  <h3>{p.title}</h3>
                  <p>{p.desc}</p>

                  {narrative && (
                    <p className="prob-status" aria-live="polite">
                      {isSolved ? (
                        <>
                          <CheckIcon className="prob-check" aria-hidden />
                          {p.solvedBy}
                        </>
                      ) : isActive ? (
                        <span className="prob-working">로봇 출동 중…</span>
                      ) : (
                        <span className="prob-pending">미해결</span>
                      )}
                    </p>
                  )}
                </article>
              </li>
            )
          })}
        </ul>
      </div>
    </section>
  )
}

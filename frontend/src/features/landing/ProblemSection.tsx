import type { CSSProperties } from 'react'
import { CheckIcon } from '../../components/icons'
import { Eyebrow } from '../../components/ui'
import { cn } from '../../lib/cn'

// 카피는 landing_1p.html 해결하는 문제 4종. solvedBy = 이 문제를 푸는 기능(기능 섹션과 연결)
const problems = [
  {
    no: '01',
    tag: '예기치 못한 상황 대응 지연',
    title: '긴급 상황 발생 시 즉각 대응이 어렵습니다',
    desc: '상황을 발견해도 어떻게 대응할지 판단하고 확인하는 시간이 더해져, 실제 조치로 이어지기까지 늦어집니다.',
    solvedBy: '실시간 맵 관제',
  },
  {
    no: '02',
    tag: '즉각 해결의 부재',
    title: '이상 상황을 즉시 확인하고 해결하기 어렵습니다',
    desc: '불법 주차나 무단 투기를 발견해도 관리실에 알리고 조치하기까지 시간이 걸려, 상황이 그대로 남습니다.',
    solvedBy: '실시간 알림',
  },
  {
    no: '03',
    tag: '순찰일지 수기 작성의 번거로움',
    title: '매번 순찰일지를 수기로 작성해야 합니다',
    desc: '순찰을 마칠 때마다 시간과 구역, 특이사항을 손으로 적어야 하고, 쌓인 일지를 다시 찾아보기도 번거롭습니다.',
    solvedBy: '자동 보고서 · AI 인사이트',
  },
  {
    no: '04',
    tag: '번거로운 교대근무',
    title: '여러 사람이 교대로 순찰해야 하는 번거로움이 있습니다',
    desc: '밤낮없이 이어지는 순찰을 사람이 번갈아 맡다 보니, 근무 조율과 인력 배치에 매번 손이 갑니다.',
    solvedBy: '로봇 자율 순찰',
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
            <Eyebrow bordered>경비원들이 겪고 있는 문제</Eyebrow>
          </span>
          <h2 className="sec-h2" data-reveal="line" data-delay="120">
            <span className="line"><span className="inner">반복 순찰과 현장 대응이 경비원에게 큰 부담이 됩니다</span></span>
          </h2>
          <p className="prob-sub" data-reveal="up" data-delay="240" style={{ '--ry': '10px' } as CSSProperties}>
            {narrative
              ? '순찰 로봇 R0-Ki가 반복 순찰부터 실시간 관제와 기록 관리까지 네 가지 업무 부담을 줄입니다.'
              : '교대 순찰과 현장 대응, 일지 작성까지 경비 업무의 부담이 곳곳에 쌓여 있습니다.'}
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
                  {/* 대괄호는 앞뒤 낱말에 붙여둔다(nbsp) — 좁은 폭에서 줄이 접힐 때
                      여는/닫는 괄호만 다음 줄로 떨어져 깨져 보이는 것을 막는다 */}
                  <span className="prob-tag font-mono">
                    [&nbsp;{p.no} · {p.tag}&nbsp;]
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

import type { CSSProperties } from 'react'
import { ArrowRightIcon } from '../../components/icons'
import { JOURNEY_STEPS } from './journeySteps'

/**
 * 해결하는 문제 → 기능 사이를 잇는 전환 구간.
 * 방금 처리한 네 문제가 각각 어떤 기능으로 이어지는지 한 화면에 보여주고 넘어간다.
 * 매핑은 journeySteps의 answers를 그대로 쓴다(두 곳이 어긋나지 않도록).
 */
export function BridgeSection() {
  // 문제 번호 순(01→04)으로 보여줘야 앞 섹션과 읽는 순서가 맞는다
  const rows = [...JOURNEY_STEPS].sort((a, b) => a.answers.localeCompare(b.answers))

  return (
    <section className="bridge" aria-label="문제와 기능의 연결">
      <div className="shell bridge-inner">
        <p className="bridge-eyebrow font-mono" data-reveal="up" style={{ '--ry': '10px' } as CSSProperties}>
          [ 문제 → 기능 ]
        </p>
        <h2 className="bridge-h2" data-reveal="line" data-delay="120">
          <span className="line"><span className="inner">네 가지 문제를 네 가지로 답합니다</span></span>
        </h2>

        <ul className="bridge-rows">
          {rows.map((s, i) => (
            <li
              key={s.no}
              data-reveal="up"
              data-delay={i * 80}
              style={{ '--ry': '18px' } as CSSProperties}
            >
              <span className="bridge-from font-mono">{s.answers}</span>
              <ArrowRightIcon className="bridge-arrow" aria-hidden />
              <span className="bridge-to">{s.title}</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}

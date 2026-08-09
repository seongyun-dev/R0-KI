import type { CSSProperties } from 'react'
import { Eyebrow } from '../../components/ui'

// 카피·구성은 와이어프레임 1p 작동 방식 4스텝. 03 알림은 긴급 단계라 강조.
const steps = [
  { no: '01', title: '순찰', desc: '가입할 때 등록한 구역과 체크포인트를 따라 로봇이 스케줄대로 자율 주행합니다.', alert: false },
  { no: '02', title: '감지', desc: '온보드 AI 비전이 영상에서 이상 상황을 판별하고 유형과 신뢰도를 매깁니다.', alert: false },
  { no: '03', title: '알림', desc: '관제 화면에 위치·시각·스냅샷이 즉시 뜨고, 긴급 건은 모달로 관리자를 붙잡습니다.', alert: true },
  { no: '04', title: '기록', desc: '순찰 경로와 처리 결과가 일지에 자동 저장되고, 통계 화면에서 누적됩니다.', alert: false },
]

/** 작동 방식 (1p) — 순찰 → 감지 → 알림 → 기록 4스텝 타임라인 */
export function HowSection() {
  return (
    <section id="how">
      <div className="shell sec-pad">
        <div className="center-head">
          <span data-reveal="up" style={{ '--ry': '10px' } as CSSProperties}>
            <Eyebrow bordered>작동 방식</Eyebrow>
          </span>
          <h2 className="sec-h2" data-reveal="line" data-delay="120">
            <span className="line"><span className="inner">한 번의 순찰이 이렇게 흘러갑니다</span></span>
          </h2>
        </div>

        <ol className="how-steps">
          {steps.map((s, i) => (
            <li
              key={s.no}
              className={`how-step${s.alert ? ' how-step--alert' : ''}`}
              data-reveal="up"
              data-delay={i * 90}
              // --sd: 원(.how-num) 팝 애니메이션을 리빌과 같은 순서로 지연
              style={{ '--ry': '24px', '--sd': `${i * 90 + 120}ms` } as CSSProperties}
            >
              <span className="how-num font-mono tabular">{s.no}</span>
              <h3>{s.title}</h3>
              <p>{s.desc}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  )
}

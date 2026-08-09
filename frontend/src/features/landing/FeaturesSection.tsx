import type { CSSProperties, ReactNode } from 'react'
import { Tag } from '../../components/ui'
import { Eyebrow } from '../../components/ui'

type Feature = {
  no: string
  title: string
  desc: string
  tags: string[]
  icon: ReactNode
}

const iconProps = {
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.8,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
  'aria-hidden': true,
} as const

// 카피는 landing_1p.html 기능 4종, 카드 디자인은 landing.html 그대로
const features: Feature[] = [
  {
    no: '01',
    title: '실시간 지도 관제',
    desc: '로봇의 현재 위치와 이동 경로, 체크포인트를 지도 위에서 그대로 봅니다. 이벤트가 발생한 지점은 지도에 바로 찍히고, 클릭하면 현장 스냅샷과 탐지 시각·신뢰도가 함께 열립니다.',
    tags: ['실시간 지도', '이벤트 핀', '현장 스냅샷'],
    icon: (
      <svg {...iconProps}>
        <path d="M2 8a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2z" />
        <path d="m15 10 5-3v10l-5-3" />
      </svg>
    ),
  },
  {
    no: '02',
    title: '이상 상황 감지와 즉시 알림',
    desc: '응급상황(쓰러짐 의심)·불법주차·무단투기를 AI 비전이 판별하고, 신뢰도와 스냅샷을 붙여 관제 화면에 띄웁니다. 같은 지점에서 반복 탐지되면 긴급으로 자동 승격됩니다.',
    tags: ['AI 비전', '신뢰도 표시', '긴급 자동 승격'],
    icon: (
      <svg {...iconProps}>
        <path d="M12 9v4M12 17h.01" />
        <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
      </svg>
    ),
  },
  {
    no: '03',
    title: '자동 순찰 일지',
    desc: '순찰 회차별 시작·종료 시각, 구역 순서, 이동거리, 발생 이벤트가 자동으로 저장돼 기간별로 다시 찾아볼 수 있습니다.',
    tags: ['자동 기록', '회차별 로그', '기간별 조회'],
    icon: (
      <svg {...iconProps}>
        <path d="M4 4h11l5 5v11a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1Z" />
        <path d="M14 4v5h5M8 13h8M8 17h5" />
      </svg>
    ),
  },
  {
    no: '04',
    title: '자율 주행 및 자동 충전',
    desc: '스케줄에 맞춰 스스로 출동하고, 배터리가 떨어지면 스테이션으로 복귀해 충전한 뒤 다음 회차를 이어갑니다.',
    tags: ['자율 주행', '스케줄 순찰', '자동 충전'],
    icon: (
      <svg {...iconProps}>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v5l3 2" />
      </svg>
    ),
  },
]

export function FeaturesSection() {
  return (
    <section id="features">
      <div className="shell sec-pad">
        <div className="center-head">
          <span data-reveal="up" style={{ '--ry': '10px' } as CSSProperties}>
            <Eyebrow bordered>기능</Eyebrow>
          </span>
          <h2 className="sec-h2" data-reveal="line" data-delay="120">
            <span className="line"><span className="inner">네 가지 문제에 하나씩 대응합니다</span></span>
          </h2>
        </div>
        <ul className="feat-grid">
          {features.map((f, i) => (
            <li key={f.no} data-reveal="up" data-delay={i * 90} style={{ '--ry': '40px' } as CSSProperties}>
              <article className="feat-card">
                <div className="glow" />
                <div className="feat-top">
                  <span className="feat-ico">{f.icon}</span>
                  <span className="feat-no font-mono">{f.no}</span>
                </div>
                <div className="feat-body">
                  <h3>{f.title}</h3>
                  <p>{f.desc}</p>
                  <div className="tags">
                    {f.tags.map((t) => (
                      <Tag key={t} tone="dark">{t}</Tag>
                    ))}
                  </div>
                </div>
              </article>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}

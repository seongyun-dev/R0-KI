import { useNavigate } from 'react-router-dom'
import { AlertTriangleIcon } from '../../components/icons'
import { Button } from '../../components/ui'

export type HeroProps = {
  /** 커서로 로봇을 움직이면 힌트를 숨긴다 (로봇 캔버스는 PatrolStage가 소유) */
  hintHidden: boolean
}

/** 히어로 — 카피/CTA/통계. 배경 3D 순찰 장면은 PatrolStage가 두 섹션에 걸쳐 깔아준다 */
export function Hero({ hintHidden }: HeroProps) {
  const navigate = useNavigate()

  return (
    <section id="home">
      <div className="hero-vignette" />

      <div className="robot-chip robot-chip--status">
        <span className="live" />
        <span>가동중 · 3대</span>
      </div>
      <div className="robot-chip robot-chip--event">
        <span className="k"><AlertTriangleIcon style={{ fontSize: '.9rem' }} /></span>
        <span>
          <span className="t">불법주차 · A동</span>
          <br />
          <span className="s">2분 전 감지</span>
        </span>
      </div>
      <div className="robot-hint" style={{ opacity: hintHidden ? 0 : 1 }}>
        커서를 움직이면 로봇이 따라 순찰해요
      </div>

      <div className="shell hero-grid">
        <div className="hero-left">
          <span className="hero-eyebrow" data-reveal="up" data-gate="ready" data-delay="200" style={{ '--ry': '10px' } as React.CSSProperties}>
            <span className="dot" />자율 순찰 · AI 비전 · 관제 대시보드
          </span>
          <h1 className="hero-h1" data-reveal="line" data-gate="ready" data-delay="250" data-line-stagger="110">
            <span className="line"><span className="inner">로봇과 경비원이 함께 만드는</span></span>
            <span className="line"><span className="inner"><span className="accent">더 효율적인 단지 순찰</span></span></span>
          </h1>
          <p className="hero-sub" data-reveal="up" data-gate="ready" data-delay="450" style={{ '--ry': '10px' } as React.CSSProperties}>
            로봇이 지정된 구역을 순찰하며 현장 정보를 관리실로 전달합니다.
            <br />
            경비원은 관제 화면에서 순찰 상황을 확인하고, 필요한 상황에 집중해 대응할 수 있습니다.
          </p>
          <div className="hero-stats" data-reveal="up" data-gate="ready" data-delay="600" style={{ '--ry': '10px' } as React.CSSProperties}>
            <div className="hero-stat"><div className="n"><b>로봇</b></div><div className="l">구역별 반복 순찰</div></div>
            <div className="hero-stat"><div className="n"><b>실시간</b></div><div className="l">관리실 현장 확인</div></div>
            <div className="hero-stat"><div className="n"><b>자동</b></div><div className="l">순찰 기록 관리</div></div>
          </div>
          <div className="cta-row" data-reveal="up" data-gate="ready" data-delay="750" style={{ '--ry': '10px' } as React.CSSProperties}>
            <Button variant="accent" withArrow="right" onClick={() => navigate('/signup/onboarding')}>회원가입하기</Button>
            <Button variant="outline" onClick={() => navigate('/login')}>관리자 로그인 →</Button>
          </div>
        </div>
      </div>

    </section>
  )
}

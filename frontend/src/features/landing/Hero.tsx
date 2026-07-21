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
            <span className="line"><span className="inner">사람이 못 보는 시간에도</span></span>
            <span className="line"><span className="inner"><span className="accent">단지는 계속 순찰됩니다</span></span></span>
          </h1>
          <p className="hero-sub" data-reveal="up" data-gate="ready" data-delay="450" style={{ '--ry': '10px' } as React.CSSProperties}>
            로봇이 정해진 구역을 스스로 돌며 이상 상황을 판별하고, 위치·시각·현장 스냅샷을 관리실 화면에 바로 띄웁니다. 순찰이 끝나면 일지는 자동으로 남습니다.
          </p>
          <div className="cta-row" data-reveal="up" data-gate="ready" data-delay="600" style={{ '--ry': '10px' } as React.CSSProperties}>
            <Button variant="accent" withArrow="right" onClick={() => navigate('/signup/onboarding')}>회원가입하기</Button>
            <Button variant="outline" onClick={() => navigate('/login')}>관리자 로그인 →</Button>
          </div>
          <div className="hero-stats" data-reveal="up" data-gate="ready" data-delay="750" style={{ '--ry': '10px' } as React.CSSProperties}>
            <div className="hero-stat"><div className="n"><b>24</b>h</div><div className="l">무인 자율 순찰</div></div>
            <div className="hero-stat"><div className="n"><b>4</b>종</div><div className="l">이상 상황 감지</div></div>
            <div className="hero-stat"><div className="n"><b>100%</b></div><div className="l">순찰 일지 자동 작성</div></div>
          </div>
        </div>
      </div>

      <div className="shell hero-status" data-reveal="fade" data-gate="ready" data-delay="900">
        <span>2014년부터 자율 주행 기술 개발</span>
        <span className="mid">전국 어디서나 원격 관제</span>
        <span className="end">아래로 스크롤 <span aria-hidden="true">↓</span></span>
      </div>
    </section>
  )
}

import { Link, useLocation, useNavigate } from 'react-router-dom'
import { BrandMark, MenuIcon } from '../icons'
import { Button } from '../ui/Button'
import { cn } from '../../lib/cn'
import './siteHeader.css'

export type SiteHeaderProps = {
  /** 로더 종료 후 진입 애니메이션 (랜딩 전용) */
  shown?: boolean
  clock: string
  /**
   * 히어로 위에 겹치지 않고 문서 흐름에 놓는다 (히어로가 없는 화면).
   * 이때는 진입 애니메이션 없이 처음부터 보인다.
   */
  plain?: boolean
  /** 있으면 브랜드를 누를 때 그 섹션으로 스크롤, 없으면 홈으로 이동 */
  onScrollTo?: (id: string) => void
  /** 풀스크린 메뉴가 있는 화면에서만 메뉴 버튼을 띄운다 */
  onMenuOpen?: () => void
}

/**
 * 상단바 — 랜딩과 로그인이 함께 쓴다.
 * 가운데는 순찰 ON/OFF 토글: OFF는 랜딩(소개), ON은 관제(로그인).
 * 실제로 순찰을 켜고 끄는 게 아니라 두 화면을 오가는 세그먼트 컨트롤이라
 * 스위치가 아닌 링크 두 개로 만들고 현재 위치를 aria-current로 알린다.
 */
export function SiteHeader({ shown, clock, plain, onScrollTo, onMenuOpen }: SiteHeaderProps) {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  // 회원가입처럼 둘 다 아닌 화면에서는 어느 쪽도 켜지 않는다(현재 위치를 잘못 말하지 않도록)
  const isOn = pathname.startsWith('/login')
  const isOff = pathname === '/'

  return (
    <header className={cn('site-header', plain && 'is-plain', shown && 'in')}>
      <div className="shell header__row">
        {onScrollTo ? (
          <button type="button" className="brand" onClick={() => onScrollTo('home')} aria-label="AI 순찰 시스템 홈">
            <BrandMark className="mk" />
            <span>AI 순찰 시스템</span>
          </button>
        ) : (
          <Link to="/" className="brand" aria-label="AI 순찰 시스템 홈">
            <BrandMark className="mk" />
            <span>AI 순찰 시스템</span>
          </Link>
        )}

        <nav className="patrol-switch" aria-label="순찰 상태">
          <Link
            to="/"
            className={cn('patrol-switch__seg', isOff && 'is-on')}
            aria-current={isOff ? 'page' : undefined}
          >
            <span className="patrol-switch__dot" aria-hidden />
            순찰 OFF
          </Link>
          <Link
            to="/login"
            className={cn('patrol-switch__seg', isOn && 'is-on')}
            aria-current={isOn ? 'page' : undefined}
          >
            <span className="patrol-switch__dot patrol-switch__dot--live" aria-hidden />
            순찰 ON
          </Link>
        </nav>

        <div className="header__right">
          <div className="clock-chip">
            <span className="live" />
            <span className="lbl">관제 시각</span>
            <span className="time font-mono tabular">{clock}</span>
          </div>
          <Button
            variant="accent"
            withArrow="up-right"
            className="header-cta"
            onClick={() => navigate('/signup/onboarding')}
          >
            회원가입하기
          </Button>
          {onMenuOpen && (
            <button type="button" className="menu-btn" onClick={onMenuOpen} aria-label="메뉴 열기">
              <span className="hv">
                <MenuIcon />
                <span>메뉴</span>
              </span>
            </button>
          )}
        </div>
      </div>
    </header>
  )
}

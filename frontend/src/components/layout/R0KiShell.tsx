import { useEffect, useState, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../../features/auth/useAuthStore'
import '../../styles/r0ki.css'

/* R0-Ki · AURA GLASS 공용 셸 — 상단바(로고·주 메뉴·알림·시계·야간모드) + 씬 배경.
   대시보드/순찰 관리 등 리디자인된 화면이 공유한다. 한 화면 고정(스크롤 없음)은
   .r0ki 루트가 담당하고, 각 화면 콘텐츠는 children 으로 들어온다. */

type Theme = 'crystal' | 'nocturne'
const THEME_KEY = 'r0ki-theme'

export function useR0KiTheme() {
  const [theme, setTheme] = useState<Theme>(() =>
    localStorage.getItem(THEME_KEY) === 'nocturne' ? 'nocturne' : 'crystal',
  )
  const toggle = () => {
    setTheme((prev) => {
      const next = prev === 'crystal' ? 'nocturne' : 'crystal'
      localStorage.setItem(THEME_KEY, next)
      return next
    })
  }

  /* 테마를 <html> 에도 심는다 (S15P11E103-295).
     ui/Modal 은 document.body 로 포털해서 .r0ki 바깥에 그려지므로
     [data-theme] 셀렉터가 닿지 않는다 — 그래서 야간에도 흰 카드로 떴다.
     여기서 심어 준 값으로 r0ki.css 끝의 포털 전용 규칙이 걸린다. */
  useEffect(() => {
    document.documentElement.dataset.r0kiTheme = theme
  }, [theme])

  return { theme, toggle }
}

/** 시계 — 실제 한국시간, 1초 갱신 */
export function useClockText() {
  const [text, setText] = useState(() => formatClock(new Date()))
  useEffect(() => {
    const t = setInterval(() => setText(formatClock(new Date())), 1000)
    return () => clearInterval(t)
  }, [])
  return text
}
/* "한국시간"이라고 적어 놓고 브라우저 로컬시간을 쓰고 있었다 —
   시간대가 다른 환경에서 틀린 시각이 뜬다. 서울 기준으로 고정한다.
   (en-GB 는 24시간 HH:MM:SS 를 안정적으로 낸다. ko-KR 은 자정을 24시로 쓰는 경우가 있다) */
const SEOUL_CLOCK = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Asia/Seoul',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
})

function formatClock(d: Date) {
  return SEOUL_CLOCK.format(d)
}

// notifications 는 주 메뉴가 아닌 상단바 알림 버튼이 활성 표시를 가져간다
export type R0KiNavKey =
  | 'dashboard'
  | 'patrol'
  | 'events'
  | 'robots'
  | 'residents'
  | 'stats'
  | 'notifications'

const NAV_ITEMS: { key: R0KiNavKey; label: string; to: string }[] = [
  { key: 'dashboard', label: '대시보드', to: '/app' },
  { key: 'patrol', label: '순찰 관리', to: '/app/patrol' },
  { key: 'events', label: '이벤트 관리', to: '/app/events' },
  { key: 'robots', label: '로봇 관리', to: '/app/robots' },
  { key: 'residents', label: '입주민 관리', to: '/app/residents' },
  { key: 'stats', label: '통계', to: '/app/stats' },
]

export type R0KiShellProps = {
  /** 상단바 주 메뉴 활성 항목 */
  active: R0KiNavKey
  /** 알림 버튼 왼쪽 슬롯 (대시보드의 로봇 상태칩 등) */
  statusChip?: ReactNode
  children: ReactNode
}

export function R0KiShell({ active, statusChip, children }: R0KiShellProps) {
  const navigate = useNavigate()
  const { theme, toggle } = useR0KiTheme()
  const clock = useClockText()
  const loginId = useAuthStore((s) => s.loginId)
  const memberName = useAuthStore((s) => s.memberName)
  const logout = useAuthStore((s) => s.logout)

  const onLogout = () => {
    logout()
    navigate('/', { replace: true })
  }

  return (
    <div className="r0ki" data-theme={theme}>
      <div className="wrap">
        <div className="stage">
          <div className="scene" />

          {/* ── 상단바 ── */}
          <div className="topbar glass g2" style={{ borderRadius: 'var(--r-pill)' }}>
            <div className="brand"><span className="core" /> R0-Ki</div>
            <nav className="nav" aria-label="주 메뉴">
              {NAV_ITEMS.map((item) => (
                <Link
                  key={item.key}
                  to={item.to}
                  className="nv"
                  aria-current={item.key === active ? 'page' : undefined}
                  aria-pressed={item.key === active ? 'true' : undefined}
                >
                  {item.label}
                </Link>
              ))}
            </nav>
            <div className="sp" />
            {statusChip}
            {/* 입주민 발송 내역으로 간다. 배지는 두지 않는다 —
                긴급 이벤트 건수를 달고 있었는데 이 페이지 내용과 맞지 않았다. */}

            <div className="clock num">
              {clock}<small>한국시간</small>
            </div>
            <button type="button" className="themebtn" onClick={toggle}>
              {theme === 'crystal' ? '야간 모드' : '주간 모드'}
            </button>
            <span className="admin">
              <svg viewBox="0 0 24 24"><circle cx="12" cy="8" r="4" /><path d="M4 21c0-4 3.6-6.5 8-6.5s8 2.5 8 6.5" /></svg>
              {(memberName ?? loginId) && <b className="who">{memberName ?? loginId}</b>} 관리자
            </span>
            <button type="button" className="themebtn" onClick={onLogout}>
              로그아웃
            </button>
          </div>

          {children}
        </div>
      </div>
    </div>
  )
}

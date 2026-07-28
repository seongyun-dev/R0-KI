import { useEffect, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useEvents } from '../../features/events/useEvents'
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
function formatClock(d: Date) {
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

export type R0KiNavKey = 'dashboard' | 'patrol' | 'events' | 'robots' | 'stats'

const NAV_ITEMS: { key: R0KiNavKey; label: string; to: string }[] = [
  { key: 'dashboard', label: '대시보드', to: '/app' },
  { key: 'patrol', label: '순찰 관리', to: '/app/patrol' },
  { key: 'events', label: '이벤트 관리', to: '/app/events' },
  { key: 'robots', label: '로봇 관리', to: '/app/robots' },
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
  const { theme, toggle } = useR0KiTheme()
  const clock = useClockText()
  // 알림 배지 — 긴급 이벤트 건수 (실서버 연동 시 그대로 값만 교체)
  const { data: events } = useEvents()
  const urgentCount = (events ?? []).filter((e) => e.riskLevel === '긴급').length

  return (
    <div className="r0ki" data-theme={theme}>
      <div className="wrap">
        <div className="stage">
          <div className="scene" />

          {/* ── 상단바 ── */}
          <div className="topbar glass g2" style={{ borderRadius: 'var(--r-pill)' }}>
            <div className="brand"><span className="core" /> R0-Ki</div>
            <nav className="nav" aria-label="주 메뉴">
              {NAV_ITEMS.map((item) =>
                item.key === active ? (
                  <span key={item.key} className="nv" aria-pressed="true">{item.label}</span>
                ) : (
                  <Link key={item.key} to={item.to} className="nv">{item.label}</Link>
                ),
              )}
            </nav>
            <div className="sp" />
            {statusChip}
            <Link to="/app/events" className="alarmbtn" aria-label={`긴급 알림 ${urgentCount}건`}>
              알림{urgentCount > 0 && <span className="badge num">{urgentCount}</span>}
            </Link>
            <div className="clock num">
              {clock}<small>한국시간</small>
            </div>
            <button type="button" className="themebtn" onClick={toggle}>
              {theme === 'crystal' ? '야간 모드' : '주간 모드'}
            </button>
          </div>

          {children}
        </div>
      </div>
    </div>
  )
}

import { NavLink } from 'react-router-dom'
import { cn } from '../../lib/cn'
import {
  AlertTriangleIcon,
  BellIcon,
  BotIcon,
  ChartIcon,
  DashboardIcon,
  RouteIcon,
} from '../icons'

// 와이어프레임 공통 사이드바 — Dashboard · 순찰관리 · 이벤트관리 · 로봇관리 · 통계 · 알림
const items = [
  { to: '/app', label: 'Dashboard', icon: DashboardIcon, end: true },
  { to: '/app/patrol', label: '순찰관리', icon: RouteIcon },
  { to: '/app/events', label: '이벤트관리', icon: AlertTriangleIcon },
  { to: '/app/robots', label: '로봇관리', icon: BotIcon },
  { to: '/app/stats', label: '통계', icon: ChartIcon },
] as const

export function Sidebar() {
  return (
    <nav aria-label="주 메뉴" className="flex shrink-0 lg:w-56 lg:flex-col lg:gap-1">
      <ul className="flex w-full gap-1 overflow-x-auto lg:flex-col">
        {items.map(({ to, label, icon: Icon, ...rest }) => (
          <li key={to} className="shrink-0 lg:shrink">
            <NavLink
              to={to}
              end={'end' in rest && rest.end}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-2.5 whitespace-nowrap rounded-control px-3.5 py-2.5 text-sm font-semibold transition-colors',
                  isActive
                    ? 'bg-ink text-white'
                    : 'text-muted hover:bg-surface hover:text-fg',
                )
              }
            >
              <Icon className="text-base" />
              {label}
            </NavLink>
          </li>
        ))}
        <li className="shrink-0 lg:shrink">
          <span
            title="준비 중"
            className="flex cursor-not-allowed items-center gap-2.5 whitespace-nowrap rounded-control px-3.5 py-2.5 text-sm font-semibold text-subtle"
          >
            <BellIcon className="text-base" />
            알림
          </span>
        </li>
      </ul>
    </nav>
  )
}

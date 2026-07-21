import { Link, useNavigate } from 'react-router-dom'
import { BrandMark, ChevronDownIcon } from '../icons'
import { useAuthStore } from '../../features/auth/useAuthStore'

/** 앱 상단 헤더 — `AI 순찰 시스템` 브랜드 + `관리자 ▾ | 로그아웃` (와이어프레임 공통) */
export function AppHeader() {
  const navigate = useNavigate()
  const logout = useAuthStore((s) => s.logout)
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-bg/90 backdrop-blur">
      <div className="flex h-16 items-center justify-between gap-4 px-4 sm:px-6">
        <Link to="/app" className="flex items-center gap-2 text-lg font-bold">
          <BrandMark className="h-6 w-6 text-accent" />
          AI 순찰 시스템
        </Link>
        <div className="flex items-center gap-1 text-sm">
          <button
            type="button"
            className="inline-flex items-center gap-1 rounded-control px-3 py-2 font-semibold transition-colors hover:bg-surface"
          >
            관리자
            <ChevronDownIcon className="text-muted" />
          </button>
          <span aria-hidden className="mx-1 h-4 w-px bg-line" />
          <button
            type="button"
            onClick={() => {
              logout()
              navigate('/login', { replace: true })
            }}
            className="rounded-control px-3 py-2 font-semibold text-muted transition-colors hover:bg-surface hover:text-fg"
          >
            로그아웃
          </button>
        </div>
      </div>
    </header>
  )
}

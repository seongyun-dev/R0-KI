import { Outlet } from 'react-router-dom'
import { AppHeader } from './AppHeader'
import { Sidebar } from './Sidebar'

/** 관제 앱 공통 셸 — 헤더 + 좌측 사이드바 + 본문 (라우트 /app/*) */
export function AppShell() {
  return (
    <div className="min-h-screen bg-bg">
      {/* 키보드 사용자용 본문 바로가기 */}
      <a
        href="#app-main"
        className="sr-only rounded-control bg-ink px-4 py-2 text-sm font-semibold text-white focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50"
      >
        본문 바로가기
      </a>
      <AppHeader />
      <div className="mx-auto flex max-w-shell flex-col gap-6 px-4 py-6 sm:px-6 lg:flex-row lg:gap-8">
        <Sidebar />
        <main id="app-main" tabIndex={-1} className="min-w-0 flex-1 pb-16">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

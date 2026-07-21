import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { BrandMark } from '../../components/icons'
import { cn } from '../../lib/cn'

export type AuthLayoutProps = {
  title: string
  description?: string
  /** 온보딩 등 넓은 화면용 */
  wide?: boolean
  /**
   * 상단바를 얹을 때 넘긴다. 넘기면 자체 브랜드 링크 대신 이 헤더가 쓰인다
   * (브랜드가 두 번 나오지 않도록).
   */
  header?: ReactNode
  children: ReactNode
}

/** 로그인/회원가입/온보딩 공통 레이아웃 — 중앙 카드 + 브랜드(또는 상단바) */
export function AuthLayout({ title, description, wide, header, children }: AuthLayoutProps) {
  return (
    <div className="flex min-h-screen flex-col bg-surface">
      {header}
      <main
        className={cn(
          'flex flex-1 flex-col items-center px-4',
          // 헤더가 있으면 위쪽 여백을 줄여 카드가 너무 내려가지 않게
          header ? 'py-8 sm:py-10' : 'py-10 sm:py-14',
        )}
      >
        {!header && (
          <Link to="/" className="mb-8 flex items-center gap-2 text-lg font-bold">
            <BrandMark className="h-6 w-6 text-accent" />
            AI 순찰 시스템
          </Link>
        )}
        <div
          className={cn(
            'w-full rounded-card bg-bg p-6 shadow-card ring-1 ring-line sm:p-10',
            wide ? 'max-w-3xl' : 'max-w-md',
          )}
        >
          <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
          {description && <p className="mt-2 text-sm leading-relaxed text-muted">{description}</p>}
          <div className="mt-8">{children}</div>
        </div>
      </main>
    </div>
  )
}

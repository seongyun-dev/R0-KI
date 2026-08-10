import type { ReactNode } from 'react'
import { Breadcrumb, type BreadcrumbItem } from '../ui/Breadcrumb'
import { cn } from '../../lib/cn'

export type PageHeaderProps = {
  breadcrumb: BreadcrumbItem[]
  title: ReactNode
  /** 제목 옆 상태칩 등 */
  aside?: ReactNode
  /** 우측 액션 버튼들 */
  actions?: ReactNode
  className?: string
}

/** 본문 상단 — 브레드크럼 + 제목 + 우측 액션 (와이어프레임 공통) */
export function PageHeader({ breadcrumb, title, aside, actions, className }: PageHeaderProps) {
  return (
    <div className={cn('flex flex-col gap-3', className)}>
      <Breadcrumb items={breadcrumb} />
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
          {aside}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
    </div>
  )
}

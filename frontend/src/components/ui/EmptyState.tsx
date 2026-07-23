import type { ReactNode } from 'react'
import { cn } from '../../lib/cn'

export type EmptyStateProps = {
  title: string
  description?: string
  action?: ReactNode
  className?: string
}

export function EmptyState({ title, description, action, className }: EmptyStateProps) {
  return (
    <div className={cn('flex flex-col items-center gap-2 rounded-card-sm bg-surface px-6 py-12 text-center', className)}>
      <p className="text-sm font-semibold">{title}</p>
      {description && <p className="text-sm text-muted">{description}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  )
}

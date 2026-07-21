import { Fragment } from 'react'
import { Link } from 'react-router-dom'
import { cn } from '../../lib/cn'

export type BreadcrumbItem = { label: string; to?: string }

export type BreadcrumbProps = {
  items: BreadcrumbItem[]
  className?: string
}

/** `Dashboard > 순찰관리 > P-1042` */
export function Breadcrumb({ items, className }: BreadcrumbProps) {
  return (
    <nav aria-label="경로" className={cn('text-sm text-muted', className)}>
      <ol className="flex flex-wrap items-center gap-1.5">
        {items.map((item, i) => {
          const last = i === items.length - 1
          return (
            <Fragment key={`${item.label}-${i}`}>
              {i > 0 && <li aria-hidden>›</li>}
              <li>
                {item.to && !last ? (
                  <Link to={item.to} className="transition-colors hover:text-fg">
                    {item.label}
                  </Link>
                ) : (
                  <span aria-current={last ? 'page' : undefined} className={cn(last && 'font-semibold text-fg')}>
                    {item.label}
                  </span>
                )}
              </li>
            </Fragment>
          )
        })}
      </ol>
    </nav>
  )
}

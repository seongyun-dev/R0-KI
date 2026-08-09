import { forwardRef, type SelectHTMLAttributes } from 'react'
import { cn } from '../../lib/cn'
import { ChevronDownIcon } from '../icons'

export type SelectProps = {
  invalid?: boolean
} & SelectHTMLAttributes<HTMLSelectElement>

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { invalid, className, children, ...rest },
  ref,
) {
  return (
    <span className={cn('relative inline-flex w-full', className)}>
      <select
        ref={ref}
        aria-invalid={invalid || undefined}
        className={cn(
          'w-full cursor-pointer appearance-none rounded-control bg-bg py-3 pl-4 pr-10 text-sm ring-1 ring-line transition-shadow',
          'focus:outline-none focus:ring-2 focus:ring-accent',
          invalid && 'ring-danger focus:ring-danger',
        )}
        {...rest}
      >
        {children}
      </select>
      <ChevronDownIcon className="pointer-events-none absolute right-3.5 top-1/2 -translate-y-1/2 text-muted" />
    </span>
  )
})

import { forwardRef, type InputHTMLAttributes, type ReactNode } from 'react'
import { cn } from '../../lib/cn'

export type CheckboxProps = {
  label: ReactNode
} & InputHTMLAttributes<HTMLInputElement>

export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(function Checkbox(
  { label, className, ...rest },
  ref,
) {
  return (
    <label className={cn('inline-flex cursor-pointer items-start gap-2.5 text-sm', className)}>
      <input
        ref={ref}
        type="checkbox"
        className="mt-0.5 h-4 w-4 flex-none cursor-pointer rounded-sm accent-accent"
        {...rest}
      />
      <span>{label}</span>
    </label>
  )
})

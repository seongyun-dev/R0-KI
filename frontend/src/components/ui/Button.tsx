import type { AnchorHTMLAttributes, ButtonHTMLAttributes, ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { cn } from '../../lib/cn'
import { ArrowRightIcon, ArrowUpRightIcon } from '../icons'
import { Spinner } from './Spinner'

export type ButtonVariant = 'accent' | 'dark' | 'light' | 'outline' | 'ghost'
export type ButtonSize = 'sm' | 'md' | 'lg'

type BaseProps = {
  variant?: ButtonVariant
  size?: ButtonSize
  /** 프로토타입 필 버튼의 화살표 뱃지 */
  withArrow?: 'right' | 'up-right'
  loading?: boolean
  className?: string
  children: ReactNode
}
type AsButton = BaseProps & { to?: undefined } & ButtonHTMLAttributes<HTMLButtonElement>
type AsLink = BaseProps & { to: string } & Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'href'>
export type ButtonProps = AsButton | AsLink

const surface: Record<ButtonVariant, string> = {
  accent: 'bg-gradient-to-br from-accent-light to-accent-deep text-white',
  dark: 'bg-ink text-white',
  light: 'bg-surface text-fg',
  outline: 'bg-transparent text-fg ring-1 ring-line',
  ghost: 'bg-transparent text-fg hover:bg-surface',
}
const badgeSurface: Record<ButtonVariant, string> = {
  accent: 'bg-white text-ink',
  dark: 'bg-white text-ink',
  light: 'bg-ink text-white',
  outline: 'bg-ink text-white',
  ghost: 'bg-ink text-white',
}
const plainSize: Record<ButtonSize, string> = {
  sm: 'px-4 py-2 text-xs',
  md: 'px-6 py-3.5 text-sm',
  lg: 'px-7 py-4 text-base',
}
const arrowSize: Record<ButtonSize, string> = {
  sm: 'p-1 pl-4 text-xs',
  md: 'p-1.5 pl-5 text-sm',
  lg: 'p-2 pl-6 text-base',
}
const badgeSize: Record<ButtonSize, string> = {
  sm: 'h-7 w-7',
  md: 'h-9 w-9',
  lg: 'h-10 w-10',
}

export function Button(props: ButtonProps) {
  const {
    variant = 'dark',
    size = 'md',
    withArrow,
    loading,
    className,
    children,
    ...rest
  } = props

  const classes = cn(
    'group inline-flex items-center justify-center gap-2.5 rounded-pill font-semibold transition-transform duration-300 ease-snap',
    'hover:scale-105 disabled:pointer-events-none disabled:opacity-50',
    surface[variant],
    withArrow ? arrowSize[size] : plainSize[size],
    className,
  )

  const Arrow = withArrow === 'up-right' ? ArrowUpRightIcon : ArrowRightIcon
  const content = (
    <>
      {loading && <Spinner />}
      {children}
      {withArrow && (
        <span
          aria-hidden
          className={cn('grid flex-none place-items-center rounded-pill', badgeSurface[variant], badgeSize[size])}
        >
          <Arrow
            className={cn(
              'transition-transform duration-300 ease-snap',
              withArrow === 'right' ? 'group-hover:translate-x-0.5' : 'group-hover:-translate-y-0.5 group-hover:translate-x-0.5',
            )}
          />
        </span>
      )}
    </>
  )

  if ('to' in props && props.to !== undefined) {
    const { to: _to, ...anchorRest } = rest as Omit<AsLink, keyof BaseProps>
    void _to
    return (
      <Link to={props.to} className={classes} {...anchorRest}>
        {content}
      </Link>
    )
  }
  const buttonRest = rest as Omit<AsButton, keyof BaseProps>
  return (
    <button type="button" disabled={loading || buttonRest.disabled} className={classes} {...buttonRest}>
      {content}
    </button>
  )
}

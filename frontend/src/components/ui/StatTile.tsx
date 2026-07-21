import type { ReactNode } from 'react'
import { cn } from '../../lib/cn'

export type StatTileProps = {
  value: ReactNode
  label: string
  /** 증감 표시 — 예: { text: '전주 +8%', direction: 'up' } */
  delta?: { text: string; direction?: 'up' | 'down' | 'neutral' }
  tone?: 'light' | 'dark'
  className?: string
}

const deltaClass = {
  up: 'text-success',
  down: 'text-danger',
  neutral: 'text-muted',
}

export function StatTile({ value, label, delta, tone = 'light', className }: StatTileProps) {
  return (
    <div
      className={cn(
        'rounded-card-sm p-5',
        tone === 'dark' ? 'bg-card text-white' : 'bg-bg ring-1 ring-line shadow-soft',
        className,
      )}
    >
      <p className="font-mono text-3xl font-bold tabular">{value}</p>
      <p className={cn('mt-1 text-sm', tone === 'dark' ? 'text-subtle' : 'text-muted')}>{label}</p>
      {delta && (
        <p className={cn('mt-1.5 font-mono text-xs font-semibold tabular', deltaClass[delta.direction ?? 'neutral'])}>
          {delta.direction === 'up' && '▲ '}
          {delta.direction === 'down' && '▼ '}
          {delta.text}
        </p>
      )}
    </div>
  )
}

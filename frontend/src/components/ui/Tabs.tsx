import { cn } from '../../lib/cn'

export type TabItem = { value: string; label: string }

export type TabsProps = {
  items: TabItem[]
  value: string
  onChange: (value: string) => void
  className?: string
}

export function Tabs({ items, value, onChange, className }: TabsProps) {
  return (
    <div role="tablist" className={cn('inline-flex gap-1 rounded-pill bg-surface p-1', className)}>
      {items.map((item) => {
        const active = item.value === value
        return (
          <button
            key={item.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(item.value)}
            className={cn(
              'rounded-pill px-4 py-2 text-sm font-semibold transition-colors duration-300 ease-snap',
              active ? 'bg-ink text-white shadow-soft' : 'text-muted hover:text-fg',
            )}
          >
            {item.label}
          </button>
        )
      })}
    </div>
  )
}

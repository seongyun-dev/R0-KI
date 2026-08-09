import type { ReactNode } from 'react'
import { cn } from '../../lib/cn'
import { EmptyState } from './EmptyState'
import { Skeleton } from './Skeleton'

export type Column<T> = {
  key: string
  header: ReactNode
  render: (row: T) => ReactNode
  align?: 'left' | 'center' | 'right'
  className?: string
}

export type DataTableProps<T> = {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T) => string
  loading?: boolean
  skeletonRows?: number
  emptyMessage?: string
  onRowClick?: (row: T) => void
  className?: string
}

const alignClass = { left: 'text-left', center: 'text-center', right: 'text-right' }

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  loading,
  skeletonRows = 4,
  emptyMessage = '표시할 데이터가 없습니다',
  onRowClick,
  className,
}: DataTableProps<T>) {
  return (
    <div className={cn('overflow-x-auto', className)}>
      <table className="w-full min-w-max border-collapse text-sm">
        <thead>
          <tr className="border-b border-line">
            {columns.map((col) => (
              <th
                key={col.key}
                scope="col"
                className={cn(
                  'whitespace-nowrap px-4 py-3 text-xs font-semibold text-muted',
                  alignClass[col.align ?? 'left'],
                  col.className,
                )}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading
            ? Array.from({ length: skeletonRows }).map((_, i) => (
                <tr key={i} className="border-b border-line">
                  {columns.map((col) => (
                    <td key={col.key} className="px-4 py-4">
                      <Skeleton className="h-4 w-full max-w-32" />
                    </td>
                  ))}
                </tr>
              ))
            : rows.map((row) => (
                <tr
                  key={rowKey(row)}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  className={cn(
                    'border-b border-line transition-colors',
                    onRowClick && 'cursor-pointer hover:bg-surface',
                  )}
                >
                  {columns.map((col) => (
                    <td
                      key={col.key}
                      className={cn(
                        'whitespace-nowrap px-4 py-4',
                        alignClass[col.align ?? 'left'],
                        col.className,
                      )}
                    >
                      {col.render(row)}
                    </td>
                  ))}
                </tr>
              ))}
        </tbody>
      </table>
      {!loading && rows.length === 0 && <EmptyState title={emptyMessage} />}
    </div>
  )
}

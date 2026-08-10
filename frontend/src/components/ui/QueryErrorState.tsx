import { Button } from './Button'
import { EmptyState } from './EmptyState'

export function QueryErrorState({
  error,
  onRetry,
  className,
}: {
  error: Error
  onRetry?: () => void
  className?: string
}) {
  return (
    <EmptyState
      title="데이터를 불러오지 못했습니다"
      description={error.message}
      className={className}
      action={
        onRetry ? (
          <Button variant="outline" size="sm" onClick={onRetry}>
            다시 시도
          </Button>
        ) : undefined
      }
    />
  )
}

import { isRouteErrorResponse, useRouteError } from 'react-router-dom'
import { Button } from '../components/ui'
import { BrandMark } from '../components/icons'

/** 라우트 에러 바운더리 — 렌더/로더 예외 시 표시 */
export default function RouteError() {
  const error = useRouteError()
  const message = isRouteErrorResponse(error)
    ? `${error.status} ${error.statusText}`
    : error instanceof Error
      ? error.message
      : '알 수 없는 오류'

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 bg-surface px-6 text-center">
      <BrandMark className="h-10 w-10 text-accent" />
      <div>
        <h1 className="text-2xl font-bold tracking-tight">문제가 발생했습니다</h1>
        <p className="mt-2 text-sm text-muted">잠시 후 다시 시도해주세요.</p>
        <p className="mt-3 max-w-md break-words font-mono text-xs text-subtle">{message}</p>
      </div>
      <div className="flex flex-wrap justify-center gap-2">
        <Button variant="dark" onClick={() => window.location.reload()}>새로고침</Button>
        <Button variant="outline" to="/app">대시보드로 이동</Button>
      </div>
    </main>
  )
}

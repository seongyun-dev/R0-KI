import { Button } from '../components/ui'
import { BrandMark } from '../components/icons'

/** 404 */
export default function NotFound() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 bg-surface px-6 text-center">
      <BrandMark className="h-10 w-10 text-accent" />
      <div>
        <p className="font-mono text-sm font-bold tracking-widest text-muted">404</p>
        <h1 className="mt-2 text-2xl font-bold tracking-tight">페이지를 찾을 수 없습니다</h1>
        <p className="mt-2 text-sm text-muted">주소가 바뀌었거나 삭제된 화면입니다.</p>
      </div>
      <div className="flex flex-wrap justify-center gap-2">
        <Button variant="dark" to="/app" withArrow="right">대시보드로 이동</Button>
        <Button variant="outline" to="/">랜딩으로</Button>
      </div>
    </main>
  )
}

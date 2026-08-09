import { useNavigate } from 'react-router-dom'
import { CheckIcon } from '../../components/icons'
import { Button, StatusBadge } from '../../components/ui'
import { useAuthStore } from '../auth/useAuthStore'

export type StepDoneProps = {
  complexName: string
  zoneCount: number
}

/** 온보딩 완료 (1x) */
export function StepDone({ complexName, zoneCount }: StepDoneProps) {
  const navigate = useNavigate()
  const login = useAuthStore((s) => s.login)
  return (
    <div className="flex flex-col items-center gap-5 py-6 text-center">
      <span className="grid h-14 w-14 place-items-center rounded-pill bg-ink text-accent-light">
        <CheckIcon className="text-2xl" />
      </span>
      <h2 className="text-xl font-bold">회원가입이 완료되었습니다</h2>
      <p className="text-sm text-muted">
        {complexName} 단지 등록 · 로봇 1대 등록 · 맵 파악 완료
      </p>
      <StatusBadge label={`구역 ${zoneCount}곳 등록 완료`} bracket />
      <Button
        variant="accent"
        withArrow="right"
        className="mt-3"
        onClick={() => {
          // 가입 완료 = 로그인 상태로 진입
          login('new-admin')
          navigate('/app', { replace: true })
        }}
      >
        대시보드로 이동
      </Button>
    </div>
  )
}

import { useEffect, useRef, useState } from 'react'
import { Button, Spinner, StatusBadge } from '../../components/ui'

export type StepMapScanProps = {
  onPrev: () => void
  onNext: () => void
}

/** Step 3/3 — 맵 파악 (로봇 자동 스캔) (1w) */
export function StepMapScan({ onPrev, onNext }: StepMapScanProps) {
  const [phase, setPhase] = useState<'idle' | 'scanning' | 'done'>('idle')
  const timerRef = useRef<number>()

  useEffect(() => () => window.clearTimeout(timerRef.current), [])

  const startScan = () => {
    setPhase('scanning')
    // 진행률(%) 대신 로딩 표시 — 스캔 완료 시 다음 단계 활성화
    timerRef.current = window.setTimeout(() => setPhase('done'), 2500)
  }

  return (
    <div className="flex flex-col gap-6">
      {phase === 'idle' && (
        <div className="flex flex-col items-center gap-4 rounded-card-sm bg-surface px-6 py-12 text-center">
          <p className="text-sm text-muted">
            [맵 파악하기]를 누르면 로봇이 단지를 순찰하며 스스로 맵을 그립니다
          </p>
          <Button variant="accent" size="lg" onClick={startScan}>
            맵 파악하기
          </Button>
        </div>
      )}

      {phase === 'scanning' && (
        <div className="flex flex-col items-center gap-4 rounded-card-sm bg-surface px-6 py-12 text-center">
          <Spinner className="h-6 w-6 text-accent" />
          <p className="font-mono text-sm text-muted">loading..</p>
          <p className="text-xs text-subtle">로봇이 단지를 순찰하며 맵을 그리고 있습니다</p>
        </div>
      )}

      {phase === 'done' && (
        <div className="flex flex-col items-center gap-3 rounded-card-sm bg-success-soft px-6 py-10 text-center">
          <StatusBadge label="파악 완료!" bracket className="text-sm" />
          <p className="text-sm text-muted">맵 파악이 끝나면 구역 지정 단계로 넘어갑니다</p>
        </div>
      )}

      <div className="flex justify-between">
        <Button variant="outline" onClick={onPrev}>← 이전</Button>
        <Button variant="dark" withArrow="right" onClick={onNext} disabled={phase !== 'done'}>
          다음: 구역 지정
        </Button>
      </div>
    </div>
  )
}

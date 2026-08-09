import { useEffect, useRef, useState } from 'react'
import { Button, ProgressBar, StatusBadge } from '../../components/ui'

export type StepMapScanProps = {
  onPrev: () => void
  onNext: () => void
}

const TOTAL_AREA = 18200 // ㎡

/** Step 3/3 — 맵 파악 (로봇 자동 스캔) (1w) */
export function StepMapScan({ onPrev, onNext }: StepMapScanProps) {
  const [phase, setPhase] = useState<'idle' | 'scanning' | 'done'>('idle')
  const [progress, setProgress] = useState(0)
  const timerRef = useRef<number>()

  useEffect(() => () => window.clearInterval(timerRef.current), [])

  const startScan = () => {
    setPhase('scanning')
    setProgress(0)
    timerRef.current = window.setInterval(() => {
      setProgress((p) => {
        const next = Math.min(100, p + 1 + Math.random() * 2)
        if (next >= 100) {
          window.clearInterval(timerRef.current)
          setPhase('done')
        }
        return next
      })
    }, 60)
  }

  const scannedArea = Math.round(((progress / 100) * TOTAL_AREA) / 100) * 100

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
        <div className="flex flex-col gap-4 rounded-card-sm bg-surface px-6 py-10">
          <div className="flex items-center justify-between">
            <StatusBadge label="SCANNING…" bracket />
            <span className="font-mono text-sm tabular text-muted">
              파악된 영역 {scannedArea.toLocaleString()}㎡ / {TOTAL_AREA.toLocaleString()}㎡
            </span>
          </div>
          <ProgressBar value={progress} label="맵 스캔 진행률" />
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

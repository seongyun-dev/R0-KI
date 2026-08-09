import type { FormEvent } from 'react'
import { Button, Field, Input } from '../../components/ui'

export type StepRobotProps = {
  onPrev: () => void
  onNext: () => void
}

/** Step 2/3 — 첫 순찰 로봇 등록 (1v) */
export function StepRobot({ onPrev, onNext }: StepRobotProps) {
  const onSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    onNext()
  }

  return (
    <form className="flex flex-col gap-5" onSubmit={onSubmit}>
      <Field label="로봇 일련번호 입력" htmlFor="ob-serial" required hint="로봇 하단 라벨 표기">
        <Input id="ob-serial" placeholder="예: SN-2026-0001" className="font-mono tabular" required />
      </Field>
      <Field label="로봇명" htmlFor="ob-robot-name" required>
        <Input id="ob-robot-name" placeholder="예: R-01" required />
      </Field>

      <p className="rounded-control bg-surface px-4 py-3 text-sm text-muted">
        담당 구역은 맵 파악이 끝난 뒤 자동으로 지정됩니다
      </p>

      <div className="mt-2 flex justify-between">
        <Button variant="outline" onClick={onPrev}>← 이전</Button>
        <Button type="submit" variant="dark" withArrow="right">
          다음: 맵 파악하기
        </Button>
      </div>
    </form>
  )
}

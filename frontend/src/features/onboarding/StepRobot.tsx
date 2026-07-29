import { useState, type FormEvent } from 'react'
import { robotsApi } from '../../api/services'
import { Button, Field, Input } from '../../components/ui'

export type StepRobotProps = {
  onPrev: () => void
  onNext: (data: { robotId: string | number; serial: string; name: string }) => void
}

/** Step 2/3 — 최초 순찰 로봇 등록 */
export function StepRobot({ onPrev, onNext }: StepRobotProps) {
  const [serial, setSerial] = useState('')
  const [name, setName] = useState('')
  const [nameError, setNameError] = useState<string>()
  const [errorMessage, setErrorMessage] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (isSubmitting) return

    const trimmedName = name.trim()
    if (trimmedName.length < 1 || trimmedName.length > 20) {
      setNameError('로봇 이름은 1~20자로 입력해 주세요.')
      return
    }

    setNameError(undefined)
    setErrorMessage('')
    setIsSubmitting(true)

    try {
      const serialNumber = serial.trim()
      const robot = await robotsApi.create({ name: trimmedName, serialNumber })
      onNext({ robotId: robot.robotId, serial: serialNumber, name: trimmedName })
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '로봇 등록에 실패했습니다.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <form className="flex flex-col gap-5" onSubmit={onSubmit}>
      <Field label="로봇 일련번호 입력" htmlFor="ob-serial" required hint="로봇 하단 라벨 표기">
        <Input
          id="ob-serial"
          value={serial}
          onChange={(event) => setSerial(event.target.value)}
          placeholder="예: SN-2026-0001"
          className="font-mono tabular"
          required
        />
      </Field>
      <Field label="로봇명" htmlFor="ob-robot-name" required hint="1~20자 · 직접 지어주세요" error={nameError}>
        <Input
          id="ob-robot-name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="예: R-01"
          maxLength={20}
          required
        />
      </Field>

      <p className="rounded-control bg-surface px-4 py-3 text-sm text-muted">
        해당 구역은 맵 파악이 끝난 뒤 자동으로 지정됩니다.
      </p>

      {errorMessage && (
        <p role="alert" className="text-sm text-danger">
          {errorMessage}
        </p>
      )}

      <div className="mt-2 flex justify-between">
        <Button type="button" variant="outline" onClick={onPrev} disabled={isSubmitting}>
          ← 이전
        </Button>
        <Button type="submit" variant="dark" withArrow="right" loading={isSubmitting}>
          다음: 맵 파악하기
        </Button>
      </div>
    </form>
  )
}

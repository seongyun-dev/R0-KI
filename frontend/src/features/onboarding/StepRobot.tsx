import { useState, type FormEvent } from 'react'
import { Button, Field, Input } from '../../components/ui'
import { robotsApi } from '../../api/services'

export type StepRobotProps = {
  onPrev: () => void
  /** 입력한 일련번호·로봇명을 상위로 전달 (등록 API 저장용) */
  onNext: (data: { serial: string; name: string }) => void
}

/** Step 2/3 — 첫 순찰 로봇 등록 (1v) */
export function StepRobot({ onPrev, onNext }: StepRobotProps) {
  const [serial, setSerial] = useState('')
  const [name, setName] = useState('')
  const [nameError, setNameError] = useState<string>()
  const [errorMessage, setErrorMessage] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  const onSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (isSubmitting) return

    const trimmedName = name.trim()
    // 로봇 이름 검증: 1~20자, 앞뒤 공백 제거, 빈 값 불가 (중복은 백엔드에서 최종 검증)
    if (trimmedName.length < 1 || trimmedName.length > 20) {
      setNameError('로봇 이름은 1~20자로 입력해주세요')
      return
    }
    setNameError(undefined)
    setErrorMessage('')
    setIsSubmitting(true)

    try {
      const serialNumber = serial.trim()
      await robotsApi.create({ name: trimmedName, serialNumber })
      onNext({ serial: serialNumber, name: trimmedName })
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : '로봇 등록 중 오류가 발생했습니다.',
      )
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
          onChange={(e) => setSerial(e.target.value)}
          placeholder="예: SN-2026-0001"
          className="font-mono tabular"
          required
        />
      </Field>
      <Field label="로봇명" htmlFor="ob-robot-name" required hint="1~20자 · 직접 지어주세요" error={nameError}>
        <Input
          id="ob-robot-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="예: R-01"
          maxLength={20}
          required
        />
      </Field>

      <p className="rounded-control bg-surface px-4 py-3 text-sm text-muted">
        담당 구역은 맵 파악이 끝난 뒤 자동으로 지정됩니다
      </p>

      {errorMessage && (
        <p role="alert" className="text-sm text-danger">
          {errorMessage}
        </p>
      )}

      <div className="mt-2 flex justify-between">
        <Button type="button" variant="outline" onClick={onPrev}>← 이전</Button>
        <Button type="submit" variant="dark" withArrow="right" loading={isSubmitting}>
          다음: 맵 파악하기
        </Button>
      </div>
    </form>
  )
}

import { useState, type FormEvent } from 'react'
import { robotsApi } from '../../api/services'

export type StepRobotProps = {
  onPrev: () => void
  onNext: (data: { robotId: string | number; serial: string; name: string }) => void
}

/** Step 2/3 — 최초 순찰 로봇 등록. R0Kiauth 시안 pRobot */
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
    <form onSubmit={onSubmit}>
      <div className="au-row">
        <label className="au-lab" htmlFor="ob-serial">로봇 일련번호 입력<span className="req">*</span></label>
        <input
          className="au-in num"
          id="ob-serial"
          value={serial}
          onChange={(event) => setSerial(event.target.value)}
          placeholder="예: SN-2026-0001"
          required
        />
        <p className="au-help">로봇 하단 라벨 표기</p>
      </div>

      <div className={nameError ? 'au-row bad' : 'au-row'}>
        <label className="au-lab" htmlFor="ob-robot-name">로봇명<span className="req">*</span></label>
        <input
          className={nameError ? 'au-in bad' : 'au-in'}
          id="ob-robot-name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="예: R-01"
          maxLength={20}
          required
        />
        {nameError ? (
          <p className="au-err" role="alert">{nameError}</p>
        ) : (
          <p className="au-help">1~20자 · 직접 지어주세요</p>
        )}
      </div>

      <div className="au-note">
        <svg viewBox="0 0 24 24"><path d="M12 8h.01M11 12h1v5h1" /><circle cx="12" cy="12" r="9" /></svg>
        <span>해당 구역은 <b>맵 파악이 끝난 뒤 자동으로 지정</b>됩니다.</span>
      </div>

      {errorMessage && (
        <p role="alert" className="au-err">{errorMessage}</p>
      )}

      <div className="au-act">
        <button type="button" className="btn btn-s btn-add" onClick={onPrev} disabled={isSubmitting}>
          <svg viewBox="0 0 24 24"><path d="M19 12H6M13 5l-7 7 7 7" /></svg>
          이전
        </button>
        <span className="grow" />
        {/* 등록을 마치면 대시보드로 간다 — 지도는 다음 로그인 때 이어서 등록한다.
            "다음: 맵 파악하기"로 두면 실제 이동과 문구가 어긋난다. */}
        <button type="submit" className="btn btn-p btn-add" disabled={isSubmitting}>
          {isSubmitting ? '등록 중…' : '로봇 등록 완료'}
          <svg viewBox="0 0 24 24"><path d="m5 13 4.5 4.5L19 7" /></svg>
        </button>
      </div>
    </form>
  )
}

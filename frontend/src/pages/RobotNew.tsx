import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { R0KiShell } from '../components/layout/R0KiShell'
import { useCreateRobot } from '../features/robots/useRobot'

/* R0-Ki 로봇 등록 (1j) — 로봇 목록의 [로봇 등록] 진입점.
   입력은 일련번호·로봇명 둘뿐이라 좁은 카드 하나로 중앙에 세운다.

   필드·검증은 온보딩 StepRobot 과 맞춘다(일련번호 = 로봇 하단 라벨, 로봇명 1~20자).
   같은 로봇을 등록하는 화면이 둘인데 규칙이 다르면 사용자가 혼란스럽다. */

const NAME_MAX = 20

export default function RobotNew() {
  const navigate = useNavigate()
  const createRobot = useCreateRobot()
  const serialRef = useRef<HTMLInputElement>(null)
  const doneTimer = useRef<number>()

  const [serial, setSerial] = useState('')
  const [name, setName] = useState('')
  const [serialError, setSerialError] = useState<string>()
  const [nameError, setNameError] = useState<string>()
  const [errorMessage, setErrorMessage] = useState<string>()
  const [toast, setToast] = useState<string>()

  // 등록 성공 토스트를 잠깐 보여준 뒤 목록으로 — 언마운트되면 타이머를 정리한다
  useEffect(() => () => window.clearTimeout(doneTimer.current), [])

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (createRobot.isPending) return

    const serialNumber = serial.trim()
    const trimmedName = name.trim()

    setSerialError(undefined)
    setNameError(undefined)
    setErrorMessage(undefined)

    if (!serialNumber) {
      setSerialError('로봇 일련번호를 입력해 주세요.')
      serialRef.current?.focus()
      return
    }
    if (trimmedName.length < 1 || trimmedName.length > NAME_MAX) {
      setNameError(`로봇 이름은 1~${NAME_MAX}자로 입력해 주세요.`)
      return
    }

    try {
      await createRobot.mutateAsync({ serialNumber, name: trimmedName })
      setToast('로봇이 등록되었습니다')
      doneTimer.current = window.setTimeout(() => navigate('/app/robots'), 1000)
    } catch (reason) {
      setErrorMessage(reason instanceof Error ? reason.message : '로봇 등록에 실패했습니다.')
    }
  }

  return (
    <R0KiShell active="robots">
      <div className="pcol">
        <div className="pagehead">
          <div>
            <div className="crumb">
              <Link to="/app">대시보드</Link><i>›</i>
              <Link to="/app/robots">로봇 관리</Link><i>›</i>
              <b>로봇 등록</b>
            </div>
            <div className="ptitle">로봇 등록</div>
          </div>
          <div className="headtools">
            <Link to="/app/robots" className="btn btn-s btn-add">
              <svg viewBox="0 0 24 24"><path d="M19 12H6M13 5l-7 7 7 7" /></svg>
              목록으로
            </Link>
          </div>
        </div>

        <div className="rnwrap">
          <div className="glass g2 rncard">
            <form className="rnform" onSubmit={onSubmit} noValidate>
              <div className={serialError ? 'au-row bad' : 'au-row'}>
                <label className="au-lab" htmlFor="rn-serial">
                  로봇 일련번호<span className="req">*</span>
                </label>
                <input
                  className={serialError ? 'au-in num bad' : 'au-in num'}
                  id="rn-serial"
                  ref={serialRef}
                  value={serial}
                  onChange={(event) => {
                    setSerial(event.target.value)
                    setSerialError(undefined)
                  }}
                  placeholder="예: SN-2026-0001"
                  autoComplete="off"
                  required
                />
                {serialError ? (
                  <p className="au-err" role="alert">{serialError}</p>
                ) : (
                  <p className="au-help">로봇 하단 라벨 표기</p>
                )}
              </div>

              <div className={nameError ? 'au-row bad' : 'au-row'}>
                <label className="au-lab" htmlFor="rn-name">
                  로봇명<span className="req">*</span>
                </label>
                <input
                  className={nameError ? 'au-in bad' : 'au-in'}
                  id="rn-name"
                  value={name}
                  onChange={(event) => {
                    setName(event.target.value)
                    setNameError(undefined)
                  }}
                  placeholder="예: R-02"
                  maxLength={NAME_MAX}
                  required
                />
                {nameError ? (
                  <p className="au-err" role="alert">{nameError}</p>
                ) : (
                  <p className="au-help">1~{NAME_MAX}자 · 관제 화면에 표시되는 이름입니다</p>
                )}
              </div>

              {errorMessage && (
                <p className="au-err" role="alert">{errorMessage}</p>
              )}

              <div className="au-act">
                <button
                  type="button"
                  className="btn btn-s"
                  onClick={() => navigate('/app/robots')}
                  disabled={createRobot.isPending}
                >
                  취소
                </button>
                <span className="grow" />
                <button type="submit" className="btn btn-p btn-add" disabled={createRobot.isPending}>
                  {createRobot.isPending ? '등록 중…' : '등록 완료'}
                  <svg viewBox="0 0 24 24"><path d="M5 12h13M12 5l7 7-7 7" /></svg>
                </button>
              </div>
            </form>
          </div>
        </div>
      </div>

      {/* 토스트 — 목록 화면과 같은 문법 */}
      <div className={`toast${toast ? ' on' : ''}`} role="status" aria-live="polite">
        <svg viewBox="0 0 24 24"><path d="M4 12.5 9.5 18 20 6.5" /></svg>
        <span>{toast}</span>
      </div>
    </R0KiShell>
  )
}

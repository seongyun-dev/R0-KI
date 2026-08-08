import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { R0KiShell } from '../components/layout/R0KiShell'
import { useCreateResident } from '../features/residents/useResidents'

/* R0-Ki 입주민 등록 — 로봇 등록(RobotNew)과 같은 카드 폼 문법.

   차량은 여기서 같이 넣을 수 있지만 필수는 아니다(등록 후 상세에서 추가 가능).
   다만 차량이 없으면 불법주차 SMS 대상이 되지 않으므로 안내 문구로 알려 준다. */

const NAME_MAX = 50
const PHONE_PATTERN = /^[0-9-]+$/

export default function ResidentNew() {
  const navigate = useNavigate()
  const createResident = useCreateResident()
  const nameRef = useRef<HTMLInputElement>(null)
  const doneTimer = useRef<number>()

  const [name, setName] = useState('')
  const [phoneNumber, setPhoneNumber] = useState('')
  const [buildingNumber, setBuildingNumber] = useState('')
  const [unitNumber, setUnitNumber] = useState('')
  // 차량은 번호만 입력받는다 — disabledVehicle 은 이 화면에서 다루지 않으므로 항상 false 로 보낸다
  const [vehicles, setVehicles] = useState<string[]>([''])

  const [fieldError, setFieldError] = useState<Record<string, string>>({})
  const [errorMessage, setErrorMessage] = useState<string>()
  const [toast, setToast] = useState<string>()

  useEffect(() => () => window.clearTimeout(doneTimer.current), [])

  const updateVehicle = (index: number, licensePlate: string) => {
    setVehicles((prev) => prev.map((value, i) => (i === index ? licensePlate : value)))
  }

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (createResident.isPending) return

    const trimmedName = name.trim()
    const trimmedPhone = phoneNumber.trim()
    const trimmedBuilding = buildingNumber.trim()
    const trimmedUnit = unitNumber.trim()
    // 빈 줄은 "안 쓴 칸"으로 보고 버린다 — 차량 없이 등록하는 것도 허용한다
    const filledVehicles = vehicles
      .map((licensePlate) => licensePlate.trim())
      .filter((licensePlate) => licensePlate !== '')
      .map((licensePlate) => ({ licensePlate, disabledVehicle: false }))

    const errors: Record<string, string> = {}
    if (!trimmedName) errors.name = '이름을 입력해 주세요.'
    if (!trimmedPhone) errors.phone = '연락처를 입력해 주세요.'
    else if (!PHONE_PATTERN.test(trimmedPhone)) {
      errors.phone = '연락처는 숫자와 하이픈만 입력할 수 있습니다.'
    }
    if (!trimmedBuilding) errors.building = '동을 입력해 주세요.'
    if (!trimmedUnit) errors.unit = '호수를 입력해 주세요.'

    const plates = filledVehicles.map((vehicle) => vehicle.licensePlate)
    if (new Set(plates).size !== plates.length) {
      errors.vehicles = '같은 차량 번호를 두 번 입력했습니다.'
    }

    setFieldError(errors)
    setErrorMessage(undefined)
    if (Object.keys(errors).length > 0) {
      if (errors.name) nameRef.current?.focus()
      return
    }

    try {
      const created = await createResident.mutateAsync({
        name: trimmedName,
        phoneNumber: trimmedPhone,
        buildingNumber: trimmedBuilding,
        unitNumber: trimmedUnit,
        vehicles: filledVehicles,
      })
      setToast('입주민이 등록되었습니다')
      doneTimer.current = window.setTimeout(
        () => navigate(`/app/residents/${created.residentId}`),
        1000,
      )
    } catch (reason) {
      setErrorMessage(reason instanceof Error ? reason.message : '입주민 등록에 실패했습니다.')
    }
  }

  return (
    <R0KiShell active="residents">
      <div className="pcol">
        <div className="pagehead">
          <div>
            <div className="crumb">
              <Link to="/app">대시보드</Link><i>›</i>
              <Link to="/app/residents">입주민 관리</Link><i>›</i>
              <b>입주민 등록</b>
            </div>
            <div className="ptitle">입주민 등록</div>
          </div>
          <div className="headtools">
            <Link to="/app/residents" className="btn btn-s btn-add">
              <svg viewBox="0 0 24 24"><path d="M19 12H6M13 5l-7 7 7 7" /></svg>
              목록으로
            </Link>
          </div>
        </div>

        <div className="rnwrap">
          <div className="glass g2 rncard">
            <form className="rnform" onSubmit={onSubmit} noValidate>
              <div className={fieldError.name ? 'au-row bad' : 'au-row'}>
                <label className="au-lab" htmlFor="rs-name">
                  이름<span className="req">*</span>
                </label>
                <input
                  className={fieldError.name ? 'au-in bad' : 'au-in'}
                  id="rs-name"
                  ref={nameRef}
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="예: 김입주"
                  maxLength={NAME_MAX}
                  required
                />
                {fieldError.name && <p className="au-err" role="alert">{fieldError.name}</p>}
              </div>

              <div className={fieldError.phone ? 'au-row bad' : 'au-row'}>
                <label className="au-lab" htmlFor="rs-phone">
                  연락처<span className="req">*</span>
                </label>
                <input
                  className={fieldError.phone ? 'au-in num bad' : 'au-in num'}
                  id="rs-phone"
                  value={phoneNumber}
                  onChange={(event) => setPhoneNumber(event.target.value)}
                  placeholder="예: 010-1234-5678"
                  autoComplete="off"
                  required
                />
                {fieldError.phone ? (
                  <p className="au-err" role="alert">{fieldError.phone}</p>
                ) : (
                  <p className="au-help">불법주차 감지 시 이 번호로 안내 문자가 발송됩니다</p>
                )}
              </div>

              <div className={fieldError.building ? 'au-row bad' : 'au-row'}>
                <label className="au-lab" htmlFor="rs-building">
                  동<span className="req">*</span>
                </label>
                <input
                  className={fieldError.building ? 'au-in num bad' : 'au-in num'}
                  id="rs-building"
                  value={buildingNumber}
                  onChange={(event) => setBuildingNumber(event.target.value)}
                  placeholder="예: 101"
                  autoComplete="off"
                  required
                />
                {fieldError.building && (
                  <p className="au-err" role="alert">{fieldError.building}</p>
                )}
              </div>

              <div className={fieldError.unit ? 'au-row bad' : 'au-row'}>
                <label className="au-lab" htmlFor="rs-unit">
                  호수<span className="req">*</span>
                </label>
                <input
                  className={fieldError.unit ? 'au-in num bad' : 'au-in num'}
                  id="rs-unit"
                  value={unitNumber}
                  onChange={(event) => setUnitNumber(event.target.value)}
                  placeholder="예: 1502"
                  autoComplete="off"
                  required
                />
                {fieldError.unit && <p className="au-err" role="alert">{fieldError.unit}</p>}
              </div>

              <div className={fieldError.vehicles ? 'au-row bad' : 'au-row'}>
                <span className="au-lab">등록 차량</span>
                {/* .au-in 은 width:100% 라 그냥 두면 입력칸이 행을 다 먹고 옆 버튼이 찌그러진다.
                    입력칸만 늘어나게 하고(flex:1+min-width:0) 나머지는 제 너비를 지킨다. */}
                {vehicles.map((licensePlate, index) => (
                  <div
                    key={index}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 'var(--s2)',
                      marginBottom: 'var(--s2)',
                    }}
                  >
                    <input
                      className="au-in num"
                      value={licensePlate}
                      onChange={(event) => updateVehicle(index, event.target.value)}
                      placeholder="예: 12가3456"
                      aria-label={`차량 번호 ${index + 1}`}
                      autoComplete="off"
                      style={{ flex: '1 1 auto', minWidth: 0 }}
                    />
                    {vehicles.length > 1 && (
                      <button
                        type="button"
                        className="btn btn-s"
                        onClick={() =>
                          setVehicles((prev) => prev.filter((_, i) => i !== index))
                        }
                        style={{ flex: 'none', whiteSpace: 'nowrap' }}
                      >
                        삭제
                      </button>
                    )}
                  </div>
                ))}
                <button
                  type="button"
                  className="btn btn-s btn-add"
                  onClick={() => setVehicles((prev) => [...prev, ''])}
                  style={{ whiteSpace: 'nowrap' }}
                >
                  <svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14" /></svg>
                  차량 추가
                </button>
                {fieldError.vehicles ? (
                  <p className="au-err" role="alert">{fieldError.vehicles}</p>
                ) : (
                  <p className="au-help">
                    비워 두고 등록할 수 있지만, 차량이 없으면 불법주차 안내 문자 대상이 되지 않습니다
                  </p>
                )}
              </div>

              {errorMessage && <p className="au-err" role="alert">{errorMessage}</p>}

              <div className="au-act">
                <button
                  type="button"
                  className="btn btn-s"
                  onClick={() => navigate('/app/residents')}
                  disabled={createResident.isPending}
                >
                  취소
                </button>
                <span className="grow" />
                <button
                  type="submit"
                  className="btn btn-p btn-add"
                  disabled={createResident.isPending}
                >
                  {createResident.isPending ? '등록 중…' : '등록 완료'}
                  <svg viewBox="0 0 24 24"><path d="M5 12h13M12 5l7 7-7 7" /></svg>
                </button>
              </div>
            </form>
          </div>
        </div>
      </div>

      <div className={`toast${toast ? ' on' : ''}`} role="status" aria-live="polite">
        <svg viewBox="0 0 24 24"><path d="M4 12.5 9.5 18 20 6.5" /></svg>
        <span>{toast}</span>
      </div>
    </R0KiShell>
  )
}

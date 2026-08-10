import { useEffect, useState, type FormEvent } from 'react'
import { authApi } from '../../api/services'
import { useComplexSearch } from '../auth/useComplexSearch'
import { formatPhone } from '../../lib/formatters'
import type { SignUpRequest } from '../../api/contracts'
import { openPostcodeSearch } from '../../lib/daumPostcode'
import {
  isPasswordValid,
  PASSWORD_VALIDATION_MESSAGE,
} from '../auth/passwordPolicy'

export type StepAccountProps = {
  onNext: (data: SignUpRequest) => void
  isSubmitting: boolean
  errorMessage?: string
}

type EmailNotice = {
  kind: 'success' | 'error'
  target: 'send' | 'verify'
  message: string
}

// 목업 중복 데이터 — 서버 연동 시 API 교체 (Signup 과 동일 기준)
const normalize = (s: string) => s.trim().replace(/\s+/g, '')
const isEmailValid = (value: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim())

/** Step 1/3 — 계정·단지 (1u). R0Kiauth 시안 pNew: 이미 등록된 단지면 안내 배너 */
export function StepAccount({ onNext, isSubmitting, errorMessage }: StepAccountProps) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [passwordError, setPasswordError] = useState<string>()
  const [passwordConfirm, setPasswordConfirm] = useState('')
  const [passwordConfirmError, setPasswordConfirmError] = useState<string>()
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [email, setEmail] = useState('')
  const [emailCode, setEmailCode] = useState('')
  const [isEmailCodeSent, setIsEmailCodeSent] = useState(false)
  const [isEmailVerified, setIsEmailVerified] = useState(false)
  const [isSendingEmail, setIsSendingEmail] = useState(false)
  const [isVerifyingEmail, setIsVerifyingEmail] = useState(false)
  const [emailNotice, setEmailNotice] = useState<EmailNotice>()
  const [zipcode, setZipcode] = useState('')
  const [complexName, setComplexName] = useState('')
  const [address, setAddress] = useState('')

  // 기존 단지 감지 — 입력 디바운스 후 단지 검색, 이름이 정확히 일치하면 분기 배너
  const [aptQuery, setAptQuery] = useState('')
  useEffect(() => {
    const t = setTimeout(() => setAptQuery(complexName), 400)
    return () => clearTimeout(t)
  }, [complexName])
  const { data: candidates } = useComplexSearch(aptQuery, {
    enabled: normalize(aptQuery).length >= 2,
  })
  const matched = candidates?.find((c) => normalize(c.name) === normalize(complexName))

  const onSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (isSubmitting) {
      return
    }
    if (!isPasswordValid(password)) {
      setPasswordError(PASSWORD_VALIDATION_MESSAGE)
      return
    }
    setPasswordError(undefined)

    if (password !== passwordConfirm) {
      setPasswordConfirmError('비밀번호가 일치하지 않습니다.')
      return
    }

    setPasswordConfirmError(undefined)
    if (!isEmailVerified) {
      setEmailNotice({
        kind: 'error',
        target: isEmailCodeSent ? 'verify' : 'send',
        message: '이메일 인증을 완료해주세요.',
      })
      return
    }

    const request: SignUpRequest = {
      username: username.trim(),
      password,
      name,
      phoneNumber: phone,
      email: email.trim(),
      apartment: {
        name: complexName,
        postalCode: zipcode,
        address,
      },
    }
    onNext(request)
  }

  const handleEmailChange = (value: string) => {
    setEmail(value)
    setEmailCode('')
    setIsEmailCodeSent(false)
    setIsEmailVerified(false)
    setEmailNotice(undefined)
  }

  const handleSendEmail = async () => {
    const normalizedEmail = email.trim()
    if (!isEmailValid(normalizedEmail) || isSendingEmail) return

    setIsSendingEmail(true)
    setEmailCode('')
    setIsEmailCodeSent(false)
    setIsEmailVerified(false)
    setEmailNotice(undefined)

    try {
      const response = await authApi.sendEmailVerification({ email: normalizedEmail })
      setIsEmailCodeSent(true)
      setEmailNotice({ kind: 'success', target: 'send', message: response.message })
    } catch (error) {
      setEmailNotice({
        kind: 'error',
        target: 'send',
        message: error instanceof Error ? error.message : '이메일 인증번호 발송에 실패했습니다.',
      })
    } finally {
      setIsSendingEmail(false)
    }
  }

  const handleVerifyEmail = async () => {
    if (emailCode.length !== 6 || isVerifyingEmail) return

    setIsVerifyingEmail(true)
    setEmailNotice(undefined)

    try {
      const response = await authApi.verifyEmail({
        email: email.trim(),
        code: emailCode,
      })
      setIsEmailVerified(true)
      setEmailNotice({ kind: 'success', target: 'verify', message: response.message })
    } catch (error) {
      setIsEmailVerified(false)
      setEmailNotice({
        kind: 'error',
        target: 'verify',
        message: error instanceof Error ? error.message : '이메일 인증에 실패했습니다.',
      })
    } finally {
      setIsVerifyingEmail(false)
    }
  }

  const handlePostcodeSearch = async () => {
    try {
      await openPostcodeSearch(({ postalCode, apartmentName, roadAddress }) => {
        setZipcode(postalCode)
        setComplexName(apartmentName)
        setAddress(roadAddress)
      })
    } catch (error) {
      const message =
        error instanceof Error ? error.message : '주소 검색 중 오류가 발생했습니다.'
      alert(message)
    }
  }

  return (
    <form onSubmit={onSubmit}>
      <div className="au-sec">계정</div>
      <div className="au-grid">
        <div className="au-row">
          <label className="au-lab" htmlFor="ob-id">아이디<span className="req">*</span></label>
          <input
            className="au-in"
            id="ob-id"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="아이디 입력"
            pattern="[A-Za-z0-9]{4,20}"
            autoComplete="username"
            required
          />
          <p className="au-help">4~20자 영문/숫자 · 중복 여부는 가입 시 서버에서 확인합니다.</p>
        </div>

        <div className={passwordError ? 'au-row bad' : 'au-row'}>
          <label className="au-lab" htmlFor="ob-pw">비밀번호<span className="req">*</span></label>
          <input
            className={passwordError ? 'au-in bad' : 'au-in'}
            id="ob-pw"
            type="password"
            value={password}
            onChange={(e) => {
              const value = e.target.value

              setPassword(value)
              setPasswordError(undefined)

              if (passwordConfirm) {
                setPasswordConfirmError(
                  value === passwordConfirm
                    ? undefined
                    : '비밀번호가 일치하지 않습니다.',
                )
              }
            }}
            placeholder="비밀번호 입력"
            autoComplete="new-password"
            minLength={8}
            pattern="(?=.*[A-Za-z])(?=.*\d)(?=.*[^A-Za-z\d\s]).{8,}"
            required
          />
          <p className="au-help">8자 이상, 영문+숫자+특수문자 조합</p>
          {passwordError && <p className="au-err" role="alert">{passwordError}</p>}
        </div>

        <div className="au-row">
          <label className="au-lab" htmlFor="ob-name">이름<span className="req">*</span></label>
          <input
            className="au-in"
            id="ob-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="이름 입력"
            required
          />
        </div>

        <div className={passwordConfirmError ? 'au-row bad' : 'au-row'}>
          <label className="au-lab" htmlFor="ob-pw-confirm">
            비밀번호 확인<span className="req">*</span>
          </label>

          <input
            className={passwordConfirmError ? 'au-in bad' : 'au-in'}
            id="ob-pw-confirm"
            type="password"
            value={passwordConfirm}
            onChange={(e) => {
              const value = e.target.value
              setPasswordConfirm(value)

              if (!value) {
                setPasswordConfirmError(undefined)
                return
              }

              setPasswordConfirmError(
                password === value
                  ? undefined
                  : '비밀번호가 일치하지 않습니다.',
              )
            }}
            placeholder="비밀번호 다시 입력"
            autoComplete="new-password"
            required
          />

          {passwordConfirm && !passwordConfirmError && (
            <p className="au-help">비밀번호가 일치합니다.</p>
          )}

          {passwordConfirmError && (
            <p className="au-err" role="alert">
              {passwordConfirmError}
            </p>
          )}
        </div>

        <div className="au-row">
          <label className="au-lab" htmlFor="ob-phone">전화번호<span className="req">*</span></label>
          <input
            className="au-in num"
            id="ob-phone"
            type="tel"
            value={phone}
            onChange={(e) => setPhone(formatPhone(e.target.value))}
            placeholder="010-1234-5678"
            required
          />
        </div>

        <div className="au-row">
          <label className="au-lab" htmlFor="ob-email">
            이메일<span className="req">*</span>
          </label>

          <div className="au-pair">
            <input
              className="au-in"
              id="ob-email"
              type="email"
              value={email}
              onChange={(e) => handleEmailChange(e.target.value)}
              placeholder="example@email.com"
              autoComplete="email"
              disabled={isSendingEmail || isVerifyingEmail}
              required
            />

            <button
              type="button"
              className="btn btn-s"
              onClick={handleSendEmail}
              disabled={!isEmailValid(email) || isSendingEmail || isEmailVerified}
            >
              {isSendingEmail ? '발송 중…' : '인증'}
            </button>
          </div>

          <p className="au-help">
            본인 확인을 위한 이메일 인증이 필요합니다.
          </p>
          {emailNotice?.target === 'send' && emailNotice.message && (
            <p
              className={emailNotice.kind === 'success' ? 'au-ok' : 'au-err'}
              role={emailNotice.kind === 'success' ? 'status' : 'alert'}
            >
              {emailNotice.message}
            </p>
          )}
        </div>

        {isEmailCodeSent && (
          <div className="au-row au-email-code">
            <label className="au-lab" htmlFor="ob-email-code">
              인증번호<span className="req">*</span>
            </label>

            <div className="au-pair">
              <input
                className="au-in num"
                id="ob-email-code"
                value={emailCode}
                onChange={(e) => {
                  setEmailCode(e.target.value.replace(/\D/g, '').slice(0, 6))
                  if (emailNotice?.target === 'verify') setEmailNotice(undefined)
                }}
                placeholder="6자리 숫자"
                inputMode="numeric"
                pattern="[0-9]{6}"
                maxLength={6}
                autoComplete="one-time-code"
                disabled={isVerifyingEmail || isEmailVerified}
                required
              />

              <button
                type="button"
                className="btn btn-s"
                onClick={handleVerifyEmail}
                disabled={emailCode.length !== 6 || isVerifyingEmail || isEmailVerified}
              >
                {isEmailVerified ? '완료' : isVerifyingEmail ? '확인 중…' : '확인'}
              </button>
            </div>

            {emailNotice?.target === 'verify' && emailNotice.message && (
              <p
                className={emailNotice.kind === 'success' ? 'au-ok' : 'au-err'}
                role={emailNotice.kind === 'success' ? 'status' : 'alert'}
              >
                {emailNotice.message}
              </p>
            )}
          </div>
        )}
      </div>

      <div className="au-sec">아파트단지 정보</div>
      <div className="au-grid">
        {/* 우편번호 찾기가 우편번호·도로명주소·아파트 이름을 함께 채우므로 그 순서로 배치 */}
        <div className="full">
          <div className="au-row">
            <label className="au-lab" htmlFor="ob-zip">우편번호<span className="req">*</span></label>
            <div className="au-pair">
              <input
                className="au-in num"
                id="ob-zip"
                value={zipcode}
                onChange={(e) => setZipcode(e.target.value.replace(/\D/g, '').slice(0, 5))}
                placeholder="우편번호"
                required
              />
              <button type="button" className="btn btn-s" onClick={handlePostcodeSearch}>
                우편번호 찾기
              </button>
            </div>
          </div>
        </div>

        <div className="full">
          <div className="au-row">
            <label className="au-lab" htmlFor="ob-addr">도로명주소<span className="req">*</span></label>
            <input
              className="au-in"
              id="ob-addr"
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              placeholder="도로명주소 입력"
              required
            />
          </div>
        </div>

        <div className="full">
          <div className="au-row">
            <label className="au-lab" htmlFor="ob-complex">아파트 이름<span className="req">*</span></label>
            <input
              className="au-in"
              id="ob-complex"
              value={complexName}
              onChange={(e) => setComplexName(e.target.value)}
              placeholder="예: 가온아파트"
              required
            />
            <p className="au-help">이미 등록된 단지를 입력하면 소속 회원 가입으로 전환됩니다</p>
            {/* 이미 등록된 단지 안내 — 별도 가입 폼으로 보내지 않는다.
                서버가 isNewApartment=false 로 응답하면 소속 회원 가입이 그대로 완료된다. */}
            {matched && (
              <div className="au-branch">
                <span className="ic">
                  <svg viewBox="0 0 24 24"><path d="M12 8h.01M11 12h1v5h1" /><circle cx="12" cy="12" r="9" /></svg>
                </span>
                <span className="bd">
                  <span className="bt">이미 등록된 단지입니다</span>
                  <span className="bs">
                    <b>{matched.name}</b> 은(는) 이미 관리자가 등록한 단지입니다. 이대로 진행하면
                    로봇·맵 등록 없이 소속 회원으로 가입이 완료됩니다.
                  </span>
                </span>
              </div>
            )}
          </div>
        </div>
      </div>

      {errorMessage && (
        <p role="alert" className="au-err">{errorMessage}</p>
      )}

      <div className="au-act">
        <span className="grow" />
        {/* 이 버튼으로 계정 등록이 끝난다(POST /api/auth/signup).
            로봇·지도는 이어지는 단계라 여기서 "다음"이 아니라 "완료"로 끊는다. */}
        <button
          type="submit"
          className="btn btn-p btn-add"
          disabled={isSubmitting || !isEmailVerified}
        >
          {isSubmitting ? '등록 중…' : '회원가입 완료'}
          <svg viewBox="0 0 24 24"><path d="m5 13 4.5 4.5L19 7" /></svg>
        </button>
      </div>

    </form>
  )
}

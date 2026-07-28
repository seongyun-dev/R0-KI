import { useState, type FormEvent } from 'react'
import { Button, Field, Input } from '../../components/ui'
import { formatPhone } from '../../lib/formatters'
import type { SignUpRequest } from '../../api/contracts'
import { openPostcodeSearch } from '../../lib/daumPostcode'
export type StepAccountProps = {
  onNext: (data: SignUpRequest) => void
  isSubmitting: boolean
  errorMessage?: string
}

/** Step 1/3 — 계정·단지 (1u) */
export function StepAccount({ onNext, isSubmitting, errorMessage }: StepAccountProps) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [zipcode, setZipcode] = useState('')
  const [complexName, setComplexName] = useState('')
  const [address, setAddress] = useState('')
  const onSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (isSubmitting) {
      return
    }
    const request: SignUpRequest = {
      username,
      password,
      name,
      phoneNumber: phone,
      apartment: {
        name: complexName,
        postalCode: zipcode,
        address,
      },
    }
    onNext(request)
  }


  const handlePostcodeSearch = () => {
    try {
      openPostcodeSearch(
        ({
          postalCode,
          apartmentName,
          roadAddress,
        }) => {
          setZipcode(postalCode)
          setComplexName(apartmentName)
          setAddress(roadAddress)
        },
      )
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : '주소 검색 중 오류가 발생했습니다.'

      alert(message)
    }
  }

  return (
    <form className="flex flex-col gap-5" onSubmit={onSubmit}>
      <section className="flex flex-col gap-5">
        <h2 className="border-b border-line pb-2 text-sm font-bold text-muted">계정</h2>
        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="아이디" htmlFor="ob-id" required hint="4~20자 영문/숫자">
            <Input id="ob-id" placeholder="아이디 입력" pattern="[A-Za-z0-9]{4,20}" type="text" value={username} onChange={(e) => setUsername(e.target.value)} required />
          </Field>
          <Field label="비밀번호" htmlFor="ob-pw" required hint="8자 이상, 영문+숫자+특수문자 조합">
            <Input id="ob-pw" type="password" value={password} onChange={(e)=> setPassword(e.target.value)} placeholder="비밀번호 입력" autoComplete="new-password" minLength={8} required />
          </Field>
          <Field label="이름" htmlFor="ob-name" required>
            <Input id="ob-name" type="text" value={name} onChange={(e)=>setName(e.target.value)} placeholder="이름 입력" required />
          </Field>
          <Field label="전화번호" htmlFor="ob-phone" required className="sm:col-span-2">
            <Input
              id="ob-phone"
              type="tel"
              value={phone}
              onChange={(e) => setPhone(formatPhone(e.target.value))}
              placeholder="010-1234-5678"
              className="font-mono tabular"
              required
            />
          </Field>
        </div>
      </section>

      <section className="flex flex-col gap-5">
        <h2 className="border-b border-line pb-2 text-sm font-bold text-muted">신규 아파트단지 정보</h2>
        <Field label="우편번호" htmlFor="ob-zip" required>
          <div className="flex gap-2">
            <Input
              id="ob-zip"
              value={zipcode}
              onChange={(e) => setZipcode(e.target.value.replace(/\D/g, '').slice(0, 5))}
              placeholder="우편번호"
              className="max-w-40 font-mono tabular"
              required
            />
            <Button type="button" variant="outline" className="flex-none" onClick={handlePostcodeSearch}>
              우편번호 찾기
            </Button>
          </div>
        </Field>
        <Field label="아파트 이름" htmlFor="ob-complex" required>
          <Input
            id="ob-complex"
            value={complexName}
            onChange={(e) => setComplexName(e.target.value)}
            placeholder="예: 가온아파트"
            required
          />
        </Field>
        <Field label="도로명주소" htmlFor="ob-addr" required>
          <Input type="text" value={address} onChange={(e)=> setAddress(e.target.value)} id="ob-addr" placeholder="도로명주소 입력" required />
        </Field>
      </section>

      <div className="mt-2 flex items-center justify-between gap-4">
        {errorMessage ? (
          <p role="alert" className="text-sm text-red-600">
            {errorMessage}
          </p>
        ) : (
          <span />
        )}

        <Button
          type="submit"
          variant="dark"
          disabled={isSubmitting}
          withArrow="right"
        >
          {isSubmitting ? '가입 처리 중...' : '다음: 로봇 등록'}
        </Button>
      </div>
    </form>
  )
}

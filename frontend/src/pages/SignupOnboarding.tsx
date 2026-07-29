import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { R0KiAuthShell } from '../components/layout/R0KiAuthShell'
import { StepAccount } from '../features/onboarding/StepAccount'
import { StepMapScan } from '../features/onboarding/StepMapScan'
import { StepRobot } from '../features/onboarding/StepRobot'
import { StepZones } from '../features/onboarding/StepZones'
import { useRegisteredMap } from '../features/onboarding/useRegisteredMap'
import { authApi } from '../api/services'
import { useAuthStore } from '../features/auth/useAuthStore'

type Phase = 'account' | 'robot' | 'scan' | 'zones'

// 화면별 제목/설명 (R0Kiauth 시안 문구)
const copy: Record<Phase, { title: string; description: string }> = {
  account: {
    title: '회원가입',
    description: '계정과 단지 정보를 함께 등록합니다. 이미 등록된 단지라면 소속 회원 가입으로 넘어갑니다.',
  },
  robot: {
    title: '첫 순찰 로봇 등록',
    description:
      '로봇 본체에 표기된 일련번호로 이 단지의 첫 로봇을 등록합니다. 등록된 로봇이 다음 단계에서 단지 맵을 직접 파악합니다.',
  },
  scan: {
    title: '로봇이 단지 맵을 파악합니다',
    description:
      '[맵 파악하기]를 누르면 로봇이 단지를 순찰하며 스스로 맵을 그립니다. 지도를 직접 올릴 필요가 없어요.',
  },
  zones: {
    title: '구역을 드래그해서 등록해주세요',
    description:
      '로봇이 보낸 맵 데이터를 화면에 그려드려요. 구역 유형을 선택한 뒤 맵 위를 드래그하면 해당 구역이 등록됩니다 (✕로 삭제).',
  },
}

// 스텝 인디케이터 [① 계정·단지][② 로봇 등록][③ 맵 등록]
const stepIndex: Record<Phase, number> = { account: 0, robot: 1, scan: 2, zones: 2 }
// 카드 폭 — 폼은 mid, 맵 편집은 map
const cardWidth: Record<Phase, string> = { account: 'w-mid', robot: 'w-mid', scan: 'w-map', zones: 'w-map' }

const STEP_LABELS = ['계정·단지', '로봇 등록', '맵 등록']

/** Stepper (.au-stp) — R0Kiauth 시안 신규 공용 컴포넌트 */
function AuthStepper({ current }: { current: number }) {
  return (
    <ol className="au-stp">
      {STEP_LABELS.map((label, i) => (
        <li key={label} className={i < current ? 'done' : i === current ? 'on' : ''}>
          <span className="st">
            <span className="n">
              {i < current ? <svg viewBox="0 0 24 24"><path d="m5 13 4.5 4.5L19 7" /></svg> : i + 1}
            </span>
            {label}
          </span>
          {i < STEP_LABELS.length - 1 && <span className="bar" />}
        </li>
      ))}
    </ol>
  )
}

/** 회원가입 · 최초 가입자 온보딩 (1u→1v→1w→1y) — R0Kiauth 시안 pNew→pRobot→pMap */
export default function SignupOnboarding() {
  const navigate = useNavigate()
  const login = useAuthStore((state) => state.login)
  const [phase, setPhase] = useState<Phase>('account')
  // 로봇 등록 입력값(이름) — 서버 연동 시 최종 제출(등록 API)로 전송. 일련번호는 등록 API 연동 시 함께 캡처
  const [robotId, setRobotId] = useState<string | number>()
  const [mapId, setMapId] = useState<string | number>()
  const setRegisteredZones = useRegisteredMap((s) => s.setZones)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string>()
  const setMapContext = useAuthStore((s) => s.setMapContext)

  return (
    <R0KiAuthShell>
      <div className="au-wrap">
        <div className={`glass g2 au-card ${cardWidth[phase]}`}>
          <h1 className="au-h">{copy[phase].title}</h1>
          <p className="au-sub">{copy[phase].description}</p>
          <AuthStepper current={stepIndex[phase]} />
          <div className="au-gap" />

          {phase === 'account' && (
            <>
              <StepAccount
                isSubmitting={isSubmitting}
                errorMessage={errorMessage}
                onNext={async (data) => {
                  setIsSubmitting(true)
                  setErrorMessage(undefined)

                  try {
                    const response = await authApi.signUp(data)
                    login(data.username, response.accessToken)
                    // 이미 등록된 단지면 소속 회원으로 가입 완료 → 바로 대시보드
                    if (response.isNewApartment) {
                      setPhase('robot')
                    } else {
                      navigate('/app', { replace: true })
                    }
                  } catch (error) {
                    setErrorMessage(
                      error instanceof Error ? error.message : '회원가입에 실패했습니다.',
                    )
                  } finally {
                    setIsSubmitting(false)
                  }
                }}
              />
              <div className="au-foot">
                이미 등록된 단지 소속이신가요? <Link to="/signup">일반 회원가입 →</Link>
                {' '}·{' '}
                <Link to="/login">로그인 →</Link>
              </div>
            </>
          )}
          {phase === 'robot' && (
            <StepRobot
              onPrev={() => setPhase('account')}
              onNext={({ robotId: registeredRobotId }) => {
                setRobotId(registeredRobotId)
                setMapContext({ robotId: registeredRobotId })
                setPhase('scan')
              }}
            />
          )}
          {phase === 'scan' && robotId != null && (
            <StepMapScan
              robotId={robotId}
              onPrev={() => setPhase('robot')}
              onNext={(completedMapId) => {
                setMapId(completedMapId)
                setMapContext({ mapId: completedMapId, robotId })
                setPhase('zones')
              }}
            />
          )}
          {phase === 'zones' && mapId != null && (
            <StepZones
              mapId={mapId}
              onPrev={() => setPhase('scan')}
              onComplete={(zones) => {
                setRegisteredZones(zones) // 대시보드 지도에 반영
                // 가입 완료 → 바로 대시보드 (StepAccount 에서 이미 로그인됨)
                navigate('/app', { replace: true })
              }}
            />
          )}
        </div>
      </div>
    </R0KiAuthShell>
  )
}

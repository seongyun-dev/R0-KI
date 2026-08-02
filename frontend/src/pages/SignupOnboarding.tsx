import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { R0KiAuthShell } from '../components/layout/R0KiAuthShell'
import { StepAccount } from '../features/onboarding/StepAccount'
import { StepMapScan } from '../features/onboarding/StepMapScan'
import { StepRobot } from '../features/onboarding/StepRobot'
import { StepZones } from '../features/onboarding/StepZones'
import { useRegisteredMap } from '../features/onboarding/useRegisteredMap'
import { SignupDoneModal } from '../features/onboarding/SignupDoneModal'
import {
  useOnboardingProgress,
  type OnboardingPhase,
} from '../features/onboarding/useOnboardingProgress'
import { authApi } from '../api/services'
import { useAuthStore } from '../features/auth/useAuthStore'

type Phase = 'account' | OnboardingPhase

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
  const currentLoginId = useAuthStore((state) => state.loginId)
  const onboardingOwner = useOnboardingProgress((state) => state.ownerLoginId)
  const storedPhase = useOnboardingProgress((state) => state.phase)
  const ownsStoredProgress =
    currentLoginId != null && onboardingOwner === currentLoginId
  const phase: Phase = ownsStoredProgress && storedPhase ? storedPhase : 'account'
  const storedRobotId = useOnboardingProgress((state) => state.robotId)
  const storedMapId = useOnboardingProgress((state) => state.mapId)
  const robotId = ownsStoredProgress ? storedRobotId : null
  const mapId = ownsStoredProgress ? storedMapId : null
  const beginOnboarding = useOnboardingProgress((state) => state.begin)
  const moveToRobot = useOnboardingProgress((state) => state.moveToRobot)
  const moveToScan = useOnboardingProgress((state) => state.moveToScan)
  const moveToZones = useOnboardingProgress((state) => state.moveToZones)
  const resetOnboarding = useOnboardingProgress((state) => state.reset)
  const setRegisteredZones = useRegisteredMap((s) => s.setZones)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string>()
  const setMapContext = useAuthStore((s) => s.setMapContext)
  // 계정 등록을 마친 직후 — 완료 모달을 띄우고, 이어서 할지 여기서 고른다
  const [signedUpId, setSignedUpId] = useState<string>()

  return (
    <R0KiAuthShell bootTagline="관리자 계정 등록을 준비하고 있습니다.">
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
                    // (로봇·지도는 단지 관리자가 이미 등록해 둔 상태)
                    if (response.isNewApartment) {
                      // 계정 등록까지가 이 단계의 끝 — 이어서 할지는 모달에서 고른다
                      setSignedUpId(data.username)
                    } else {
                      resetOnboarding()
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
              {/* 일반 회원가입(/signup)은 front/dev 에서 제거됨 — 가입 경로는 온보딩 하나로 통일 */}
              <div className="au-foot">
                이미 계정이 있으신가요? <Link to="/login">로그인 →</Link>
              </div>
            </>
          )}
          {phase === 'robot' && (
            <StepRobot
              onPrev={() => navigate('/login')}
              onNext={({ robotId: registeredRobotId }) => {
                setMapContext({ robotId: registeredRobotId })
                /* 로봇 등록을 마치면 곧바로 맵 등록으로 넘어간다.
                   지도가 없으면 관제 화면이 비어 있어, 여기서 끊지 않고 이어서 받는다. */
                moveToScan(registeredRobotId)
              }}
            />
          )}
          {phase === 'scan' && robotId != null && (
            <StepMapScan
              robotId={robotId}
              onPrev={moveToRobot}
              onNext={(completedMapId) => {
                setMapContext({ mapId: completedMapId, robotId })
                moveToZones(completedMapId)
              }}
            />
          )}
          {phase === 'zones' && mapId != null && (
            <StepZones
              mapId={mapId}
              onPrev={() => {
                if (robotId != null) moveToScan(robotId)
              }}
              onComplete={(zones) => {
                setRegisteredZones(zones) // 대시보드 지도에 반영
                resetOnboarding()
                // 가입 완료 → 바로 대시보드 (StepAccount 에서 이미 로그인됨)
                navigate('/app', { replace: true })
              }}
            />
          )}
        </div>
      </div>

      {/* 계정 등록 직후 — 이어서 로봇을 등록할지, 나중에 할지 고른다.
          나중에 하기를 골라도 계정은 남고, 다음 로그인 때 이 단계로 돌아온다. */}
      <SignupDoneModal
        open={signedUpId != null}
        onContinue={() => {
          if (signedUpId) beginOnboarding(signedUpId)
          setSignedUpId(undefined)
        }}
        onLater={() => {
          setSignedUpId(undefined)
          navigate('/login', { replace: true })
        }}
      />
    </R0KiAuthShell>
  )
}

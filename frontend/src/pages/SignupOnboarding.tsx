import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Stepper } from '../components/ui'
import { SiteHeader } from '../components/layout/SiteHeader'
import { AuthLayout } from '../features/auth/AuthLayout'
import { useClock } from '../features/landing/useClock'
import { StepAccount } from '../features/onboarding/StepAccount'
import { StepDone } from '../features/onboarding/StepDone'
import { StepMapScan } from '../features/onboarding/StepMapScan'
import { StepRobot } from '../features/onboarding/StepRobot'
import { StepZones } from '../features/onboarding/StepZones'

type Phase = 'account' | 'robot' | 'scan' | 'zones' | 'done'

// 화면별 제목/설명 (docs/screens.md 문구 그대로)
const copy: Record<Phase, { title: string; description?: string }> = {
  account: {
    title: '최초 가입자 등록',
    description: '이 단지의 첫 관리자입니다. 계정과 단지 정보를 함께 등록합니다',
  },
  robot: {
    title: '첫 순찰 로봇 등록',
    description:
      '로봇 본체에 표기된 일련번호로 이 단지의 첫 로봇을 등록합니다. 등록된 로봇이 다음 단계에서 단지 맵을 직접 파악합니다',
  },
  scan: {
    title: '로봇이 단지 맵을 파악합니다',
    description:
      '[맵 파악하기]를 누르면 로봇이 단지를 순찰하며 스스로 맵을 그립니다. 지도를 직접 올릴 필요가 없어요',
  },
  zones: {
    title: '구역을 드래그해서 등록해주세요',
    description:
      '로봇이 보낸 맵 데이터를 화면에 그려드려요. 구역 유형을 선택한 뒤 맵 위를 드래그하면 해당 구역이 등록됩니다 (✕로 삭제)',
  },
  done: { title: '최초 가입자 등록' },
}

// 스텝 인디케이터 [① 계정·단지][② 로봇 등록][③ 맵 등록]
const stepIndex: Record<Phase, number> = { account: 0, robot: 1, scan: 2, zones: 2, done: 3 }

/** 회원가입 · 최초 가입자 온보딩 (1u→1v→1w→1y→1x) */
export default function SignupOnboarding() {
  const clock = useClock()
  const [phase, setPhase] = useState<Phase>('account')
  const [complexName, setComplexName] = useState('가온아파트')
  const [zoneCount, setZoneCount] = useState(0)

  return (
    <AuthLayout
      wide
      title={copy[phase].title}
      description={copy[phase].description}
      header={<SiteHeader plain clock={clock} />}
    >
      <Stepper
        steps={['계정·단지', '로봇 등록', '맵 등록']}
        current={stepIndex[phase]}
        className="mb-8"
      />

      {phase === 'account' && (
        <>
          <StepAccount
            onNext={({ complexName: name }) => {
              setComplexName(name)
              setPhase('robot')
            }}
          />
          <p className="mt-6 border-t border-line pt-5 text-center text-sm text-muted">
            이미 등록된 단지 소속이신가요?{' '}
            <Link to="/signup" className="font-semibold text-fg underline-offset-4 hover:underline">
              일반 회원가입 →
            </Link>
          </p>
        </>
      )}
      {phase === 'robot' && <StepRobot onPrev={() => setPhase('account')} onNext={() => setPhase('scan')} />}
      {phase === 'scan' && <StepMapScan onPrev={() => setPhase('robot')} onNext={() => setPhase('zones')} />}
      {phase === 'zones' && (
        <StepZones
          onPrev={() => setPhase('scan')}
          onComplete={(n) => {
            setZoneCount(n)
            setPhase('done')
          }}
        />
      )}
      {phase === 'done' && <StepDone complexName={complexName} zoneCount={zoneCount} />}
    </AuthLayout>
  )
}

import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { PageHeader } from '../components/layout/PageHeader'
import { QrCodeIcon } from '../components/icons'
import { Button, Card, Field, Input, useToast } from '../components/ui'
import { useCreateRobot } from '../features/robots/useRobot'

/** 로봇 등록 (1j) — QR 스캔 + 등록번호 직접입력 */
export default function RobotNew() {
  const navigate = useNavigate()
  const toast = useToast()
  const createRobot = useCreateRobot()
  const [manual, setManual] = useState(false)
  const [regNo, setRegNo] = useState('')
  const [name, setName] = useState('')

  const onSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (!regNo) {
      setManual(true)
      toast('등록번호 또는 일련번호를 입력해주세요')
      return
    }
    try {
      // 백엔드 등록 요청은 name·serialNumber만 받는다.
      await createRobot.mutateAsync({
        serialNumber: regNo,
        name,
      })
      toast('✓ 로봇이 등록되었습니다')
      navigate('/app/robots')
    } catch (reason) {
      toast(reason instanceof Error ? reason.message : '로봇 등록에 실패했습니다')
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        breadcrumb={[
          { label: 'Dashboard', to: '/app' },
          { label: '로봇관리', to: '/app/robots' },
          { label: '로봇 등록' },
        ]}
        title="로봇 등록"
      />

      <Card className="p-5 sm:p-8">
        <form className="flex flex-col gap-6" onSubmit={onSubmit}>
          {/* QR 스캔 영역 */}
          <div className="flex flex-col items-center gap-4 rounded-card-sm bg-surface px-6 py-10 text-center">
            <span className="grid h-28 w-28 place-items-center rounded-card-sm bg-bg ring-1 ring-line">
              <QrCodeIcon className="text-5xl text-muted" />
            </span>
            <div>
              <p className="text-sm font-semibold">로봇 본체의 QR 코드를 스캔하세요</p>
              <p className="mt-1 text-xs text-muted">카메라에 QR 코드를 비추면 등록번호가 자동 입력됩니다</p>
            </div>
            <Button variant="outline" size="sm" onClick={() => setManual(true)}>
              등록번호 직접입력
            </Button>
          </div>

          {manual && (
            <Field label="등록번호" htmlFor="rn-regno" required hint="예: RB-2024-01">
              <Input
                id="rn-regno"
                value={regNo}
                onChange={(e) => setRegNo(e.target.value)}
                placeholder="RB-2024-01"
                className="font-mono tabular"
                required
              />
            </Field>
          )}

          <Field label="로봇명" htmlFor="rn-name" required>
            <Input
              id="rn-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="예: R-02"
              required
            />
          </Field>

          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => navigate(-1)}>취소</Button>
            <Button type="submit" variant="accent" withArrow="right" loading={createRobot.isPending}>
              등록 완료
            </Button>
          </div>
        </form>
      </Card>
    </div>
  )
}

import { useEffect, useState } from 'react'
import { Button, Drawer, Field, Input, Select } from '../../components/ui'
import type { Robot, RobotStatus } from '../../types/domain'

export type RobotEditDrawerProps = {
  open: boolean
  robot: Robot
  onClose: () => void
  onSave: (patch: { name: string; status: RobotStatus }) => void | Promise<void>
}

const STATUS_OPTIONS: RobotStatus[] = ['순찰중', '대기', '충전중', '오류', '오프라인']

/** 로봇 수정 드로어 (1k) — 저장 시 Toast */
export function RobotEditDrawer({ open, robot, onClose, onSave }: RobotEditDrawerProps) {
  const [name, setName] = useState(robot.name)
  const [status, setStatus] = useState<RobotStatus>(
    STATUS_OPTIONS.includes(robot.status as RobotStatus) ? (robot.status as RobotStatus) : '대기',
  )
  const [isSaving, setSaving] = useState(false)

  // 열 때마다 현재 로봇 값으로 초기화
  useEffect(() => {
    if (!open) return
    setName(robot.name)
    setStatus(STATUS_OPTIONS.includes(robot.status as RobotStatus) ? (robot.status as RobotStatus) : '대기')
  }, [open, robot])

  return (
    <Drawer open={open} onClose={onClose} title="로봇 수정">
      <form
        className="flex flex-col gap-5"
        onSubmit={async (e) => {
          e.preventDefault()
          setSaving(true)
          try {
            await onSave({ name, status })
            onClose()
          } finally {
            setSaving(false)
          }
        }}
      >
        <Field label="로봇명" htmlFor="rb-name">
          <Input id="rb-name" value={name} onChange={(e) => setName(e.target.value)} required />
        </Field>
        <Field label="상태" htmlFor="rb-status">
          <Select id="rb-status" value={status} onChange={(e) => setStatus(e.target.value as RobotStatus)}>
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </Select>
        </Field>
        <Button type="submit" variant="dark" className="mt-2" loading={isSaving}>저장</Button>
      </form>
    </Drawer>
  )
}

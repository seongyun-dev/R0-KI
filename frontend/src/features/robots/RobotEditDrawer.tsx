import { useEffect, useState } from 'react'
import { Button, Drawer, Field, Input } from '../../components/ui'
import type { Robot } from '../../types/domain'

export type RobotEditDrawerProps = {
  open: boolean
  robot: Robot
  onClose: () => void
  onSave: (patch: { name: string }) => void | Promise<void>
}

/** 로봇 수정 드로어 (1k) — 로봇명만 수정. 상태는 시스템이 관리. 저장 시 Toast */
export function RobotEditDrawer({ open, robot, onClose, onSave }: RobotEditDrawerProps) {
  const [name, setName] = useState(robot.name)
  const [isSaving, setSaving] = useState(false)

  // 열 때마다 현재 로봇 값으로 초기화
  useEffect(() => {
    if (!open) return
    setName(robot.name)
  }, [open, robot])

  return (
    <Drawer open={open} onClose={onClose} title="로봇 수정">
      <form
        className="flex flex-col gap-5"
        onSubmit={async (e) => {
          e.preventDefault()
          setSaving(true)
          try {
            await onSave({ name })
            onClose()
          } finally {
            setSaving(false)
          }
        }}
      >
        <Field label="로봇명" htmlFor="rb-name">
          <Input id="rb-name" value={name} onChange={(e) => setName(e.target.value)} required />
        </Field>
        <Button type="submit" variant="dark" className="mt-2" loading={isSaving}>저장</Button>
      </form>
    </Drawer>
  )
}

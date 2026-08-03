import { useEffect, useState } from 'react'
import { Button, Drawer, Field, Input } from '../../components/ui'
import type { Robot } from '../../types/domain'

export type RobotEditDrawerProps = {
  open: boolean
  robot: Robot
  onClose: () => void
  onSave: (patch: { name: string }) => void | Promise<void>
  // 삭제 핸들러가 주어지면 삭제(위험) 액션을 노출한다.
  onDelete?: () => void | Promise<void>
}

/** 로봇 수정 드로어 (1k) — 로봇명 수정 + 삭제. 상태는 시스템이 관리. 저장/삭제 시 Toast */
export function RobotEditDrawer({ open, robot, onClose, onSave, onDelete }: RobotEditDrawerProps) {
  const [name, setName] = useState(robot.name)
  const [isSaving, setSaving] = useState(false)
  const [isDeleting, setDeleting] = useState(false)
  // 삭제 확인 2단계 (오조작 방지)
  const [confirmDelete, setConfirmDelete] = useState(false)

  /* 열 때와 대상 로봇이 바뀔 때만 초기화한다.
     robot 은 부모가 매 렌더 새로 만드는 객체라({...loaded, ...patch}) 그대로 의존성에
     두면 부모가 다시 그려질 때마다(토스트 타이머 등) 입력 중이던 이름이 되돌아간다. */
  useEffect(() => {
    if (!open) return
    setName(robot.name)
    setConfirmDelete(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, robot.id])

  const handleDelete = async () => {
    if (!onDelete) return
    setDeleting(true)
    try {
      await onDelete()
      onClose()
    } finally {
      setDeleting(false)
    }
  }

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

      {onDelete && (
        <div className="mt-6 border-t border-line pt-5">
          <p className="mb-2 text-xs font-bold tracking-wider text-muted">위험 구역</p>
          {confirmDelete ? (
            <div className="flex flex-col gap-3 rounded-control bg-surface px-4 py-3">
              <p className="text-sm">
                <span className="font-semibold">{robot.name}</span> 로봇을 삭제할까요? 되돌릴 수 없습니다.
              </p>
              <div className="flex justify-end gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setConfirmDelete(false)}
                  disabled={isDeleting}
                >
                  취소
                </Button>
                <Button
                  type="button"
                  variant="dark"
                  size="sm"
                  className="bg-danger text-white hover:bg-danger"
                  loading={isDeleting}
                  onClick={handleDelete}
                >
                  삭제
                </Button>
              </div>
            </div>
          ) : (
            <Button
              type="button"
              variant="outline"
              className="text-danger ring-danger/40 hover:bg-danger/5"
              onClick={() => setConfirmDelete(true)}
            >
              로봇 삭제
            </Button>
          )}
        </div>
      )}
    </Drawer>
  )
}

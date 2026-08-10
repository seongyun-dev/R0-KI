import type { RobotObstacleEvent } from '../../api/contracts'
import { Button, Modal } from '../../components/ui'

export type RobotObstacleAlertModalProps = {
  event: RobotObstacleEvent
  onClose: () => void
}

export function RobotObstacleAlertModal({ event, onClose }: RobotObstacleAlertModalProps) {
  return (
    <Modal open onClose={onClose} title="로봇 장애물 감지" className="ring-2 ring-danger">
      <div className="flex flex-col gap-4">
        <p className="text-sm leading-relaxed">
          로봇 <strong className="font-mono">{event.robotId}</strong>이 장애물을 발견해 정지했습니다.
        </p>
        {event.message && (
          <p className="rounded-control bg-danger-soft px-4 py-3 text-sm">{event.message}</p>
        )}
        {event.direction && (
          <p className="text-sm text-muted">장애물 방향: {event.direction}</p>
        )}
        <div className="flex justify-end">
          <Button variant="dark" onClick={onClose}>확인</Button>
        </div>
      </div>
    </Modal>
  )
}

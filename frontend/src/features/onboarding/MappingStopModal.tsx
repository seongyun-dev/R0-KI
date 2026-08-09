import { R0KiModal } from '../../components/layout/R0KiModal'

export type MappingStopModalProps = {
  open: boolean
  stopping: boolean
  error?: string
  onCancel: () => void
  onConfirm: () => void
}

export function MappingStopModal({
  open,
  stopping,
  error,
  onCancel,
  onConfirm,
}: MappingStopModalProps) {
  const close = () => {
    if (!stopping) onCancel()
  }

  return (
    <R0KiModal open={open} onClose={close} title="맵 생성 종료">
      <p className="mdtext">
        자율 탐색을 종료하고 현재까지 생성된 지도를 저장하시겠습니까?
      </p>

      {error && <p className="pserr" role="alert">{error}</p>}

      <div className="mdact psact">
        <button type="button" className="btn btn-s" onClick={onCancel} disabled={stopping}>
          취소
        </button>
        <button type="button" className="btn btn-stop" onClick={onConfirm} disabled={stopping}>
          {stopping ? '종료 요청 중...' : '맵 생성 종료'}
        </button>
      </div>
    </R0KiModal>
  )
}

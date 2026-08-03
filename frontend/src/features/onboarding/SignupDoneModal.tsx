import { R0KiModal } from '../../components/layout/R0KiModal'

/* 회원가입 완료 모달 (1u+) — 계정 등록 직후.
   계정은 이미 만들어져 있고, 호출측이 이 모달을 띄우기 전에 온보딩 진행 상태를 세운다.
   그래서 여기서는 "닫기"도 로봇 등록 단계로 이어지는 것 외에 다른 길이 없다 —
   로봇·지도가 없는 계정을 관제 화면으로 들여보내지 않기 위해서다. */

export type SignupDoneModalProps = {
  open: boolean
  /** [로봇 등록하러 가기] — 모달을 닫고 로봇 등록 단계로. 닫기(✕·배경·Esc)도 같은 동작 */
  onContinue: () => void
}

export function SignupDoneModal({ open, onContinue }: SignupDoneModalProps) {
  return (
    <R0KiModal open={open} onClose={onContinue} title="회원가입 완료">
      <p className="mdtext">
        계정이 등록되었습니다.<br />
        관제를 시작하려면 <b>순찰 로봇과 단지 지도</b>를 등록해야 합니다.
      </p>

      <div className="au-note">
        <svg viewBox="0 0 24 24"><path d="M12 8h.01M11 12h1v5h1" /><circle cx="12" cy="12" r="9" /></svg>
        <span>등록을 마치지 않고 나가면 <b>다음 로그인 때 이 단계부터</b> 다시 시작합니다.</span>
      </div>

      <div className="mdact">
        <button type="button" className="btn btn-p btn-add" onClick={onContinue}>
          로봇 등록하러 가기
          <svg viewBox="0 0 24 24"><path d="M5 12h13M12 5l7 7-7 7" /></svg>
        </button>
      </div>
    </R0KiModal>
  )
}

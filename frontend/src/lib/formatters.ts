/** 전화번호 자동 하이픈 — 입력 중 "01012345678" → "010-1234-5678" */
export function formatPhone(value: string) {
  const d = value.replace(/\D/g, '').slice(0, 11)
  if (d.length <= 3) return d
  if (d.length <= 7) return `${d.slice(0, 3)}-${d.slice(3)}`
  return `${d.slice(0, 3)}-${d.slice(3, 7)}-${d.slice(7)}`
}

/** 전화번호 가운데 자리 마스킹 — 입주민 목록(서버가 내려주는 maskedPhoneNumber)과 같은 형식.
    "010-1234-5678" → "010-****-5678" */
export function maskPhone(value: string) {
  const d = value.replace(/\D/g, '')
  if (d.length < 8) return value
  const area = d.slice(0, 3)
  const last4 = d.slice(-4)
  return `${area}-****-${last4}`
}

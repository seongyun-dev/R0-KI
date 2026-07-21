export type PasswordStrength = { level: 0 | 1 | 2 | 3; label: string; dots: string }

/** 비밀번호 강도 — 규칙: 8자 이상, 영문+숫자+특수문자 조합 (1t 강도 표시 "●●○ 보통") */
export function passwordStrength(pw: string): PasswordStrength {
  if (!pw) return { level: 0, label: '', dots: '○○○' }
  let score = 0
  if (pw.length >= 8) score++
  if (/[A-Za-z]/.test(pw) && /\d/.test(pw)) score++
  if (/[^A-Za-z0-9]/.test(pw)) score++
  if (score <= 1) return { level: 1, label: '약함', dots: '●○○' }
  if (score === 2) return { level: 2, label: '보통', dots: '●●○' }
  return { level: 3, label: '강함', dots: '●●●' }
}

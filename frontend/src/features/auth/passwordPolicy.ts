export const PASSWORD_PATTERN = /^(?=.*[A-Za-z])(?=.*\d)(?=.*[^A-Za-z\d\s]).{8,}$/
export const PASSWORD_VALIDATION_MESSAGE =
  '비밀번호는 8자 이상이며 영문, 숫자, 특수문자를 포함해야 합니다.'

export function isPasswordValid(password: string) {
  return PASSWORD_PATTERN.test(password)
}

const trimSlash = (value: string) => value.replace(/\/+$/, '')

export const env = {
  apiBaseUrl: trimSlash(import.meta.env.VITE_API_BASE_URL?.trim() ?? ''),
  // 배포 대상 프론트에서는 모든 기능이 실제 API를 사용한다.
  useMocks: false,
  defaultMapId: import.meta.env.VITE_DEFAULT_MAP_ID?.trim() || undefined,
  defaultRobotId: import.meta.env.VITE_DEFAULT_ROBOT_ID?.trim() || undefined,
}

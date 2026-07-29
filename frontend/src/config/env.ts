const trimSlash = (value: string) => value.replace(/\/+$/, '')

export const env = {
  apiBaseUrl: trimSlash(import.meta.env.VITE_API_BASE_URL?.trim() ?? ''),
  // false 로 두면 Stats가 /api/analytics/events/* 실연동
  useMocks: import.meta.env.VITE_USE_MOCKS !== 'false',
  defaultMapId: import.meta.env.VITE_DEFAULT_MAP_ID?.trim() || undefined,
  defaultRobotId: import.meta.env.VITE_DEFAULT_ROBOT_ID?.trim() || undefined,
}

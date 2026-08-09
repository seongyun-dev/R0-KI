const trimSlash = (value: string) => value.replace(/\/+$/, '')

export const env = {
  apiBaseUrl: trimSlash(import.meta.env.VITE_API_BASE_URL?.trim() ?? ''),
  useMocks: import.meta.env.VITE_USE_MOCKS !== 'false',
  defaultMapId: import.meta.env.VITE_DEFAULT_MAP_ID?.trim() || undefined,
  defaultRobotId: import.meta.env.VITE_DEFAULT_ROBOT_ID?.trim() || undefined,
  statsEndpoint: import.meta.env.VITE_STATS_ENDPOINT?.trim() || '/api/statistics',
}

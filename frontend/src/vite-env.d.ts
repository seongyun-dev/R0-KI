/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
  readonly VITE_USE_MOCKS?: string
  readonly VITE_DEFAULT_MAP_ID?: string
  readonly VITE_DEFAULT_ROBOT_ID?: string
  readonly VITE_STATS_ENDPOINT?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

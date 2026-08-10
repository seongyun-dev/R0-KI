import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  // 로컬 개발에서 실서버 API로 붙일 때만 사용 (예: .env.local에 VITE_DEV_API_PROXY=https://<backend>).
  // 운영 도메인/IP는 소스에 하드코딩하지 않고 env로 주입한다(CONTRACTS.md).
  const proxyTarget = env.VITE_DEV_API_PROXY

  return {
    plugins: [react()],
    server: proxyTarget
      ? {
          proxy: {
            '/api': { target: proxyTarget, changeOrigin: true, secure: false },
          },
        }
      : {},
  }
})

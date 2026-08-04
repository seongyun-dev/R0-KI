import { defineConfig } from 'vite'

/* S15P11E103-296 로키 미리보기 단독 빌드 — three.js까지 한 파일로 묶어
   dev 서버 없이 열리는 HTML을 만든다. 확인용 임시 설정. */
export default defineConfig({
  root: __dirname,
  base: './',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    target: 'es2020',
    assetsInlineLimit: 100_000_000,
    cssCodeSplit: false,
    modulePreload: { polyfill: false },
    rollupOptions: { output: { inlineDynamicImports: true } },
  },
})

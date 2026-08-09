/** @type {import('tailwindcss').Config} */
// Tailwind v3. 색 값은 tokens.css와 동일하게 유지할 것(둘 다 진실원천의 사본).
// 투명도 유틸(bg-accent/50)을 쓰려면 리터럴 hex가 필요하므로 여기엔 hex로 둔다.
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: '#ffffff',
        fg: '#111111',
        ink: '#0a0a0a',
        card: '#0d0d10',
        surface: { DEFAULT: '#f2f1ef', 2: '#e7e5e1' },
        line: '#e6e5e2',
        muted: '#8a8a8a',
        subtle: '#b6b6b6',
        'hero-to': '#eceae7',
        accent: {
          DEFAULT: '#e0532a',
          light: '#ff6a3d',
          deep: '#b8431e',
          soft: '#f6d9cb',
        },
        success: { DEFAULT: '#16a34a', soft: '#dcfce7' },
        info: { DEFAULT: '#2563eb', soft: '#dbeafe' },
        warning: { DEFAULT: '#d97706', soft: '#fef3c7' },
        danger: { DEFAULT: '#e5484d', soft: '#fde8e8' },
        online: '#22c55e',
        // 차트 카테고리 색 (tokens.css와 동일)
        chart: { 1: '#2563eb', 2: '#0d9488', 3: '#e0532a', 4: '#7c5cd6' },
      },
      fontFamily: {
        sans: ["'Pretendard Variable'", 'Pretendard', 'system-ui', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      borderRadius: {
        pill: '9999px',
        card: '2rem',
        'card-sm': '1.25rem',
        control: '0.875rem',
      },
      maxWidth: { shell: '88rem' },
      boxShadow: {
        soft: '0 1px 2px rgba(17,17,17,.06)',
        card: '0 8px 24px -12px rgba(17,17,17,.18)',
        pop: '0 25px 50px -12px rgba(0,0,0,.25)',
      },
      transitionTimingFunction: {
        out: 'cubic-bezier(.22,1,.36,1)',
        snap: 'cubic-bezier(.2,.8,.2,1)',
      },
      screens: { sm: '640px', md: '768px', lg: '1024px', xl: '1280px' },
    },
  },
  plugins: [],
}

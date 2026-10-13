import type { Config } from 'tailwindcss'

const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        canvas: '#0B0C0E',
        card: '#121316',
        elevated: '#181A1D',
        hairline: '#232529',
        ink: '#E8E6E1',
        muted: '#8A8D91',
        faint: '#55585C',
        aggressive: '#34D399',
        constructive: '#2DD4BF',
        neutral: '#A1A1AA',
        caution: '#FBBF24',
        defensive: '#F87171',
      },
      fontFamily: {
        sans: ['var(--font-inter)', 'system-ui', 'sans-serif'],
        mono: ['var(--font-mono)', 'ui-monospace', 'monospace'],
      },
      fontSize: {
        display: ['clamp(2.6rem,6vw,4.5rem)', { lineHeight: '1.02', letterSpacing: '-0.03em' }],
      },
    },
  },
  plugins: [],
}
export default config

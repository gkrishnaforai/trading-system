import type { Config } from 'tailwindcss'

const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        canvas: '#FFFFFF',
        card: '#FFFFFF',
        elevated: '#F6F5F2',
        hairline: '#E6E3DC',
        ink: '#0D0C0A',
        muted: '#363330',
        faint: '#57534C',
        accent: '#EA580C',
        aggressive: '#15803D',
        constructive: '#0F766E',
        neutral: '#78716C',
        caution: '#A16207',
        defensive: '#B91C1C',
      },
      fontFamily: {
        sans: ['var(--font-inter)', 'system-ui', 'sans-serif'],
        mono: ['var(--font-mono)', 'ui-monospace', 'monospace'],
      },
      fontSize: {
        display: ['clamp(1.7rem,4vw,2.8rem)', { lineHeight: '1.05', letterSpacing: '-0.03em' }],
      },
    },
  },
  plugins: [],
}
export default config

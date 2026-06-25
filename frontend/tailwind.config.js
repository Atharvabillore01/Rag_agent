/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ida: {
          navy:          '#0D2545',
          'navy-mid':    '#1A3A6B',
          blue:          '#1A56DB',
          'blue-hover':  '#1648C0',
          'blue-light':  '#EBF5FF',
          'blue-pale':   '#F0F7FF',
          saffron:       '#E05D0D',
          'saffron-h':   '#C54F0A',
          'saffron-lt':  '#FFF3ED',
          gold:          '#F5A623',
        },
      },
      fontFamily: {
        display: ['"Plus Jakarta Sans"', 'sans-serif'],
        body:    ['Inter', 'sans-serif'],
      },
      boxShadow: {
        card:       '0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04)',
        'card-h':   '0 4px 16px rgba(0,0,0,0.09), 0 2px 6px rgba(0,0,0,0.05)',
        elevated:   '0 8px 30px rgba(0,0,0,0.10), 0 2px 8px rgba(0,0,0,0.06)',
        'input-f':  '0 0 0 3px rgba(26, 86, 219, 0.18)',
        panel:      '4px 0 24px rgba(0,0,0,0.06)',
      },
      backgroundImage: {
        'ida-grad':    'linear-gradient(135deg, #0D2545 0%, #1A3A6B 60%, #1A56DB 100%)',
        'ida-btn':     'linear-gradient(135deg, #1A56DB 0%, #1648C0 100%)',
        'saffron-btn': 'linear-gradient(135deg, #E05D0D 0%, #C54F0A 100%)',
        'dot-grid':    'radial-gradient(circle, #CBD5E1 1px, transparent 1px)',
      },
      backgroundSize: {
        'dot-sm': '24px 24px',
      },
      animation: {
        'fade-in':   'fadeIn 0.35s ease-out',
        'slide-up':  'slideUp 0.4s ease-out',
        'slide-in':  'slideIn 0.3s ease-out',
        'bounce-d':  'bounceDot 1.4s ease-in-out infinite',
        'pulse-r':   'pulseRing 2s cubic-bezier(0.455,0.03,0.515,0.955) infinite',
        'spin-slow': 'spin 2.5s linear infinite',
        'float':     'float 3s ease-in-out infinite',
      },
      keyframes: {
        fadeIn:    { from: { opacity: '0' }, to: { opacity: '1' } },
        slideUp:   { from: { opacity: '0', transform: 'translateY(18px)' }, to: { opacity: '1', transform: 'translateY(0)' } },
        slideIn:   { from: { opacity: '0', transform: 'translateX(-12px)' }, to: { opacity: '1', transform: 'translateX(0)' } },
        bounceDot: { '0%,80%,100%': { transform: 'scale(0)' }, '40%': { transform: 'scale(1)' } },
        pulseRing: {
          '0%':   { transform: 'scale(0.95)', boxShadow: '0 0 0 0 rgba(26,86,219,0.45)' },
          '70%':  { transform: 'scale(1)',    boxShadow: '0 0 0 8px rgba(26,86,219,0)' },
          '100%': { transform: 'scale(0.95)', boxShadow: '0 0 0 0 rgba(26,86,219,0)' },
        },
        float: {
          '0%,100%': { transform: 'translateY(0px)' },
          '50%':     { transform: 'translateY(-8px)' },
        },
      },
    },
  },
  plugins: [],
}

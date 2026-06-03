/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        cream: '#FEF9F1',
        ink: '#141414',
        prosper: {
          orange: '#FF421C',
          'orange-bright': '#FF671D',
          'blue-deep': '#013653',
          'blue-hero': '#095580',
          'blue-accent': '#0083BC',
        },
        warm: {
          700: '#332E29',
          600: '#514B45',
          500: '#676059',
        },
        border: {
          gray: '#ECEBEB',
          cream: '#E3DED6',
        },
      },
      fontFamily: {
        inter: ['Inter', 'sans-serif'],
        manrope: ['Manrope', 'sans-serif'],
      },
      borderRadius: {
        card: '20px',
        btn: '12px',
        well: '10px',
        pill: '100px',
      },
      boxShadow: {
        card: '0 1px 2px rgba(20,20,20,.04), 0 8px 24px rgba(20,20,20,.06)',
        chip: '0 12px 32px rgba(1,54,83,.18)',
      },
    },
  },
  plugins: [],
}

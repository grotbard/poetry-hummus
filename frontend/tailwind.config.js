/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Sampled from the restaurant's own logo.
        teal: {
          DEFAULT: '#7CC4C4',
          light: '#A5D9D9',
          dark: '#4F9E9E',
          deep: '#2E7373',
        },
        wine: {
          DEFAULT: '#67062F',
          light: '#8E2B52',
          dark: '#4A0421',
        },
        hummus: {
          DEFAULT: '#E8DCA0',
          light: '#F4EDCB',
          dark: '#C9B96E',
        },
        chickpea: '#D9A94C',
        ink: '#2A2026',
      },
      fontFamily: {
        sans: ['Heebo', 'system-ui', 'sans-serif'],
        display: ['Frank Ruhl Libre', 'Heebo', 'serif'],
      },
      boxShadow: {
        plate: '0 18px 40px -18px rgba(42, 32, 38, 0.45)',
      },
    },
  },
  plugins: [],
}

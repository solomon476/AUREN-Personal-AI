/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#f4f6fb',
          100: '#e7ecf6',
          200: '#cbd7ed',
          300: '#9eb8df',
          400: '#6b92ce',
          500: '#4872bd',
          600: '#3457a4',
          700: '#2a4484',
          800: '#25396d',
          900: '#23325a',
          950: '#141d37',
        },
      },
    },
  },
  plugins: [],
}


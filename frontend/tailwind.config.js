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
        obsidian: {
          950: '#06070a',
          900: '#090a0f',
          850: '#0d0f17',
          800: '#121520',
          750: '#181c2b',
          700: '#1f2436',
        },
        champagne: {
          50: '#faf7ef',
          100: '#f3ebd8',
          200: '#e6d4b0',
          300: '#d7ba83',
          400: '#caa35e',
          500: '#be8c42',
          600: '#a37134',
          700: '#83542a',
          800: '#6c4327',
          900: '#5a3823',
          950: '#2c190d',
        },
        auren: {
          bg: '#08090d',
          surface: '#0f1118',
          elevated: '#151822',
          highlight: '#1c202e',
          border: '#1e2333',
          borderSubtle: '#151926',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
      },
      boxShadow: {
        'glow-champagne': '0 0 24px -4px rgba(202, 163, 94, 0.15)',
        'glow-indigo': '0 0 24px -4px rgba(99, 102, 241, 0.2)',
        'subtle-elevation': '0 4px 20px -2px rgba(0, 0, 0, 0.5), 0 0 0 1px rgba(255, 255, 255, 0.05)',
      },
    },
  },
  plugins: [],
}

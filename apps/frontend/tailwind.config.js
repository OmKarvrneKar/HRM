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
        corporate: {
          navy: '#0f2942',
          blue: '#1e3a8a',
          light: '#3b82f6',
          surface: '#f8fafc',
          border: '#e2e8f0',
        },
        brand: {
          primary: '#1e3a8a',
          accent: '#2563eb',
          success: '#10b981',
          warning: '#f59e0b',
          danger: '#ef4444',
          darkBg: '#0f172a',
          darkCard: '#1e293b',
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      }
    },
  },
  plugins: [],
}


/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'card-bg': 'rgba(30, 41, 59, 0.7)',
        'accent': '#3b82f6',
      },
    },
  },
  plugins: [],
}

/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'primary': '#0f1117',
        'secondary': '#1a1d29',
        'tertiary': '#22262f',
        'elevated': '#2a2e3a',
        'accent': {
          'primary': '#3b82f6',
          'secondary': '#8b5cf6',
          'success': '#10b981',
          'warning': '#f59e0b',
          'danger': '#ef4444',
          'info': '#06b6d4',
        },
        'text': {
          'primary': '#f8fafc',
          'secondary': '#cbd5e1',
          'tertiary': '#94a3b8',
          'muted': '#64748b',
        },
      },
      backgroundColor: {
        'glass': 'rgba(26, 29, 41, 0.7)',
        'glass-hover': 'rgba(42, 46, 58, 0.85)',
        'elevated': 'rgba(34, 38, 47, 0.9)',
      },
      boxShadow: {
        'glow-blue': '0 0 20px rgba(59, 130, 246, 0.15)',
        'glow-purple': '0 0 20px rgba(139, 92, 246, 0.15)',
        'glow-green': '0 0 20px rgba(16, 185, 129, 0.15)',
      },
      borderRadius: {
        'sm': '0.5rem',
        'md': '0.75rem',
        'lg': '1rem',
        'xl': '1.5rem',
      },
      transitionDuration: {
        'fast': '150ms',
        'base': '250ms',
        'slow': '350ms',
        'smooth': '500ms',
      },
      fontFamily: {
        'sans': ['Inter', 'system-ui', 'sans-serif'],
        'display': ['Space Grotesk', 'system-ui', 'sans-serif'],
        'mono': ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
    },
  },
  plugins: [],
}

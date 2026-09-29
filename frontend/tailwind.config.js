/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // SCADA dark palette
        bg:        '#0d1117',
        surface:   '#161b22',
        border:    '#30363d',
        text:      '#e6edf3',
        muted:     '#8b949e',
        accent:    '#388bfd',
        success:   '#3fb950',
        warning:   '#d29922',
        danger:    '#f85149',
        // Provenance badge colors
        prov: {
          simulated:   '#1a7f37',  // SIMULATED_LIVE — green
          synthetic:   '#1a60b5',  // SYNTHETIC_HISTORICAL — blue
          ml:          '#7c3aed',  // ML_PREDICTION — purple
          optimizer:   '#c06c00',  // OPTIMIZER_RECOMMENDATION — amber
          demo:        '#b91c1c',  // DEMO_RESULT — red
          field:       '#065f46',  // FIELD_FACT — dark green
          literature:  '#1e40af',  // LITERATURE_ASSUMPTION — dark blue
        },
      },
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', '"Fira Code"', 'monospace'],
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'fade-in': 'fadeIn 0.3s ease-in-out',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0', transform: 'translateY(4px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
}

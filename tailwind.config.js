/** @type {import('tailwindcss').Config} */
// Système de design « Ada » — propre, sobre, inspiration Apple.
// Les couleurs sont adossées à des variables CSS (voir src/index.css) pour que
// les mêmes classes fonctionnent en thème clair ET sombre. Format RGB séparé par
// des espaces → compatible avec l'opacité Tailwind (bg-surface/70, text-ink/60…).
module.exports = {
    darkMode: ['class', '[data-theme="dark"]'],
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            fontFamily: {
                // Police système (SF sur Apple) — fin du sci-fi « Share Tech Mono ».
                sans: ['-apple-system', 'BlinkMacSystemFont', '"SF Pro Text"', '"SF Pro Display"', '"Segoe UI"', 'Roboto', 'Helvetica', 'Arial', 'sans-serif'],
                mono: ['"SF Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', 'monospace'],
            },
            colors: {
                // Tokens sémantiques (clair/sombre via variables CSS)
                bg: 'rgb(var(--c-bg) / <alpha-value>)',
                surface: 'rgb(var(--c-surface) / <alpha-value>)',
                surface2: 'rgb(var(--c-surface-2) / <alpha-value>)',
                ink: 'rgb(var(--c-ink) / <alpha-value>)',
                muted: 'rgb(var(--c-muted) / <alpha-value>)',
                line: 'rgb(var(--c-line) / <alpha-value>)',
                accent: 'rgb(var(--c-accent) / <alpha-value>)',
                'accent-soft': 'rgb(var(--c-accent-soft) / <alpha-value>)',
                positive: 'rgb(var(--c-positive) / <alpha-value>)',
                danger: 'rgb(var(--c-danger) / <alpha-value>)',
                warn: 'rgb(var(--c-warn) / <alpha-value>)',
                // Rétro-compat : ancien « cyan » conservé pour ne rien casser pendant la migration.
                cyan: { 400: '#22d3ee', 500: '#06b6d4', 900: '#164e63' },
            },
            borderRadius: {
                ada: '14px',
                'ada-lg': '20px',
                'ada-xl': '28px',
            },
            boxShadow: {
                // Ombres douces façon Apple (discrètes, superposées)
                'ada-sm': '0 1px 2px rgba(0,0,0,0.05), 0 1px 1px rgba(0,0,0,0.04)',
                'ada': '0 2px 8px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04)',
                'ada-md': '0 6px 20px rgba(0,0,0,0.08), 0 2px 6px rgba(0,0,0,0.05)',
                'ada-lg': '0 18px 48px rgba(0,0,0,0.12), 0 4px 12px rgba(0,0,0,0.06)',
            },
            transitionTimingFunction: {
                ada: 'cubic-bezier(0.22, 1, 0.36, 1)',
            },
        },
    },
    plugins: [],
}

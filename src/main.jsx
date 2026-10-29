import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'

const app = <App />
const isElectron = Boolean(window?.process?.versions?.electron)

// ── Thème clair/sombre ───────────────────────────────────────────────────────
// Auto selon le système par défaut ; l'utilisateur peut forcer 'light'/'dark'
// (mémorisé). data-theme absent = auto (géré par prefers-color-scheme dans le CSS).
try {
    const saved = typeof localStorage !== 'undefined' ? localStorage.getItem('ada-theme') : null
    if (saved === 'light' || saved === 'dark') {
        document.documentElement.setAttribute('data-theme', saved)
    }
    // Helper global pour la bascule depuis l'UI : window.adaSetTheme('light'|'dark'|'auto')
    window.adaSetTheme = (mode) => {
        try {
            if (mode === 'auto') {
                document.documentElement.removeAttribute('data-theme')
                localStorage.removeItem('ada-theme')
            } else {
                document.documentElement.setAttribute('data-theme', mode)
                localStorage.setItem('ada-theme', mode)
            }
        } catch (e) { /* stockage indisponible */ }
    }
} catch (e) { /* pas de localStorage */ }

// ── Mode perfs Electron ──────────────────────────────────────────────────────
// Coupe les backdrop-blur / grosses ombres (très coûteux en GPU) via les règles
// .electron-performance d'index.css. Était défini mais jamais activé → c'était la
// cause n°1 du lag. Désactivable pour comparer : localStorage['ada-perf'] = 'off'.
try {
    const perfOff = typeof localStorage !== 'undefined' && localStorage.getItem('ada-perf') === 'off'
    if (isElectron && !perfOff) {
        document.documentElement.classList.add('electron-performance')
    }
} catch (e) {
    if (isElectron) document.documentElement.classList.add('electron-performance')
}

// PWA : enregistre le service worker en web/mobile (pas dans Electron).
// Le rend installable sur l'écran d'accueil du téléphone.
if (!isElectron && 'serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js').catch(() => {})
    })
}

ReactDOM.createRoot(document.getElementById('root')).render(
    isElectron ? app : <React.StrictMode>{app}</React.StrictMode>,
)

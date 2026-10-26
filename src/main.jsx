import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'

const app = <App />
const isElectron = Boolean(window?.process?.versions?.electron)

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

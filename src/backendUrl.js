const LOCAL_BACKEND_URL = 'http://localhost:8000';

function isElectronRenderer() {
    return Boolean(
        typeof window !== 'undefined'
        && window.process?.versions?.electron
    );
}

function isLocalViteServer() {
    if (typeof window === 'undefined') return false;
    const localHosts = new Set(['localhost', '127.0.0.1']);
    return localHosts.has(window.location.hostname) && window.location.port === '5173';
}

// Electron et Vite local parlent au backend local. Une build web servie par
// FastAPI utilise son origine HTTPS courante (Tailscale, Cloudflare, etc.).
export const BACKEND_URL = (
    import.meta.env.VITE_BACKEND_URL?.trim()
    || (isElectronRenderer() || isLocalViteServer()
        ? LOCAL_BACKEND_URL
        : window.location.origin)
);

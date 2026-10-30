// Résolution du token d'auth Socket.IO :
//  1) VITE_ADA_API_TOKEN si défini au build (web/mobile),
//  2) sinon IPC interne Electron, lu depuis backend/.env par le main process.
// Sans token correct, le backend refuse le handshake et la fenêtre ne reçoit
// plus rien d'Ada (humeur, parole, pilotage, chat).
function fromElectronIpc(hostWindow = globalThis.window) {
    try {
        const ipcRenderer = hostWindow?.require?.('electron')?.ipcRenderer;
        return ipcRenderer?.sendSync('ada-token:get') || '';
    } catch (_) {
        return '';
    }
}

export function resolveAdaToken(viteToken = '', hostWindow = globalThis.window) {
    return viteToken || fromElectronIpc(hostWindow) || '';
}

export const ADA_TOKEN = resolveAdaToken(import.meta.env?.VITE_ADA_API_TOKEN || '');

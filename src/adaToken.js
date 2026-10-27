// Résolution du token d'auth Socket.IO, robuste :
//  1) VITE_ADA_API_TOKEN si défini au build (web/mobile),
//  2) sinon le token injecté par Electron dans process.argv (--ada-token=…),
//     lu directement depuis backend/.env → plus rien à synchroniser à la main.
// Sans token correct, le backend refuse le handshake et la fenêtre ne reçoit
// plus rien d'Ada (humeur, parole, pilotage, chat).
function fromArgv() {
    try {
        const argv = (typeof window !== 'undefined' && window.process && window.process.argv) || [];
        const a = argv.find((x) => typeof x === 'string' && x.startsWith('--ada-token='));
        return a ? a.slice('--ada-token='.length) : '';
    } catch (_) {
        return '';
    }
}

export const ADA_TOKEN = (import.meta.env.VITE_ADA_API_TOKEN || '') || fromArgv() || '';

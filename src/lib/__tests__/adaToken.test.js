import { describe, expect, it, vi } from 'vitest';
import { resolveAdaToken } from '../../adaToken';


describe('ADA_TOKEN dans Electron', () => {
    it('utilise le canal IPC interne sans lire les arguments du processus', async () => {
        const sendSync = vi.fn().mockReturnValue('token-ipc-test');
        const hostWindow = {
            require: vi.fn().mockReturnValue({ ipcRenderer: { sendSync } }),
        };
        const token = resolveAdaToken('', hostWindow);

        expect(token).toBe('token-ipc-test');
        expect(sendSync).toHaveBeenCalledWith('ada-token:get');
    });

    it('échoue proprement hors Electron', () => {
        const hostWindow = {
            require: vi.fn(() => { throw new Error('Electron indisponible'); }),
        };

        expect(resolveAdaToken('', hostWindow)).toBe('');
    });
});

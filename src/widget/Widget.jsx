import React, { useCallback, useEffect, useRef, useState } from 'react';
import io from 'socket.io-client';
import Eyes from './Eyes';
import MiniChat from './MiniChat';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';

// IPC (contextIsolation désactivé comme dans App.jsx)
const ipc = (() => {
    try {
        return window.require('electron').ipcRenderer;
    } catch {
        return { send: () => {}, on: () => {} };
    }
})();

const DRAG_THRESHOLD = 5; // px : en dessous = clic (toggle), au-dessus = déplacement

export default function Widget() {
    const [open, setOpen] = useState(false);
    const [piloting, setPiloting] = useState(false);
    const [speaking, setSpeaking] = useState(false);
    const [look, setLook] = useState({ x: 0, y: 0 });
    const drag = useRef({ active: false, moved: 0, sx: 0, sy: 0 });
    const speakTimer = useRef(null);

    // Socket : pilotage PC (humeur « acting ») + parole d'Ada (humeur « speaking »).
    useEffect(() => {
        let socket;
        try {
            socket = io(BACKEND_URL, { transports: ['websocket'], upgrade: false });
            socket.on('pc_control_state', (d) => setPiloting(!!(d && d.active)));
            // Quand Ada émet du texte, elle « parle » : bouche qui pulse ~1,6 s.
            socket.on('transcription', (d) => {
                if (!d || d.sender === 'user') return;
                setSpeaking(true);
                if (speakTimer.current) clearTimeout(speakTimer.current);
                speakTimer.current = setTimeout(() => setSpeaking(false), 1600);
            });
        } catch (e) { /* backend indisponible */ }
        return () => {
            try { socket && socket.close(); } catch (e) {}
            if (speakTimer.current) clearTimeout(speakTimer.current);
        };
    }, []);

    // Les pupilles suivent le curseur (dans la fenêtre de la vignette).
    useEffect(() => {
        const onMouse = (e) => {
            const cx = window.innerWidth / 2;
            const cy = window.innerHeight / 2;
            setLook({ x: (e.clientX - cx) / (cx || 1), y: (e.clientY - cy) / (cy || 1) });
        };
        window.addEventListener('mousemove', onMouse);
        return () => window.removeEventListener('mousemove', onMouse);
    }, []);

    // Humeur : pilotage > parole > repos.
    const mood = piloting ? 'acting' : (speaking ? 'speaking' : 'idle');

    const toggle = useCallback(() => {
        setOpen((prev) => {
            const next = !prev;
            ipc.send('widget:set-open', { open: next });
            return next;
        });
    }, []);

    const onMove = useCallback((e) => {
        const d = drag.current;
        if (!d.active) return;
        d.moved = Math.max(d.moved, Math.abs(e.screenX - d.sx) + Math.abs(e.screenY - d.sy));
        // Le déplacement réel est calculé côté Electron (il connaît la position de la
        // fenêtre et l'écran) — on envoie juste la position écran du curseur.
        ipc.send('widget:drag-move', { mx: e.screenX, my: e.screenY });
    }, []);

    const onUp = useCallback(() => {
        const d = drag.current;
        d.active = false;
        window.removeEventListener('mousemove', onMove);
        window.removeEventListener('mouseup', onUp);
        ipc.send('widget:drag-end');
        if (d.moved < DRAG_THRESHOLD) toggle();
    }, [onMove, toggle]);

    const onMouseDown = useCallback((e) => {
        if (e.button !== 0) return;
        e.preventDefault();
        drag.current = { active: true, moved: 0, sx: e.screenX, sy: e.screenY };
        ipc.send('widget:drag-start');
        window.addEventListener('mousemove', onMove);
        window.addEventListener('mouseup', onUp);
    }, [onMove, onUp]);

    return (
        <div className="jarvis-widget">
            <button
                className={`jv-avatar ${open ? 'is-open' : ''} ${piloting ? 'is-piloting' : ''}`}
                onMouseDown={onMouseDown}
                title={piloting ? 'Jarvis pilote l’écran…' : 'Jarvis — cliquer pour ouvrir, glisser pour déplacer'}
            >
                <Eyes mood={mood} look={look} size={40} />
                {!open && <span className="jv-pulse" />}
                {piloting && <span className="jv-piloting-ring" />}
            </button>

            {open && <MiniChat onClose={toggle} />}
        </div>
    );
}

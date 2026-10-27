import React, { useCallback, useEffect, useRef, useState } from 'react';
import io from 'socket.io-client';
import Face from './Face';
import MiniChat from './MiniChat';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';
// Même token d'auth que la fenêtre principale : sans lui, si ADA_API_TOKEN est
// configuré côté backend, le handshake socket de la vignette est REFUSÉ et elle
// ne reçoit plus rien (humeur, parole, pilotage) — seul le curseur (local) marche.
const ADA_TOKEN = import.meta.env.VITE_ADA_API_TOKEN || '';

// IPC (contextIsolation désactivé comme dans App.jsx)
const ipc = (() => {
    try {
        return window.require('electron').ipcRenderer;
    } catch {
        return { send: () => {}, on: () => {} };
    }
})();

const DRAG_THRESHOLD = 5; // px : en dessous = clic (toggle), au-dessus = déplacement

// Tailles du visage (px) et fenêtre correspondante. Le renderer est la source de
// vérité : il calcule les dimensions et demande à Electron de redimensionner.
const FACE_PX = { s: 60, m: 88, l: 132, xl: 196 };
const PAD = 12;
const CHAT = { width: 360, height: 560 };
const SIZE_ORDER = ['s', 'm', 'l', 'xl'];

export default function Widget() {
    const [open, setOpen] = useState(false);
    const [size, setSize] = useState('m');
    const [full, setFull] = useState(false);
    const [piloting, setPiloting] = useState(false);
    const [speaking, setSpeaking] = useState(false);
    const [affect, setAffect] = useState(null);
    const [look, setLook] = useState({ x: 0, y: 0 });
    const [fullPx, setFullPx] = useState(360);
    const drag = useRef({ active: false, moved: 0, sx: 0, sy: 0 });
    const speakTimer = useRef(null);

    // Socket : état émotionnel du brain + pilotage PC + parole d'Ada.
    useEffect(() => {
        let socket;
        try {
            socket = io(BACKEND_URL, {
                transports: ['websocket'],
                upgrade: false,
                auth: ADA_TOKEN ? { token: ADA_TOKEN } : undefined,
            });
            socket.on('connect_error', (e) => console.warn('[widget] socket refusé :', e && e.message));
            socket.on('pc_control_state', (d) => setPiloting(!!(d && d.active)));
            socket.on('ada_affect', (d) => { if (d && typeof d === 'object') setAffect(d); });
            // Signal fiable relayé par la fenêtre qui joue l'audio (dure toute la phrase).
            socket.on('ada_speaking', (d) => setSpeaking(!!(d && d.on)));
        } catch (e) { /* backend indisponible */ }
        return () => {
            try { socket && socket.close(); } catch (e) {}
            if (speakTimer.current) clearTimeout(speakTimer.current);
        };
    }, []);

    // Les pupilles suivent le curseur (dans la fenêtre).
    useEffect(() => {
        const onMouse = (e) => {
            const cx = window.innerWidth / 2, cy = window.innerHeight / 2;
            setLook({ x: (e.clientX - cx) / (cx || 1), y: (e.clientY - cy) / (cy || 1) });
        };
        window.addEventListener('mousemove', onMouse);
        return () => window.removeEventListener('mousemove', onMouse);
    }, []);

    // En plein écran : taille du visage = ~55 % du plus petit côté de l'écran.
    useEffect(() => {
        if (!full) return;
        const recompute = () => setFullPx(Math.round(Math.min(window.innerWidth, window.innerHeight) * 0.55));
        recompute();
        window.addEventListener('resize', recompute);
        return () => window.removeEventListener('resize', recompute);
    }, [full]);

    // Redimensionne la fenêtre Electron selon l'état (taille / chat ouvert).
    useEffect(() => {
        if (full) return; // la fenêtre est gérée par le mode plein écran
        const facePx = FACE_PX[size];
        const w = open ? CHAT.width : Math.max(facePx + PAD * 2, 176);
        const h = open ? CHAT.height : facePx + PAD * 2;
        ipc.send('widget:resize', { w, h });
    }, [size, open, full]);

    const toggleFull = useCallback(() => {
        setFull((prev) => {
            const next = !prev;
            ipc.send('widget:fullscreen', { on: next });
            if (next) setOpen(false);
            return next;
        });
    }, []);

    const toggleOpen = useCallback(() => {
        if (full) return;
        setOpen((p) => !p);
    }, [full]);

    // Glisser / cliquer sur le visage.
    const onMove = useCallback((e) => {
        const d = drag.current;
        if (!d.active) return;
        d.moved = Math.max(d.moved, Math.abs(e.screenX - d.sx) + Math.abs(e.screenY - d.sy));
        ipc.send('widget:drag-move', { mx: e.screenX, my: e.screenY });
    }, []);

    const onUp = useCallback(() => {
        const d = drag.current;
        d.active = false;
        window.removeEventListener('mousemove', onMove);
        window.removeEventListener('mouseup', onUp);
        ipc.send('widget:drag-end');
        if (d.moved < DRAG_THRESHOLD) toggleOpen();
    }, [onMove, toggleOpen]);

    const onMouseDown = useCallback((e) => {
        if (e.button !== 0 || full) return;
        e.preventDefault();
        drag.current = { active: true, moved: 0, sx: e.screenX, sy: e.screenY };
        ipc.send('widget:drag-start');
        window.addEventListener('mousemove', onMove);
        window.addEventListener('mouseup', onUp);
    }, [onMove, onUp, full]);

    const cycleSize = useCallback((s) => (e) => {
        e.stopPropagation();
        setSize(s);
    }, []);

    const facePx = full ? fullPx : FACE_PX[size];
    const commonFace = (
        <Face affect={affect} talking={speaking} acting={piloting} look={look} size={facePx} />
    );

    // ── Plein écran : visage centré sur fond quasi plein, contrôles discrets ──
    if (full) {
        return (
            <div className="jarvis-widget jv-full">
                <div className="jv-full-face">{commonFace}</div>
                <div className="jv-controls jv-controls-full">
                    {SIZE_ORDER.map((s) => (
                        <button key={s} className="jv-size-dot" onClick={cycleSize(s)} title={`Taille ${s.toUpperCase()}`}>
                            {s.toUpperCase()}
                        </button>
                    ))}
                    <button className="jv-size-dot jv-full-btn" onClick={toggleFull} title="Quitter le plein écran">⤡</button>
                </div>
            </div>
        );
    }

    // ── Chat ouvert : petit visage en tête + mini-chat ──
    if (open) {
        return (
            <div className="jarvis-widget jv-open">
                <button className="jv-avatar is-open" onMouseDown={onMouseDown} title="Ada">
                    <Face affect={affect} talking={speaking} acting={piloting} look={look} size={48} />
                </button>
                <MiniChat onClose={toggleOpen} />
            </div>
        );
    }

    // ── Vignette : le visage EST la vignette ──
    return (
        <div className={`jarvis-widget jv-collapsed ${piloting ? 'is-piloting' : ''}`}>
            <button className="jv-avatar" onMouseDown={onMouseDown}
                    title={piloting ? 'Ada pilote l’écran…' : 'Ada — cliquer pour ouvrir, glisser pour déplacer'}>
                {commonFace}
            </button>
            <div className="jv-controls">
                {SIZE_ORDER.map((s) => (
                    <button key={s} className={`jv-size-dot ${size === s ? 'is-active' : ''}`}
                            onClick={cycleSize(s)} title={`Taille ${s.toUpperCase()}`}>
                        {s.toUpperCase()}
                    </button>
                ))}
                <button className="jv-size-dot jv-full-btn" onClick={(e) => { e.stopPropagation(); toggleFull(); }}
                        title="Plein écran">⤢</button>
            </div>
        </div>
    );
}

/**
 * eye-main.js — « Les yeux d'Ada » (Couche B).
 *
 * Capture une caméra (idéalement la caméra arrière du téléphone clippé au casque,
 * ou n'importe quelle webcam) et pousse les frames au backend via le canal
 * EXISTANT `video_frame` → qui alimente la vision d'Ada (YOLO + Gemini multimodal).
 * Résultat : « Ada voit ce que tu vois », découplé du casque → marche avec
 * n'importe quel casque (même bas de gamme) + une petite caméra.
 *
 * getUserMedia exige HTTPS → passe par le Tailscale (ou localhost).
 */
import io from 'socket.io-client';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';
const ADA_TOKEN = import.meta.env.VITE_ADA_API_TOKEN || '';
const FPS = parseFloat(import.meta.env.VITE_EYE_FPS || '2'); // frames/seconde envoyées
const W = 640, H = 480;

const video = document.getElementById('cam');
const statusEl = document.getElementById('status');
const goBtn = document.getElementById('go');

const canvas = document.createElement('canvas');
canvas.width = W; canvas.height = H;
const ctx = canvas.getContext('2d');

const socket = io(BACKEND_URL, {
    transports: ['websocket'], upgrade: false,
    auth: ADA_TOKEN ? { token: ADA_TOKEN } : undefined,
});

let connected = false, sent = 0;

function setStatus(t) { statusEl.textContent = t + (sent ? ` · ${sent} frames envoyées` : ''); }

socket.on('connect', () => {
    connected = true;
    socket.emit('set_vision_mode', { mode: 'camera' }); // Ada regarde la caméra
    setStatus('connectée');
});
socket.on('disconnect', () => { connected = false; setStatus('hors ligne'); });

async function start() {
    goBtn.style.display = 'none';
    try {
        const stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 720 } },
            audio: false,
        });
        video.srcObject = stream;
        await video.play();
        setStatus('caméra active — Ada voit ✓');
        loop();
    } catch (e) {
        setStatus('caméra refusée : ' + (e && e.message ? e.message : e));
        goBtn.style.display = '';
    }
}

let last = 0;
function loop() {
    requestAnimationFrame(loop);
    const now = performance.now();
    if (now - last < 1000 / FPS) return;
    last = now;
    if (!connected || video.readyState < 2) return;
    try {
        ctx.drawImage(video, 0, 0, W, H);
        const b64 = canvas.toDataURL('image/jpeg', 0.5).split(',')[1];
        socket.emit('video_frame', { image: b64 });
        sent++;
        if (sent % 4 === 0) setStatus('Ada voit ✓');
    } catch (e) { /* frame sautée */ }
}

goBtn.addEventListener('click', start);
setStatus('prête — active la caméra');

/**
 * xr-main.js — Client WebXR portable d'Ada (Couche A).
 *
 * Marche sur N'IMPORTE QUEL casque WebXR (Quest, Pico, cardboard…) via le
 * navigateur : AR passthrough si dispo, sinon VR, sinon aperçu 2D sur desktop.
 * Affiche la présence d'Ada (orbe réactive + panneau texte) dans l'espace, et
 * réutilise EXACTEMENT le pipeline voix du client web (mic 16 kHz -> socket,
 * voix d'Ada en PCM 24 kHz). Se connecte au backend via Socket.IO (+ Tailscale).
 */
import * as THREE from 'three';
import { XRButton } from 'three/examples/jsm/webxr/XRButton.js';
import io from 'socket.io-client';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';
const ADA_TOKEN = import.meta.env.VITE_ADA_API_TOKEN || '';

// ── Three.js : scène, caméra, rendu ─────────────────────────────────────────
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(70, window.innerWidth / window.innerHeight, 0.01, 50);

const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.xr.enabled = true;
renderer.setClearAlpha(0); // transparent -> passthrough visible en AR
document.getElementById('xr-root').appendChild(renderer.domElement);

scene.add(new THREE.HemisphereLight(0xbfefff, 0x102030, 1.1));
const keyLight = new THREE.PointLight(0x22d3ee, 2.2, 10);
keyLight.position.set(0, 2, 0);
scene.add(keyLight);

// ── Orbe d'Ada (présence réactive) ──────────────────────────────────────────
const ORB_POS = new THREE.Vector3(0, 1.3, -1.2);
const orbGroup = new THREE.Group();
orbGroup.position.copy(ORB_POS);
scene.add(orbGroup);

const CYAN = new THREE.Color(0x22d3ee);
const AMBER = new THREE.Color(0xfbbf24);

const core = new THREE.Mesh(
    new THREE.IcosahedronGeometry(0.14, 3),
    new THREE.MeshStandardMaterial({ color: 0x0a2230, emissive: CYAN.clone(), emissiveIntensity: 0.8, roughness: 0.3, metalness: 0.4 })
);
orbGroup.add(core);

const shell = new THREE.Mesh(
    new THREE.IcosahedronGeometry(0.2, 2),
    new THREE.MeshBasicMaterial({ color: CYAN.clone(), wireframe: true, transparent: true, opacity: 0.35 })
);
orbGroup.add(shell);

// ── Panneau texte (canvas -> texture) ───────────────────────────────────────
const panelCanvas = document.createElement('canvas');
panelCanvas.width = 1024; panelCanvas.height = 512;
const pctx = panelCanvas.getContext('2d');
const panelTex = new THREE.CanvasTexture(panelCanvas);
const panel = new THREE.Mesh(
    new THREE.PlaneGeometry(0.9, 0.45),
    new THREE.MeshBasicMaterial({ map: panelTex, transparent: true })
);
panel.position.set(0, 1.0, -1.2);
scene.add(panel);

let statusLine = 'Connexion…';
let adaLines = [];
function drawPanel() {
    pctx.clearRect(0, 0, 1024, 512);
    pctx.fillStyle = 'rgba(6,16,22,0.72)';
    pctx.strokeStyle = 'rgba(34,211,238,0.5)';
    pctx.lineWidth = 4;
    roundRect(pctx, 8, 8, 1008, 496, 28); pctx.fill(); pctx.stroke();
    pctx.fillStyle = '#22d3ee';
    pctx.font = 'bold 34px "Share Tech Mono", monospace';
    pctx.fillText('ADA', 40, 60);
    pctx.fillStyle = '#7dd3fc';
    pctx.font = '24px monospace';
    pctx.fillText(statusLine, 130, 58);
    pctx.fillStyle = '#e5f6fb';
    pctx.font = '26px monospace';
    const text = adaLines.slice(-4).join('\n') || '…';
    wrapText(pctx, text, 40, 120, 944, 34);
    panelTex.needsUpdate = true;
}
function roundRect(c, x, y, w, h, r) {
    c.beginPath();
    c.moveTo(x + r, y); c.arcTo(x + w, y, x + w, y + h, r); c.arcTo(x + w, y + h, x, y + h, r);
    c.arcTo(x, y + h, x, y, r); c.arcTo(x, y, x + w, y, r); c.closePath();
}
function wrapText(c, text, x, y, maxW, lh) {
    for (const para of text.split('\n')) {
        let line = '', yy = y;
        for (const word of para.split(' ')) {
            const test = line + word + ' ';
            if (c.measureText(test).width > maxW && line) { c.fillText(line, x, yy); line = word + ' '; yy += lh; }
            else line = test;
        }
        c.fillText(line, x, yy);
        y = yy + lh;
    }
}
drawPanel();

// ── Socket.IO + voix (même contrat que le client web) ───────────────────────
const socket = io(BACKEND_URL, {
    transports: ['websocket'], upgrade: false,
    auth: ADA_TOKEN ? { token: ADA_TOKEN } : undefined,
});

let amp = 0;        // amplitude cible (0..1) -> anime l'orbe
let piloting = false;

socket.on('connect', () => { statusLine = 'connectée'; drawPanel(); });
socket.on('disconnect', () => { statusLine = 'hors ligne'; drawPanel(); });
socket.on('status', (d) => { if (d && d.msg) { statusLine = String(d.msg); drawPanel(); } });
socket.on('pc_control_state', (d) => { piloting = !!(d && d.active); });

socket.on('transcription', (d) => {
    if (!d || !d.text) return;
    const last = adaLines[adaLines.length - 1];
    if (last && last.startsWith(d.sender + ':')) adaLines[adaLines.length - 1] = last + d.text;
    else adaLines.push(`${d.sender}: ${d.text}`);
    if (adaLines.length > 20) adaLines = adaLines.slice(-20);
    amp = Math.max(amp, 0.5);
    drawPanel();
});

// Lecture de la voix d'Ada (PCM16 @ 24 kHz) — identique au client web.
let playCtx = null, playNext = 0;
socket.on('clear_audio', () => { playNext = 0; });
socket.on('audio_pcm', (data) => {
    try {
        if (!playCtx || playCtx.state === 'closed') { playCtx = new AudioContext({ sampleRate: 24000 }); playNext = 0; }
        if (playCtx.state === 'suspended') playCtx.resume();
        const bytes = data instanceof ArrayBuffer ? new Uint8Array(data) : new Uint8Array(Object.values(data));
        const int16 = new Int16Array(bytes.buffer, bytes.byteOffset, Math.floor(bytes.byteLength / 2));
        const f32 = new Float32Array(int16.length);
        let sum = 0;
        for (let i = 0; i < int16.length; i++) { f32[i] = int16[i] / 32768; sum += f32[i] * f32[i]; }
        amp = Math.max(amp, Math.min(1, Math.sqrt(sum / (int16.length || 1)) * 4));
        const buf = playCtx.createBuffer(1, f32.length, 24000);
        buf.getChannelData(0).set(f32);
        const src = playCtx.createBufferSource(); src.buffer = buf; src.connect(playCtx.destination);
        const startAt = Math.max(playCtx.currentTime + 0.01, playNext);
        src.start(startAt); playNext = startAt + buf.duration;
    } catch (e) { console.error('[XR] audio_pcm', e); }
});

// Capture micro -> backend (16 kHz PCM), identique au client web.
let micCtx = null, micStarted = false;
async function startMic() {
    if (micStarted) return;
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
        micCtx = new AudioContext({ sampleRate: 16000 });
        const source = micCtx.createMediaStreamSource(stream);
        const processor = micCtx.createScriptProcessor(2048, 1, 1);
        processor.onaudioprocess = (e) => {
            const f32 = e.inputBuffer.getChannelData(0);
            const int16 = new Int16Array(f32.length);
            let sum = 0;
            for (let i = 0; i < f32.length; i++) { const s = Math.max(-1, Math.min(1, f32[i])); int16[i] = s < 0 ? s * 0x8000 : s * 0x7fff; sum += s * s; }
            amp = Math.max(amp, Math.min(1, Math.sqrt(sum / f32.length) * 3));
            socket.emit('mic_audio_chunk', { data: Array.from(new Uint8Array(int16.buffer)) });
        };
        const silent = micCtx.createGain(); silent.gain.value = 0; silent.connect(micCtx.destination);
        source.connect(processor); processor.connect(silent);
        socket.emit('start_audio', { device_index: null, device_name: null, muted: false });
        micStarted = true;
        statusLine = 'à l’écoute'; drawPanel();
    } catch (e) { console.error('[XR] mic', e); statusLine = 'micro refusé'; drawPanel(); }
}

// ── Bouton XR (AR passthrough si dispo, sinon VR) ───────────────────────────
document.body.appendChild(XRButton.createButton(renderer, {
    optionalFeatures: ['local-floor', 'bounded-floor', 'hand-tracking', 'layers'],
}));
renderer.xr.addEventListener('sessionstart', () => {
    if (playCtx && playCtx.state === 'suspended') playCtx.resume();
    startMic(); // voix activée dès l'entrée dans le monde
});

// ── Boucle de rendu ─────────────────────────────────────────────────────────
const clock = new THREE.Clock();
renderer.setAnimationLoop(() => {
    const dt = clock.getDelta();
    amp = Math.max(0, amp - dt * 1.6); // décroissance douce
    const pulse = 1 + amp * 0.5;
    core.scale.setScalar(pulse);
    shell.scale.setScalar(1 + amp * 0.25);
    shell.rotation.y += dt * 0.4; shell.rotation.x += dt * 0.15;
    const col = piloting ? AMBER : CYAN;
    core.material.emissive.copy(col); core.material.emissiveIntensity = 0.6 + amp * 1.2;
    shell.material.color.copy(col);
    keyLight.color.copy(col); keyLight.intensity = 1.5 + amp * 3;
    renderer.render(scene, camera);
});

window.addEventListener('resize', () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
});

// Desktop : petit mot pour cliquer le bouton XR (ou tester le son hors casque).
statusLine = 'prête — entre en XR';
drawPanel();

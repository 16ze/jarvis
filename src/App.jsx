import React, { useEffect, useState, useRef, useMemo } from 'react';
import io from 'socket.io-client';

import Visualizer from './components/Visualizer';
import TopAudioBar from './components/TopAudioBar';
import CadWindow from './components/CadWindow';
import TerminalWindow from './components/TerminalWindow';
import ChatModule from './components/ChatModule';
import ToolsModule from './components/ToolsModule';
import WorkspaceShell from './components/WorkspaceShell';
import { Mic, MicOff, Settings, X, Minus, Power, Video, VideoOff, Layout, Hand, Printer, Clock } from 'lucide-react';
import { FilesetResolver, HandLandmarker } from '@mediapipe/tasks-vision';
// MemoryPrompt removed - memory is now actively saved to project
import ConfirmationPopup from './components/ConfirmationPopup';
import AuthLock from './components/AuthLock';
import KasaWindow from './components/KasaWindow';
import PrinterWindow from './components/PrinterWindow';
import SettingsWindow from './components/SettingsWindow';
import DocumentsWindow from './components/DocumentsWindow';
import OsShell from './components/OsShell';
import MobileApp from './components/MobileApp';
import {
    DEFAULT_HAND_CONTROL_CONFIG,
    OneEuroFilter2D,
    CursorEngine,
    GestureStateMachine,
    clampPointToInteractionBox,
} from './lib/handTrackingControl';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';
// Token partagé optionnel : envoyé au handshake si ADA_API_TOKEN est configuré
// côté backend (voir server.py). Vide = aucune auth exigée (défense = origine CORS).
const ADA_TOKEN = import.meta.env.VITE_ADA_API_TOKEN || '';
const socket = io(BACKEND_URL, {
    transports: ['websocket'],
    upgrade: false,
    auth: ADA_TOKEN ? { token: ADA_TOKEN } : undefined,
});
const ipcRenderer = (() => {
    try {
        return window.require('electron').ipcRenderer;
    } catch {
        // Running in browser (mobile/web) — no Electron
        return {
            send: () => {},
            on: () => {},
            off: () => {},
        };
    }
})();

const isMobile = window.innerWidth < 768 || /iPhone|iPad|Android/i.test(navigator.userAgent);
const isElectron = Boolean(window?.process?.versions?.electron);

function App() {
    const [status, setStatus] = useState('Disconnected');
    const [socketConnected, setSocketConnected] = useState(socket.connected); // Track socket connection reactively
    // Auth State
    const [isAuthenticated, setIsAuthenticated] = useState(() => {
        // Optimistically assume authenticated if face auth is NOT enabled
        return localStorage.getItem('face_auth_enabled') !== 'true';
    });

    // Initialize from LocalStorage to prevent flash of UI
    const [isLockScreenVisible, setIsLockScreenVisible] = useState(() => {
        const saved = localStorage.getItem('face_auth_enabled');
        // If saved is 'true', we MUST start locked.
        // If 'false' or null (default off), we start unlocked.
        return saved === 'true';
    });

    // Local state for tracking settings, also init from local storage
    const [faceAuthEnabled, setFaceAuthEnabled] = useState(() => {
        return localStorage.getItem('face_auth_enabled') === 'true';
    });


    const [isConnected, setIsConnected] = useState(true); // Power state DEFAULT ON
    const [isMuted, setIsMuted] = useState(false); // Mic state DEFAULT ON
    const [isVideoOn, setIsVideoOn] = useState(false); // Video state
    const [isScreenMode, setIsScreenMode] = useState(false); // Ada sees screen
    const [messages, setMessages] = useState([]);
    const [inputValue, setInputValue] = useState('');
    const [cadData, setCadData] = useState(null);
    const [cadThoughts, setCadThoughts] = useState(''); // Streaming AI thoughts
    const [cadRetryInfo, setCadRetryInfo] = useState({ attempt: 1, maxAttempts: 3, error: null }); // Retry status
    // showMemoryPrompt removed - memory is now actively saved to project
    const [confirmationRequest, setConfirmationRequest] = useState(null); // { id, tool, args }
    const [kasaDevices, setKasaDevices] = useState([]);
    const [showKasaWindow, setShowKasaWindow] = useState(false);
    const [showPrinterWindow, setShowPrinterWindow] = useState(false);
    const [showDocumentsWindow, setShowDocumentsWindow] = useState(false);
    const [showCadWindow, setShowCadWindow] = useState(false);
    const [showWorkspaceWindow, setShowWorkspaceWindow] = useState(false);
    const [workspaceState, setWorkspaceState] = useState({ activeWorkspace: 'default', items: [] });
    const [workspaceEvents, setWorkspaceEvents] = useState([]);
    const [workspaceStatus, setWorkspaceStatus] = useState(null);
    const [workspaceResearchResult, setWorkspaceResearchResult] = useState(null);

    const [showTerminalWindow, setShowTerminalWindow] = useState(false);
    const [showChatWindow, setShowChatWindow] = useState(false);
    const [terminalEntries, setTerminalEntries] = useState([]);

    // Printing workflow status (for top toolbar display)
    const [slicingStatus, setSlicingStatus] = useState({ active: false, percent: 0, message: '' });
    const [activePrintStatus, setActivePrintStatus] = useState(null); // {printer, progress_percent, time_elapsed, state}
    const [printerCount, setPrinterCount] = useState(0); // Count of connected printers
    const [currentTime, setCurrentTime] = useState(new Date()); // Live clock


    // RESTORED STATE
    const [aiAudioData, setAiAudioData] = useState(new Array(64).fill(0));
    const [micAudioData, setMicAudioData] = useState(new Array(32).fill(0));
    const aiAudioDataRef = useRef(new Array(64).fill(0));
    const micAudioDataRef = useRef(new Array(32).fill(0));
    const [fps, setFps] = useState(0);

    // Device states - microphones, speakers, webcams
    const [micDevices, setMicDevices] = useState([]);
    const [speakerDevices, setSpeakerDevices] = useState([]);
    const [webcamDevices, setWebcamDevices] = useState([]);

    // Selected device IDs - restored from localStorage
    const [selectedMicId, setSelectedMicId] = useState(() => localStorage.getItem('selectedMicId') || '');
    const [selectedSpeakerId, setSelectedSpeakerId] = useState(() => localStorage.getItem('selectedSpeakerId') || '');
    const [selectedWebcamId, setSelectedWebcamId] = useState(() => localStorage.getItem('selectedWebcamId') || '');
    const [showSettings, setShowSettings] = useState(false);
    const [osScreen, setOsScreen] = useState(null); // écran natif OS actif : null | 'observability' | 'agents'
    const [currentProject, setCurrentProject] = useState('default');

    // Modular Mode State
    const [isModularMode, setIsModularMode] = useState(false);
    const [elementPositions, setElementPositions] = useState({
        video: { x: 40, y: 80 }, // Initial positions (approximate)
        visualizer: { x: window.innerWidth / 2, y: window.innerHeight / 2 - 150 },
        chat: { x: window.innerWidth / 2, y: window.innerHeight / 2 + 100 },
        cad: { x: window.innerWidth / 2 + 300, y: window.innerHeight / 2 },
        browser: { x: window.innerWidth / 2 - 300, y: window.innerHeight / 2 },
        kasa: { x: window.innerWidth / 2 + 350, y: window.innerHeight / 2 - 100 },
        printer: { x: window.innerWidth / 2 - 350, y: window.innerHeight / 2 - 100 },
        tools: { x: window.innerWidth / 2, y: window.innerHeight - 132 } // Fixed bottom OFFSET
    });

    const [elementSizes, setElementSizes] = useState({
        visualizer: { w: 550, h: 350 },
        chat: { w: 560, h: 320 },
        tools: { w: 500, h: 80 }, // Approx
        cad: { w: 400, h: 400 },

        video: { w: 320, h: 180 },
        kasa: { w: 300, h: 380 }, // Approx
        printer: { w: 380, h: 380 } // Approx
    });
    const [activeDragElement, setActiveDragElement] = useState(null);

    // Z-Index Stacking Order (last element = highest z-index)
    const [zIndexOrder, setZIndexOrder] = useState([
        'visualizer', 'chat', 'tools', 'video', 'cad', 'browser', 'kasa', 'printer'
    ]);

    // Hand Control State
    const [isHandTrackingEnabled, setIsHandTrackingEnabled] = useState(false); // DEFAULT OFF
    // Cursor uses refs + direct DOM — no state to avoid 60fps re-renders
    const cursorElRef = useRef(null);
    const isPinchingRef = useRef(false);
    const pinchFramesRef = useRef(0);
    const fistFramesRef = useRef(0);
    const isHandOsDraggingRef = useRef(false);
    const handOsGestureRef = useRef('idle');
    const handOsGestureCandidateRef = useRef('idle');
    const handOsGestureFramesRef = useRef(0);
    const handOsReleaseFramesRef = useRef(0);
    const lastHandOsClickAtRef = useRef(0);
    const lastHandOsWindowSwitchAtRef = useRef(0);
    const handOsSwipeStartRef = useRef({ x: null, y: null, t: 0 });
    const [cursorSensitivity, setCursorSensitivity] = useState(2.0);
    const [isCameraFlipped, setIsCameraFlipped] = useState(false); // Gesture control camera flip

    // Refs for Loop Access (Avoiding Closure Staleness)
    const isHandTrackingEnabledRef = useRef(false); // DEFAULT OFF
    const cursorSensitivityRef = useRef(2.0);
    const isCameraFlippedRef = useRef(false);
    const handLandmarkerRef = useRef(null);
    const handLandmarkerInitPromiseRef = useRef(null);
    const cursorTrailRef = useRef([]); // Stores last N positions for trail
    const [ripples, setRipples] = useState([]); // Visual ripples on click
    const lastHandOsMoveSentRef = useRef(0);
    const lastHandOsScrollYRef = useRef(null);
    const lastHandOsScrollSentRef = useRef(0);
    const lastHandOsNavAtRef = useRef(0);
    const handPointFilterRef = useRef(new OneEuroFilter2D(DEFAULT_HAND_CONTROL_CONFIG.filter));
    const cursorEngineRef = useRef(new CursorEngine(DEFAULT_HAND_CONTROL_CONFIG.cursor));
    const gestureMachineRef = useRef(new GestureStateMachine(DEFAULT_HAND_CONTROL_CONFIG.gestures));
    const lastHandDebugAtRef = useRef(0);
    const [handDebug, setHandDebug] = useState({
        state: 'IDLE',
        pinchRatio: null,
        confidence: 0,
        clutch: false,
        rawCursor: null,
        filteredCursor: null,
        interactionInside: false,
        deadZone: DEFAULT_HAND_CONTROL_CONFIG.cursor.deadZone,
    });

    // Web Audio Context for Mic Visualization
    const audioContextRef = useRef(null);
    const analyserRef = useRef(null);
    const sourceRef = useRef(null);
    const animationFrameRef = useRef(null);
    const micVisualizerStreamRef = useRef(null);
    const lastAiAudioUpdateRef = useRef(0);

    // Frontend mic capture with AEC (replaces PyAudio on the backend)
    const aecStreamRef = useRef(null);
    const aecAudioCtxRef = useRef(null);
    const aecProcessorRef = useRef(null);
    const aecDeviceIdRef = useRef(null);

    // Web Audio playback for Ada (enables browser AEC — browser knows what it's playing)
    const playbackCtxRef = useRef(null);
    const playbackNextTimeRef = useRef(0);
    const playbackSourcesRef = useRef([]);  // Active sources — stopped on interrupt

    // Video Refs
    const videoRef = useRef(null);
    const canvasRef = useRef(null);
    const transmissionCanvasRef = useRef(null); // Dedicated canvas for resizing payload
    const videoIntervalRef = useRef(null);
    const videoAnimationFrameRef = useRef(null);
    const videoStreamRef = useRef(null);
    const isVideoStartingRef = useRef(false);
    const lastFrameTimeRef = useRef(0);
    const frameCountRef = useRef(0);
    const lastVideoTimeRef = useRef(-1);
    const lastHandDetectionRef = useRef(0);
    const lastVideoFrameSentRef = useRef(0);
    const videoBlobInFlightRef = useRef(false);

    // Ref to track video state for the loop (avoids closure staleness)
    const isVideoOnRef = useRef(false);
    const isModularModeRef = useRef(false);
    const elementPositionsRef = useRef(elementPositions);
    const activeDragElementRef = useRef(null);
    const lastActiveDragElementRef = useRef(null);
    const lastCursorPosRef = useRef({ x: 0, y: 0 });
    const lastWristPosRef = useRef({ x: 0, y: 0 }); // For stable fist gesture tracking

    // Smoothing and Snapping Refs
    const smoothedCursorPosRef = useRef({ x: 0, y: 0 });
    const snapStateRef = useRef({ isSnapped: false, element: null, snapPos: { x: 0, y: 0 } });

    // Mouse Drag Refs
    const dragOffsetRef = useRef({ x: 0, y: 0 });
    const isDraggingRef = useRef(false);

    // Update refs when state changes
    useEffect(() => {
        isModularModeRef.current = isModularMode;
        elementPositionsRef.current = elementPositions;
        isHandTrackingEnabledRef.current = isHandTrackingEnabled;
        cursorSensitivityRef.current = cursorSensitivity;
        isCameraFlippedRef.current = isCameraFlipped;
        console.log("[Ref Sync] Camera flipped ref updated to:", isCameraFlipped);
    }, [isModularMode, elementPositions, isHandTrackingEnabled, cursorSensitivity, isCameraFlipped]);

    useEffect(() => {
        if (!isHandTrackingEnabled) {
            handPointFilterRef.current.reset();
            cursorEngineRef.current.reset({ width: window.innerWidth, height: window.innerHeight });
            gestureMachineRef.current.reset();
            setHandDebug(prev => ({ ...prev, state: 'IDLE', confidence: 0, clutch: false, interactionInside: false }));
        }
    }, [isHandTrackingEnabled]);

    // Live Clock Update
    useEffect(() => {
        const timer = setInterval(() => {
            setCurrentTime(new Date());
        }, 1000);
        return () => clearInterval(timer);
    }, []);

    // Centering Logic (Startup & Resize)
    useEffect(() => {
        const centerElements = () => {
            const width = window.innerWidth;
            const height = window.innerHeight;

            const vizH = Math.min(620, Math.max(430, height * 0.58));
            const vizY = Math.max(245, height * 0.38);
            const toolsCenterY = height - 132;
            const chatH = Math.min(360, Math.max(280, height * 0.34));
            const chatY = Math.max(96, height - chatH - 126);

            setElementSizes(prev => ({
                ...prev,
                visualizer: { w: Math.min(1180, width * 0.82), h: vizH },
                chat: { w: Math.min(560, width * 0.82), h: chatH }
            }));

            setElementPositions(prev => ({
                ...prev,
                visualizer: {
                    x: width / 2,
                    y: vizY
                },
                chat: {
                    x: width / 2,
                    y: chatY
                },
                tools: {
                    x: width / 2,
                    y: toolsCenterY
                }
            }));
        };

        // Center on mount
        centerElements();

        // Center on resize
        window.addEventListener('resize', centerElements);
        return () => window.removeEventListener('resize', centerElements);
    }, []);

    // Utility: Clamp position to viewport so component stays fully visible
    const clampToViewport = (pos, size) => {
        const margin = 10;
        const topBarHeight = 60;
        const width = window.innerWidth;
        const height = window.innerHeight;

        return {
            x: Math.max(size.w / 2 + margin, Math.min(width - size.w / 2 - margin, pos.x)),
            y: Math.max(size.h / 2 + margin + topBarHeight, Math.min(height - size.h / 2 - margin, pos.y))
        };
    };

    // Utility: Get z-index for an element based on stacking order
    const getZIndex = (id) => {
        const baseZ = 30; // Above background elements
        const index = zIndexOrder.indexOf(id);
        return baseZ + (index >= 0 ? index : 0);
    };

    // Utility: Bring element to front (highest z-index)
    const bringToFront = (id) => {
        setZIndexOrder(prev => {
            const filtered = prev.filter(el => el !== id);
            return [...filtered, id]; // Move to end = highest z-index
        });
    };

    const ensureHandLandmarker = async () => {
        if (isMobile || handLandmarkerRef.current) return handLandmarkerRef.current;
        if (handLandmarkerInitPromiseRef.current) return handLandmarkerInitPromiseRef.current;

        handLandmarkerInitPromiseRef.current = (async () => {
            try {
                console.log("Initializing HandLandmarker...");

                const modelUrl = new URL('/hand_landmarker.task', window.location.href);
                modelUrl.searchParams.set('v', '20260516-fixed');

                const response = await fetch(modelUrl.href, { cache: 'no-store' });
                if (!response.ok) {
                    throw new Error(`Failed to fetch model: ${response.status} ${response.statusText}`);
                }

                const modelAssetBuffer = new Uint8Array(await response.arrayBuffer());
                const hasZipHeader =
                    modelAssetBuffer.length >= 4 &&
                    ((modelAssetBuffer[0] === 0x50 && modelAssetBuffer[1] === 0x4b) ||
                        (modelAssetBuffer[0] === 0x00 &&
                            modelAssetBuffer[1] === 0x00 &&
                            modelAssetBuffer[2] === 0x50 &&
                            modelAssetBuffer[3] === 0x4b));

                if (!hasZipHeader) {
                    const preview = new TextDecoder()
                        .decode(modelAssetBuffer.slice(0, 80))
                        .replace(/\s+/g, ' ')
                        .trim();
                    throw new Error(`Invalid hand model asset. Expected MediaPipe task bundle, got: ${preview || 'binary data'}`);
                }

                let vision;
                if (isElectron && typeof window.require === 'function') {
                    const path = window.require('path');
                    const appRoot = window.process?.cwd?.() || process.cwd();
                    const wasmDir = path.join(appRoot, 'public', 'mediapipe', 'wasm');
                    vision = {
                        wasmLoaderPath: path.join(wasmDir, 'vision_wasm_internal.js'),
                        wasmBinaryPath: path.join(wasmDir, 'vision_wasm_internal.wasm'),
                    };
                } else {
                    const wasmRoot = new URL('/mediapipe/wasm/', window.location.href).href;
                    vision = await FilesetResolver.forVisionTasks(wasmRoot);
                }

                handLandmarkerRef.current = await HandLandmarker.createFromOptions(vision, {
                    baseOptions: {
                        modelAssetBuffer,
                        delegate: "CPU"
                    },
                    runningMode: "VIDEO",
                    numHands: 1
                });
                addMessage('System', 'Hand Tracking Ready');
                return handLandmarkerRef.current;
            } catch (error) {
                console.error("Failed to initialize HandLandmarker:", error);
                addMessage('System', `Hand Tracking Error: ${error.message}`);
                handLandmarkerInitPromiseRef.current = null;
                return null;
            }
        })();

        return handLandmarkerInitPromiseRef.current;
    };

    // Ref to track if model has been auto-connected (prevents duplicate connections)
    const hasAutoConnectedRef = useRef(false);

    // Auto-Connect Model on Start (Only after Auth and devices loaded)
    useEffect(() => {
        // Only auto-connect once: when socket connected, authenticated, and devices loaded
        if (isConnected && isAuthenticated && socketConnected && micDevices.length > 0 && !hasAutoConnectedRef.current) {
            hasAutoConnectedRef.current = true;

            // Trigger Kasa and Printer Discovery
            socket.emit('discover_kasa');
            socket.emit('discover_printers');

            // Connect to model with small delay for socket stability
            const timer = setTimeout(() => {
                const index = micDevices.findIndex(d => d.deviceId === selectedMicId);
                const queryDevice = micDevices.find(d => d.deviceId === selectedMicId);
                const deviceName = queryDevice ? queryDevice.label : null;
                console.log("Auto-connecting to model with device:", deviceName, "Index:", index);

                setStatus('Connecting...');
                // Start frontend mic capture with AEC before telling backend to connect
                startFrontendMic(selectedMicId);
                socket.emit('start_audio', {
                    device_index: index >= 0 ? index : null,
                    device_name: deviceName,
                    muted: isMuted
                });
            }, 500);
        }
    }, [isConnected, isAuthenticated, socketConnected, micDevices, selectedMicId]);

    useEffect(() => {
        // Socket IO Setup
        socket.on('connect', () => {
            setStatus('Connected');
            setSocketConnected(true);
            socket.emit('get_settings');
        });
        socket.on('disconnect', () => {
            setStatus('Disconnected');
            setSocketConnected(false);
        });
        socket.on('status', (data) => {
            addMessage('System', data.msg);
            // Update status bar based on backend messages
            if (data.msg === 'A.D.A Started') {
                setStatus('Model Connected');
            } else if (data.msg === 'A.D.A Stopped') {
                setStatus('Connected');
            }
        });
        socket.on('audio_data', (data) => {
            aiAudioDataRef.current = data.data;
            if (!isMobile) return;

            const now = performance.now();
            if (now - lastAiAudioUpdateRef.current < 50) return;
            lastAiAudioUpdateRef.current = now;
            setAiAudioData(data.data);
        });

        // Interrupt: stop all scheduled audio sources immediately
        socket.on('clear_audio', () => {
            const toStop = [...playbackSourcesRef.current];
            playbackSourcesRef.current = [];
            playbackNextTimeRef.current = 0;
            toStop.forEach(s => { try { s.stop(); } catch (_) {} });
        });

        // Raw PCM16 from Ada — play via Web Audio API so browser AEC can cancel echo from mic
        socket.on('audio_pcm', (data) => {
            try {
                // Lazy-init playback AudioContext at Ada's sample rate (24000 Hz)
                if (!playbackCtxRef.current || playbackCtxRef.current.state === 'closed') {
                    playbackCtxRef.current = new AudioContext({ sampleRate: 24000 });
                    playbackNextTimeRef.current = 0;
                }
                const ctx = playbackCtxRef.current;
                if (ctx.state === 'suspended') ctx.resume();

                // data is a Buffer/Uint8Array of PCM16 bytes
                const bytes = data instanceof ArrayBuffer ? new Uint8Array(data) : new Uint8Array(Object.values(data));
                const int16 = new Int16Array(bytes.buffer, bytes.byteOffset, bytes.byteLength / 2);
                const float32 = new Float32Array(int16.length);
                for (let i = 0; i < int16.length; i++) {
                    float32[i] = int16[i] / 32768.0;
                }

                const buffer = ctx.createBuffer(1, float32.length, 24000);
                buffer.getChannelData(0).set(float32);

                const source = ctx.createBufferSource();
                source.buffer = buffer;
                source.connect(ctx.destination);
                // Unique ID to safely target this source on interrupt
                const sourceId = crypto.randomUUID();
                source._id = sourceId;

                // Schedule gaplessly: start at next available slot
                // 10ms buffer (was 50ms) — reduced to minimize barge-in latency
                const now = ctx.currentTime;
                const startAt = Math.max(now + 0.01, playbackNextTimeRef.current);
                source.start(startAt);
                playbackNextTimeRef.current = startAt + buffer.duration;

                // Track source so we can stop it on interrupt
                playbackSourcesRef.current.push(source);
                source.onended = () => {
                    playbackSourcesRef.current = playbackSourcesRef.current.filter(s => s._id !== sourceId);
                };
            } catch (err) {
                console.error('[Audio] Playback error:', err);
            }
        });
        socket.on('auth_status', (data) => {
            console.log("Auth Status:", data);
            setIsAuthenticated(data.authenticated);
            if (data.authenticated) {
                // If authenticated, hide lock screen with animation (handled by component if visible)
                // But simpler: just hide it
                // Actually, wait for animation if it WAS visible.
                // For now, let's just assume if authenticated -> hide
                // But we want the component to invoke onAnimationComplete.
                // If we are starting up (and face auth disabled), we want it FALSE immediately.
                if (!isLockScreenVisible) {
                    // Do nothing, already hidden
                }
            } else {
                // If NOT authenticated, show lock screen
                setIsLockScreenVisible(true);
            }
        });

        socket.on('settings', (settings) => {
            console.log("[Settings] Received:", settings);
            if (settings && typeof settings.face_auth_enabled !== 'undefined') {
                setFaceAuthEnabled(settings.face_auth_enabled);
                localStorage.setItem('face_auth_enabled', settings.face_auth_enabled);
            }
            if (typeof settings.camera_flipped !== 'undefined') {
                console.log("[Settings] Camera flip set to:", settings.camera_flipped);
                setIsCameraFlipped(settings.camera_flipped);
            }
        });
        socket.on('error', (data) => {
            console.error("Socket Error:", data);
            addMessage('System', `Error: ${data.msg}`);
        });
        socket.on('cad_data', (data) => {
            console.log("Received CAD Data:", data);
            setCadData(data);
            setCadThoughts(''); // Clear thoughts when generation complete
            setShowCadWindow(true); // Open window when data arrives
            // Auto-show the window if it's hidden, clamped to viewport
            if (!elementPositions.cad) {
                const size = { w: 400, h: 400 };
                const clamped = clampToViewport({ x: window.innerWidth / 2 + 150, y: window.innerHeight / 2 }, size);
                setElementPositions(prev => ({
                    ...prev,
                    cad: clamped
                }));
            }
        });
        socket.on('cad_status', (data) => {
            console.log("Received CAD Status:", data);
            // Extract retry info from extended payload
            if (data.attempt) {
                setCadRetryInfo({
                    attempt: data.attempt,
                    maxAttempts: data.max_attempts || 3,
                    error: data.error
                });
            }
            if (data.status === 'generating' || data.status === 'retrying') {
                setCadData({ format: 'loading' });
                setShowCadWindow(true);
                if (data.status === 'generating' && data.attempt === 1) {
                    setCadThoughts(''); // Clear previous thoughts for new generation
                }
                // Auto-show the window, clamped to viewport
                if (!elementPositions.cad) {
                    const size = { w: 400, h: 400 };
                    const clamped = clampToViewport({ x: window.innerWidth / 2 + 150, y: window.innerHeight / 2 }, size);
                    setElementPositions(prev => ({
                        ...prev,
                        cad: clamped
                    }));
                }
            } else if (data.status === 'failed') {
                // Keep loading state but show error
                setCadData({ format: 'loading' });
            }
        });
        socket.on('cad_thought', (data) => {
            // Append streaming thought text
            setCadThoughts(prev => prev + data.text);
        });
        // browser_frame supprimé — le web agent Playwright a été retiré
        // Les logs execute_pc_task arrivent via terminal_output

        socket.on('terminal_output', (data) => {
            setTerminalEntries(prev => [...prev, { command: data.command, output: data.output }].slice(-100));
            setShowTerminalWindow(true);
            if (data.command === '[PC]' || data.command === '[CHAT]') {
                addMessage('System', data.output);
            }
        });

        // Handle streaming transcription
        socket.on('transcription', (data) => {
            setMessages(prev => {
                const lastMsg = prev[prev.length - 1];

                // If the last message is from the same sender, append the chunk
                if (lastMsg && lastMsg.sender === data.sender) {
                    // Create a NEW object instead of mutating (prevents React StrictMode duplication)
                    return [
                        ...prev.slice(0, -1),
                        {
                            ...lastMsg,
                            text: lastMsg.text + data.text
                        }
                    ];
                } else {
                    // New message block
                    return [...prev, {
                        sender: data.sender,
                        text: data.text,
                        time: new Date().toLocaleTimeString()
                    }];
                }
            });
        });

        // Handle tool confirmation requests
        socket.on('tool_confirmation_request', (data) => {
            console.log("Received Confirmation Request:", data);
            setConfirmationRequest(data);
        });

        // Handle Print Window Request (from CadWindow)
        socket.on('request_print_window', () => {
            setShowPrinterWindow(true);
            const size = { w: 380, h: 380 };
            const clamped = clampToViewport({ x: window.innerWidth / 2, y: window.innerHeight / 2 }, size);
            setElementPositions(prev => ({
                ...prev,
                printer: clamped
            }));
        });

        // Kasa Devices
        socket.on('kasa_devices', (devices) => {
            console.log("Kasa Devices:", devices);
            setKasaDevices(devices);
        });

        socket.on('kasa_update', (data) => {
            setKasaDevices(prev => prev.map(d => {
                if (d.ip === data.ip) {
                    // Update only fields that are not null/undefined
                    return {
                        ...d,
                        is_on: data.is_on !== null ? data.is_on : d.is_on,
                        brightness: data.brightness !== null ? data.brightness : d.brightness
                    };
                }
                return d;
            }));
        });

        socket.on('project_update', (data) => {
            console.log("Project Update:", data.project);
            setCurrentProject(data.project);
            addMessage('System', `Switched to project: ${data.project}`);
        });

        socket.on('workspace_state', (data) => {
            setWorkspaceState(data || { activeWorkspace: 'default', items: [] });
        });

        socket.on('workspace_status', (data) => {
            setWorkspaceStatus(data);
            if (data?.message) {
                addMessage('System', data.message);
            }
        });

        socket.on('workspace_activity', (data) => {
            setWorkspaceEvents(prev => [...prev, data].slice(-80));
        });

        socket.on('workspace_item_created', (data) => {
            setWorkspaceEvents(prev => [...prev, { type: 'item_created', ...data }].slice(-80));
        });

        socket.on('workspace_research_result', (data) => {
            if (!data) {
                setWorkspaceResearchResult(null);
                return;
            }
            setWorkspaceResearchResult({
                markdown: data.markdown || '',
                results: Array.isArray(data.results) ? data.results : [],
                query: data.query || '',
                depth: data.depth || 'standard',
                synthesized: Boolean(data.synthesized),
            });
        });

        // Track printer count for toolbar display
        socket.on('printer_list', (list) => {
            console.log('[PRINTERS] Count:', list.length);
            setPrinterCount(list.length);
        });

        // Slicing progress for top toolbar
        socket.on('slicing_progress', (data) => {
            console.log('[SLICING] Progress:', data);
            setSlicingStatus({
                active: data.percent < 100,
                percent: data.percent,
                message: data.message
            });
        });

        // Print status for top toolbar - track active prints
        socket.on('print_status_update', (data) => {
            console.log('[PRINT STATUS]', data);
            // Only show in toolbar if actively printing
            if (data.state && data.state.toLowerCase().includes('print')) {
                setActivePrintStatus({
                    printer: data.printer,
                    progress_percent: data.progress_percent,
                    time_elapsed: data.time_elapsed,
                    state: data.state
                });
            } else if (data.state && (data.state.toLowerCase() === 'idle' || data.state.toLowerCase() === 'standby' || data.state.toLowerCase() === 'complete')) {
                // Clear if print finished or idle
                setActivePrintStatus(null);
            }
        });



        // Get All Media Devices (Microphones, Speakers, Webcams)
        navigator.mediaDevices.enumerateDevices().then(devs => {
            const audioInputs = devs.filter(d => d.kind === 'audioinput');
            const audioOutputs = devs.filter(d => d.kind === 'audiooutput');
            const videoInputs = devs.filter(d => d.kind === 'videoinput');

            setMicDevices(audioInputs);
            setSpeakerDevices(audioOutputs);
            setWebcamDevices(videoInputs);

            // Restore saved microphone or use first available
            const savedMicId = localStorage.getItem('selectedMicId');
            if (savedMicId && audioInputs.some(d => d.deviceId === savedMicId)) {
                setSelectedMicId(savedMicId);
            } else if (audioInputs.length > 0) {
                setSelectedMicId(audioInputs[0].deviceId);
            }

            // Restore saved speaker or use first available
            const savedSpeakerId = localStorage.getItem('selectedSpeakerId');
            if (savedSpeakerId && audioOutputs.some(d => d.deviceId === savedSpeakerId)) {
                setSelectedSpeakerId(savedSpeakerId);
            } else if (audioOutputs.length > 0) {
                setSelectedSpeakerId(audioOutputs[0].deviceId);
            }

            // Restore saved webcam, skipping virtual cameras
            const virtualKeywords = /obs|virtual|snap|manycam|xsplit|ndi|dshow/i;
            const savedWebcamId = localStorage.getItem('selectedWebcamId');
            const savedDevice = videoInputs.find(d => d.deviceId === savedWebcamId);
            const isVirtual = savedDevice && virtualKeywords.test(savedDevice.label);

            if (savedWebcamId && savedDevice && !isVirtual) {
                // Saved device exists and is a real camera
                setSelectedWebcamId(savedWebcamId);
            } else {
                // No valid saved camera (or it was OBS) — pick first real camera
                if (isVirtual) localStorage.removeItem('selectedWebcamId');
                const realCam = videoInputs.find(d => !virtualKeywords.test(d.label));
                if (realCam || videoInputs.length > 0) {
                    setSelectedWebcamId((realCam || videoInputs[0]).deviceId);
                }
            }
        });

        socket.on('vision_mode', (data) => {
            setIsScreenMode(data.mode === 'screen');
        });
        socket.on('hand_control_status', (data) => {
            if (!data) return;
            if (typeof data.enabled === 'boolean') {
                setIsHandTrackingEnabled(data.enabled);
            }
            addMessage('System', data.message || (data.enabled ? 'Hand OS control enabled' : 'Hand OS control disabled'));
        });

        return () => {
            socket.off('connect');
            socket.off('disconnect');
            socket.off('status');
            socket.off('audio_data');
            socket.off('audio_pcm');
            socket.off('clear_audio');
            socket.off('cad_data');
            socket.off('cad_thought');
            socket.off('cad_status');

            socket.off('transcription');
            socket.off('tool_confirmation_request');
            socket.off('kasa_devices');
            socket.off('kasa_update');
            socket.off('project_update');
            socket.off('workspace_state');
            socket.off('workspace_status');
            socket.off('workspace_activity');
            socket.off('workspace_item_created');
            socket.off('workspace_research_result');
            socket.off('printer_list');
            socket.off('slicing_progress');
            socket.off('print_status_update');
            socket.off('error');
            socket.off('vision_mode');
            socket.off('hand_control_status');

            stopMicVisualizer();
            stopVideo();
        };
    }, []);

    // Initial check in case we are already connected (fix race condition)
    useEffect(() => {
        if (socket.connected) {
            setStatus('Connected');
            socket.emit('get_settings');
        }
    }, []);

    // Persist device selections to localStorage when they change
    useEffect(() => {
        if (selectedMicId) {
            localStorage.setItem('selectedMicId', selectedMicId);
            console.log('[Settings] Saved microphone:', selectedMicId);
        }
    }, [selectedMicId]);

    useEffect(() => {
        if (
            isConnected &&
            socketConnected &&
            selectedMicId &&
            aecStreamRef.current &&
            aecDeviceIdRef.current !== selectedMicId
        ) {
            console.log('[AEC] Microphone changed while connected, restarting capture.');
            startFrontendMic(selectedMicId);
        }
    }, [isConnected, socketConnected, selectedMicId]);

    useEffect(() => {
        if (selectedSpeakerId) {
            localStorage.setItem('selectedSpeakerId', selectedSpeakerId);
            console.log('[Settings] Saved speaker:', selectedSpeakerId);
        }
    }, [selectedSpeakerId]);

    useEffect(() => {
        if (!selectedWebcamId) return;
        localStorage.setItem('selectedWebcamId', selectedWebcamId);
        console.log('[Settings] Saved webcam:', selectedWebcamId);
        // If video is currently running, restart it with the new camera
        if (isVideoOnRef.current) {
            stopVideo();
            // Small delay to let the old stream release the device
            setTimeout(() => startVideo(), 200);
        }
    }, [selectedWebcamId]);

    // Start/Stop Mic Visualizer
    useEffect(() => {
        if (selectedMicId) {
            startMicVisualizer(selectedMicId);
        }
    }, [selectedMicId]);

    const stopFrontendMic = () => {
        if (aecProcessorRef.current) { aecProcessorRef.current.disconnect(); aecProcessorRef.current = null; }
        if (aecAudioCtxRef.current) { aecAudioCtxRef.current.close(); aecAudioCtxRef.current = null; }
        if (aecStreamRef.current) { aecStreamRef.current.getTracks().forEach(t => t.stop()); aecStreamRef.current = null; }
        aecDeviceIdRef.current = null;
        if (playbackCtxRef.current) { playbackCtxRef.current.close(); playbackCtxRef.current = null; }
        playbackNextTimeRef.current = 0;
    };

    const startFrontendMic = async (deviceId) => {
        stopFrontendMic();
        try {
            const constraints = {
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true,
                    channelCount: 1,
                    ...(deviceId ? { deviceId: { exact: deviceId } } : {})
                }
            };
            const stream = await navigator.mediaDevices.getUserMedia(constraints);
            aecStreamRef.current = stream;
            aecDeviceIdRef.current = deviceId || null;

            // AudioContext at 16kHz — browser resamples from device native rate
            const ctx = new AudioContext({ sampleRate: 16000 });
            aecAudioCtxRef.current = ctx;

            const source = ctx.createMediaStreamSource(stream);
            // ScriptProcessorNode: 2048 samples @ 16kHz = 128ms per chunk
            const processor = ctx.createScriptProcessor(2048, 1, 1);
            aecProcessorRef.current = processor;

            processor.onaudioprocess = (e) => {
                const float32 = e.inputBuffer.getChannelData(0);
                // Convert Float32 → PCM Int16
                const int16 = new Int16Array(float32.length);
                for (let i = 0; i < float32.length; i++) {
                    const s = Math.max(-1, Math.min(1, float32[i]));
                    int16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
                }
                socket.emit('mic_audio_chunk', { data: Array.from(new Uint8Array(int16.buffer)) });
            };

            // ScriptProcessor requires a destination to fire, but we must NOT route mic to speakers.
            // Connect to a silent GainNode (gain=0) as a dead-end.
            const silentGain = ctx.createGain();
            silentGain.gain.value = 0;
            silentGain.connect(ctx.destination);

            source.connect(processor);
            processor.connect(silentGain);
            console.log('[AEC] Frontend mic capture started with echoCancellation: true, sampleRate:', ctx.sampleRate);
        } catch (err) {
            console.error('[AEC] Failed to start frontend mic capture:', err);
        }
    };

    const startMicVisualizer = async (deviceId) => {
        stopMicVisualizer();
        try {
            const stream = await navigator.mediaDevices.getUserMedia({
                audio: { deviceId: { exact: deviceId } }
            });
            micVisualizerStreamRef.current = stream;

            audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)();
            analyserRef.current = audioContextRef.current.createAnalyser();
            analyserRef.current.fftSize = 64;

            sourceRef.current = audioContextRef.current.createMediaStreamSource(stream);
            sourceRef.current.connect(analyserRef.current);

            let micFrameCount = 0;
            const updateMicData = () => {
                if (!analyserRef.current) return;
                micFrameCount++;
                if (micFrameCount % 3 === 0) { // throttle to ~20fps instead of 60fps
                    const dataArray = new Uint8Array(analyserRef.current.frequencyBinCount);
                    analyserRef.current.getByteFrequencyData(dataArray);
                    const values = Array.from(dataArray);
                    micAudioDataRef.current = values;
                    if (isMobile) {
                        setMicAudioData(values);
                    }
                }
                animationFrameRef.current = requestAnimationFrame(updateMicData);
            };

            updateMicData();
        } catch (err) {
            console.error("Error accessing microphone:", err);
        }
    };

    const stopMicVisualizer = () => {
        if (animationFrameRef.current) cancelAnimationFrame(animationFrameRef.current);
        if (sourceRef.current) sourceRef.current.disconnect();
        if (audioContextRef.current) audioContextRef.current.close();
        if (micVisualizerStreamRef.current) {
            micVisualizerStreamRef.current.getTracks().forEach(track => track.stop());
            micVisualizerStreamRef.current = null;
        }
        animationFrameRef.current = null;
        sourceRef.current = null;
        audioContextRef.current = null;
        analyserRef.current = null;
    };

    const startVideo = async () => {
        if (isVideoStartingRef.current || isVideoOnRef.current) {
            return;
        }

        isVideoStartingRef.current = true;
        try {
            // 720p/30fps is enough for hand tracking and avoids saturating Electron.
            const constraints = {
                video: {
                    width: { ideal: 1280 },
                    height: { ideal: 720 },
                    frameRate: { ideal: 30, max: 30 },
                    aspectRatio: 16 / 9
                }
            };

            // Use selected webcam if available
            if (selectedWebcamId) {
                constraints.video.deviceId = { exact: selectedWebcamId };
            }

            const stream = await navigator.mediaDevices.getUserMedia(constraints);
            videoStreamRef.current = stream;
            if (videoRef.current) {
                videoRef.current.srcObject = stream;
                await videoRef.current.play();
            }

            // Initialize the transmission canvas
            if (!transmissionCanvasRef.current) {
                transmissionCanvasRef.current = document.createElement('canvas');
                transmissionCanvasRef.current.width = 640;
                transmissionCanvasRef.current.height = 360;
                console.log("Initialized transmission canvas (640x360)");
            }

            setIsVideoOn(true);
            isVideoOnRef.current = true; // Update ref for loop

            console.log("Starting video loop with webcam:", selectedWebcamId || "default");
            if (videoAnimationFrameRef.current) {
                cancelAnimationFrame(videoAnimationFrameRef.current);
            }
            videoAnimationFrameRef.current = requestAnimationFrame(predictWebcam);

        } catch (err) {
            console.error("Error accessing camera:", err);
            addMessage('System', 'Error accessing camera');
            stopVideo();
        } finally {
            isVideoStartingRef.current = false;
        }
    };

    const predictWebcam = () => {
        // Use ref for checking state to avoid closure staleness
        if (!videoRef.current || !canvasRef.current || !isVideoOnRef.current) {
            return;
        }

        // Check if video has valid dimensions to prevent MediaPipe crash
        if (videoRef.current.readyState < 2 || videoRef.current.videoWidth === 0 || videoRef.current.videoHeight === 0) {
            videoAnimationFrameRef.current = requestAnimationFrame(predictWebcam);
            return;
        }

        // 1. Draw Video to Local Display Canvas (Native Resolution)
        const ctx = canvasRef.current.getContext('2d');

        // Ensure canvas matches video dimensions
        if (canvasRef.current.width !== videoRef.current.videoWidth || canvasRef.current.height !== videoRef.current.videoHeight) {
            canvasRef.current.width = videoRef.current.videoWidth;
            canvasRef.current.height = videoRef.current.videoHeight;
        }

        ctx.drawImage(videoRef.current, 0, 0, canvasRef.current.width, canvasRef.current.height);
        if (isHandTrackingEnabledRef.current) {
            drawHandDebugOverlay(ctx, canvasRef.current.width, canvasRef.current.height, handDebug);
        }

        // 2. Send Frame to Backend (Throttled & Resized)
        // Only send if connected
        if (isConnected) {
            const now = performance.now();
            const frameSendIntervalMs = isHandTrackingEnabledRef.current ? 1000 : 500;
            const shouldSendFrame = now - lastVideoFrameSentRef.current >= frameSendIntervalMs;
            if (shouldSendFrame && !videoBlobInFlightRef.current) {
                const transCanvas = transmissionCanvasRef.current;
                if (transCanvas) {
                    videoBlobInFlightRef.current = true;
                    lastVideoFrameSentRef.current = now;

                    const transCtx = transCanvas.getContext('2d');
                    transCtx.drawImage(videoRef.current, 0, 0, transCanvas.width, transCanvas.height);

                    transCanvas.toBlob((blob) => {
                        videoBlobInFlightRef.current = false;
                        if (blob && isVideoOnRef.current && socket.connected) {
                            socket.emit('video_frame', { image: blob });
                        }
                    }, 'image/jpeg', 0.45);
                }
            }
        }


        // 3. Hand Tracking
        let startTimeMs = performance.now();
        // Use Ref for toggle check
        if (
            isHandTrackingEnabledRef.current &&
            handLandmarkerRef.current &&
            videoRef.current.currentTime !== lastVideoTimeRef.current &&
            startTimeMs - lastHandDetectionRef.current >= 66
        ) {
            lastHandDetectionRef.current = startTimeMs;
            lastVideoTimeRef.current = videoRef.current.currentTime;
            let results;
            try {
                results = handLandmarkerRef.current.detectForVideo(videoRef.current, startTimeMs);
            } catch (err) {
                console.error("[HandTracking] detectForVideo error:", err);
                videoAnimationFrameRef.current = requestAnimationFrame(predictWebcam);
                return;
            }

            // Log every 100 frames to confirm loop is running
            if (frameCountRef.current % 100 === 0) {
                console.log("Tracking loop running... Last result:", results.landmarks.length > 0 ? "Hand Found" : "No Hand");
            }

            if (results.landmarks && results.landmarks.length > 0) {
                const landmarks = results.landmarks[0];
                const indexTip = landmarks[8];
                const thumbTip = landmarks[4];
                const middleTip = landmarks[12];
                const wrist = landmarks[0];
                const viewport = { width: window.innerWidth, height: window.innerHeight };
                const osControlActive = socket.connected;

                const dist2d = (a, b) => Math.sqrt(
                    Math.pow(a.x - b.x, 2) +
                    Math.pow(a.y - b.y, 2)
                );
                const dist3d = (a, b) => Math.sqrt(
                    Math.pow(a.x - b.x, 2) +
                    Math.pow(a.y - b.y, 2) +
                    Math.pow((a.z || 0) - (b.z || 0), 2)
                );
                const isFingerExtendedByTip = (tipIdx, pipIdx) => landmarks[tipIdx].y < landmarks[pipIdx].y - 0.012;
                const isFingerOpenByWrist = (tipIdx, mcpIdx) => (
                    dist2d(landmarks[tipIdx], wrist) > dist2d(landmarks[mcpIdx], wrist) * 1.22
                );
                const isFingerFolded = (tipIdx, pipIdx, mcpIdx) => {
                    const tip = landmarks[tipIdx];
                    const pip = landmarks[pipIdx];
                    const mcp = landmarks[mcpIdx];
                    return tip.y > pip.y + 0.01 || dist2d(tip, wrist) < dist2d(mcp, wrist) * 1.12;
                };

                const indexExtended = isFingerExtendedByTip(8, 6) && isFingerOpenByWrist(8, 5);
                const middleExtended = isFingerExtendedByTip(12, 10) && isFingerOpenByWrist(12, 9);
                const ringExtended = isFingerExtendedByTip(16, 14) && isFingerOpenByWrist(16, 13);
                const pinkyExtended = isFingerExtendedByTip(20, 18) && isFingerOpenByWrist(20, 17);
                const openPalm = indexExtended && middleExtended && ringExtended && pinkyExtended;

                const rawIndexPoint = {
                    x: isCameraFlippedRef.current ? (1 - indexTip.x) : indexTip.x,
                    y: indexTip.y,
                };
                const boxedIndexPoint = clampPointToInteractionBox(
                    rawIndexPoint,
                    DEFAULT_HAND_CONTROL_CONFIG.interactionBox
                );
                const filteredPoint = handPointFilterRef.current.filter(
                    { x: boxedIndexPoint.x, y: boxedIndexPoint.y },
                    startTimeMs
                );
                const rawCursor = {
                    x: boxedIndexPoint.x * viewport.width,
                    y: boxedIndexPoint.y * viewport.height,
                };

                const wristRawX = isCameraFlippedRef.current ? (1 - wrist.x) : wrist.x;
                const wristBox = clampPointToInteractionBox(
                    { x: wristRawX, y: wrist.y },
                    DEFAULT_HAND_CONTROL_CONFIG.interactionBox
                );
                const wristScreenX = wristBox.x * viewport.width;
                const wristScreenY = wristBox.y * viewport.height;

                const palmSize = Math.max(
                    dist2d(wrist, landmarks[5]),
                    dist2d(wrist, landmarks[9]),
                    0.001
                );
                const foldedCount = [
                    isFingerFolded(8, 6, 5),
                    isFingerFolded(12, 10, 9),
                    isFingerFolded(16, 14, 13),
                    isFingerFolded(20, 18, 17)
                ].filter(Boolean).length;
                const fistActive = foldedCount >= 4 && !indexExtended && !middleExtended && !ringExtended && !pinkyExtended;
                const pinchDistance = Math.min(dist2d(middleTip, thumbTip), dist3d(middleTip, thumbTip));
                const pinchRatio = pinchDistance / palmSize;
                const pinchClosed = (
                    pinchRatio < DEFAULT_HAND_CONTROL_CONFIG.gestures.pinchStartRatio &&
                    indexExtended &&
                    !fistActive
                );
                const pinchReleased = (
                    pinchRatio > DEFAULT_HAND_CONTROL_CONFIG.gestures.pinchEndRatio ||
                    !indexExtended
                );
                const indexMiddleTipDistance = dist2d(indexTip, middleTip);
                const scrollActive = (
                    indexExtended &&
                    middleExtended &&
                    !ringExtended &&
                    !pinkyExtended &&
                    indexMiddleTipDistance > palmSize * 0.18 &&
                    !pinchClosed
                );

                const gestureSnapshot = gestureMachineRef.current.update({
                    handPresent: true,
                    clutch: openPalm && !pinchClosed,
                    drag: fistActive,
                    scroll: scrollActive,
                    pinch: pinchClosed && !pinchReleased,
                }, startTimeMs);
                const activeState = gestureSnapshot.state;
                const clutchActive = activeState === 'CLUTCH';
                const isScroll = activeState === 'SCROLL';
                const isFist = activeState === 'DRAG';
                const isPinchCandidate = activeState === 'CLICK_CANDIDATE';

                handOsGestureRef.current = activeState.toLowerCase();

                if (socket.connected && openPalm && (activeState === 'CLUTCH' || activeState === 'TRACKING')) {
                    const nowForSwitch = performance.now();
                    const swipeStart = handOsSwipeStartRef.current;
                    if (swipeStart.x === null || nowForSwitch - swipeStart.t > 650) {
                        handOsSwipeStartRef.current = { x: wristScreenX, y: wristScreenY, t: nowForSwitch };
                    } else {
                        const dx = wristScreenX - swipeStart.x;
                        const dy = wristScreenY - swipeStart.y;
                        const horizontalEnough = Math.abs(dx) > viewport.width * 0.20;
                        const verticalStable = Math.abs(dy) < viewport.height * 0.18;
                        const cooldownDone = nowForSwitch - lastHandOsWindowSwitchAtRef.current > 950;
                        if (horizontalEnough && verticalStable && cooldownDone) {
                            lastHandOsWindowSwitchAtRef.current = nowForSwitch;
                            socket.emit('hand_control_event', {
                                type: 'window_switch',
                                direction: dx > 0 ? 'next' : 'previous'
                            });
                            handOsSwipeStartRef.current = { x: null, y: null, t: 0 };
                        }
                    }
                } else {
                    handOsSwipeStartRef.current = { x: null, y: null, t: 0 };
                }

                if (gestureSnapshot.action === 'drag_start') {
                    if (socket.connected && !isHandOsDraggingRef.current) {
                        isHandOsDraggingRef.current = true;
                        socket.emit('hand_control_event', { type: 'mouse_down' });
                    }
                    lastWristPosRef.current = { x: wristScreenX, y: wristScreenY };
                } else if (gestureSnapshot.action === 'drag_end') {
                    if (socket.connected && isHandOsDraggingRef.current) {
                        socket.emit('hand_control_event', { type: 'mouse_up' });
                        isHandOsDraggingRef.current = false;
                    }
                    activeDragElementRef.current = null;
                } else if (gestureSnapshot.action === 'click') {
                    cursorEngineRef.current.freeze(startTimeMs);
                    if (socket.connected) {
                        socket.emit('hand_control_event', { type: 'click' });
                    } else {
                        const el = document.elementFromPoint(lastCursorPosRef.current.x, lastCursorPosRef.current.y);
                        if (el) {
                            const clickable = el.closest('button, input, a, [role="button"]');
                            if (clickable && typeof clickable.click === 'function') {
                                clickable.click();
                            } else if (typeof el.click === 'function') {
                                el.click();
                            }
                        }
                    }
                }

                const cursorUpdate = cursorEngineRef.current.update({
                    point: filteredPoint,
                    timestampMs: startTimeMs,
                    viewport,
                    sensitivity: cursorSensitivityRef.current,
                    clutch: clutchActive || isScroll || isFist,
                });

                let finalX = cursorUpdate.x;
                let finalY = cursorUpdate.y;
                const SNAP_THRESHOLD = 50;
                const UNSNAP_THRESHOLD = 100;

                if (osControlActive && snapStateRef.current.isSnapped) {
                    if (snapStateRef.current.element) {
                        snapStateRef.current.element.classList.remove('snap-highlight');
                        snapStateRef.current.element.style.boxShadow = '';
                        snapStateRef.current.element.style.backgroundColor = '';
                        snapStateRef.current.element.style.borderColor = '';
                    }
                    snapStateRef.current = { isSnapped: false, element: null, snapPos: { x: 0, y: 0 } };
                }

                if (!osControlActive && snapStateRef.current.isSnapped) {
                    const dist = Math.sqrt(
                        Math.pow(finalX - snapStateRef.current.snapPos.x, 2) +
                        Math.pow(finalY - snapStateRef.current.snapPos.y, 2)
                    );

                    if (dist > UNSNAP_THRESHOLD) {
                        if (snapStateRef.current.element) {
                            snapStateRef.current.element.classList.remove('snap-highlight');
                            snapStateRef.current.element.style.boxShadow = '';
                            snapStateRef.current.element.style.backgroundColor = '';
                            snapStateRef.current.element.style.borderColor = '';
                        }
                        snapStateRef.current = { isSnapped: false, element: null, snapPos: { x: 0, y: 0 } };
                    } else {
                        finalX = snapStateRef.current.snapPos.x;
                        finalY = snapStateRef.current.snapPos.y;
                    }
                } else if (!osControlActive && !clutchActive && !isFist) {
                    const targets = Array.from(document.querySelectorAll('button, input, select, .draggable'));
                    let closest = null;
                    let minDist = Infinity;

                    for (const el of targets) {
                        const rect = el.getBoundingClientRect();
                        const centerX = rect.left + rect.width / 2;
                        const centerY = rect.top + rect.height / 2;
                        const dist = Math.sqrt(Math.pow(finalX - centerX, 2) + Math.pow(finalY - centerY, 2));

                        if (dist < minDist) {
                            minDist = dist;
                            closest = { el, centerX, centerY };
                        }
                    }

                    if (closest && minDist < SNAP_THRESHOLD) {
                        snapStateRef.current = {
                            isSnapped: true,
                            element: closest.el,
                            snapPos: { x: closest.centerX, y: closest.centerY }
                        };
                        finalX = closest.centerX;
                        finalY = closest.centerY;
                        closest.el.classList.add('snap-highlight');
                        closest.el.style.boxShadow = '0 0 20px rgba(34, 211, 238, 0.6)';
                        closest.el.style.backgroundColor = 'rgba(6, 182, 212, 0.2)';
                        closest.el.style.borderColor = 'rgba(34, 211, 238, 1)';
                    }
                }

                if (cursorElRef.current) {
                    cursorElRef.current.style.left = finalX + 'px';
                    cursorElRef.current.style.top = finalY + 'px';
                    if (isPinchCandidate) {
                        cursorElRef.current.style.backgroundColor = 'rgba(34,211,238,1)';
                        cursorElRef.current.style.boxShadow = '0 0 15px rgba(34,211,238,0.8)';
                        cursorElRef.current.style.transform = 'translate(-50%,-50%) scale(0.75)';
                    } else if (clutchActive) {
                        cursorElRef.current.style.backgroundColor = 'rgba(250,204,21,0.9)';
                        cursorElRef.current.style.boxShadow = '0 0 14px rgba(250,204,21,0.35)';
                        cursorElRef.current.style.transform = 'translate(-50%,-50%) scale(0.9)';
                    } else {
                        cursorElRef.current.style.backgroundColor = '';
                        cursorElRef.current.style.boxShadow = '0 0 10px rgba(34,211,238,0.3)';
                        cursorElRef.current.style.transform = 'translate(-50%,-50%)';
                    }
                }

                isPinchingRef.current = isPinchCandidate;

                if (socket.connected && !isScroll && !clutchActive) {
                    const nowForOs = performance.now();
                    if (nowForOs - lastHandOsMoveSentRef.current >= 45) {
                        lastHandOsMoveSentRef.current = nowForOs;
                        socket.emit('hand_control_event', {
                            type: 'move',
                            x: finalX / viewport.width,
                            y: finalY / viewport.height
                        });
                    }
                }

                if (isScroll && socket.connected) {
                    if (lastHandOsScrollYRef.current === null) {
                        lastHandOsScrollYRef.current = finalY;
                    } else {
                        const nowForScroll = performance.now();
                        const scrollDelta = Math.round(
                            (lastHandOsScrollYRef.current - finalY) /
                            DEFAULT_HAND_CONTROL_CONFIG.gestures.scrollStepPx
                        );
                        if (Math.abs(scrollDelta) >= 1 && nowForScroll - lastHandOsScrollSentRef.current >= 80) {
                            lastHandOsScrollSentRef.current = nowForScroll;
                            socket.emit('hand_control_event', {
                                type: 'scroll',
                                dy: Math.max(-10, Math.min(10, scrollDelta))
                            });
                            lastHandOsScrollYRef.current = finalY;
                        }
                    }
                } else {
                    lastHandOsScrollYRef.current = null;
                }

                if (!osControlActive && isFist) {
                    if (!activeDragElementRef.current) {
                        const draggableElements = ['cad', 'browser', 'kasa', 'printer'];
                        for (const id of draggableElements) {
                            const el = document.getElementById(id);
                            if (el) {
                                const rect = el.getBoundingClientRect();
                                if (finalX >= rect.left && finalX <= rect.right && finalY >= rect.top && finalY <= rect.bottom) {
                                    activeDragElementRef.current = id;
                                    bringToFront(id);
                                    lastWristPosRef.current = { x: wristScreenX, y: wristScreenY };
                                    break;
                                }
                            }
                        }
                    }

                    if (activeDragElementRef.current) {
                        const dx = wristScreenX - lastWristPosRef.current.x;
                        const dy = wristScreenY - lastWristPosRef.current.y;
                        if (Math.abs(dx) > 0.5 || Math.abs(dy) > 0.5) {
                            updateElementPosition(activeDragElementRef.current, dx, dy);
                        }
                        lastWristPosRef.current = { x: wristScreenX, y: wristScreenY };
                    }
                } else if (!isFist) {
                    activeDragElementRef.current = null;
                }

                if (activeDragElementRef.current !== lastActiveDragElementRef.current) {
                    setActiveDragElement(activeDragElementRef.current);
                    lastActiveDragElementRef.current = activeDragElementRef.current;
                }

                lastCursorPosRef.current = { x: finalX, y: finalY };

                if (startTimeMs - lastHandDebugAtRef.current >= 100) {
                    lastHandDebugAtRef.current = startTimeMs;
                    setHandDebug({
                        state: activeState,
                        pinchRatio,
                        confidence: gestureSnapshot.confidence,
                        clutch: clutchActive,
                        rawCursor,
                        filteredCursor: { x: finalX, y: finalY },
                        interactionInside: boxedIndexPoint.inside,
                        deadZone: DEFAULT_HAND_CONTROL_CONFIG.cursor.deadZone,
                    });
                }

                drawSkeleton(ctx, landmarks);
            } else {
                pinchFramesRef.current = 0;
                fistFramesRef.current = 0;
                isPinchingRef.current = false;
                lastHandOsScrollYRef.current = null;
                handOsGestureRef.current = 'idle';
                handOsGestureCandidateRef.current = 'idle';
                handOsGestureFramesRef.current = 0;
                handOsReleaseFramesRef.current = 0;
                handOsSwipeStartRef.current = { x: null, y: null, t: 0 };
                gestureMachineRef.current.reset();
                handPointFilterRef.current.reset();
                cursorEngineRef.current.previousPoint = null;
                if (isHandOsDraggingRef.current && socket.connected) {
                    isHandOsDraggingRef.current = false;
                    socket.emit('hand_control_event', { type: 'mouse_up' });
                }
                activeDragElementRef.current = null;
                if (lastActiveDragElementRef.current !== null) {
                    setActiveDragElement(null);
                    lastActiveDragElementRef.current = null;
                }
                if (startTimeMs - lastHandDebugAtRef.current >= 100) {
                    lastHandDebugAtRef.current = startTimeMs;
                    setHandDebug(prev => ({ ...prev, state: 'IDLE', confidence: 0, clutch: false, interactionInside: false }));
                }
            }

        }

        // 4. FPS Calculation
        const now = performance.now();
        frameCountRef.current++;
        if (now - lastFrameTimeRef.current >= 1000) {
            setFps(frameCountRef.current);
            frameCountRef.current = 0;
            lastFrameTimeRef.current = now;
        }

        if (isVideoOnRef.current) {
            videoAnimationFrameRef.current = requestAnimationFrame(predictWebcam);
        }
    };

    const drawSkeleton = (ctx, landmarks) => {
        ctx.strokeStyle = '#00FFFF';
        ctx.lineWidth = 2;

        // Connections
        const connections = HandLandmarker.HAND_CONNECTIONS;
        for (const connection of connections) {
            const start = landmarks[connection.start];
            const end = landmarks[connection.end];
            ctx.beginPath();
            ctx.moveTo(start.x * canvasRef.current.width, start.y * canvasRef.current.height);
            ctx.lineTo(end.x * canvasRef.current.width, end.y * canvasRef.current.height);
            ctx.stroke();
        }
    };

    const drawHandDebugOverlay = (ctx, canvasWidth, canvasHeight, debug) => {
        const box = DEFAULT_HAND_CONTROL_CONFIG.interactionBox;
        const left = box.left * canvasWidth;
        const top = box.top * canvasHeight;
        const width = (box.right - box.left) * canvasWidth;
        const height = (box.bottom - box.top) * canvasHeight;

        ctx.save();
        ctx.strokeStyle = 'rgba(250, 204, 21, 0.8)';
        ctx.lineWidth = 2;
        ctx.setLineDash([8, 6]);
        ctx.strokeRect(left, top, width, height);
        ctx.setLineDash([]);

        if (debug?.rawCursor) {
            ctx.fillStyle = 'rgba(248, 113, 113, 0.95)';
            ctx.beginPath();
            ctx.arc(
                (debug.rawCursor.x / window.innerWidth) * canvasWidth,
                (debug.rawCursor.y / window.innerHeight) * canvasHeight,
                5,
                0,
                Math.PI * 2
            );
            ctx.fill();
        }

        if (debug?.filteredCursor) {
            ctx.fillStyle = 'rgba(34, 211, 238, 0.95)';
            ctx.beginPath();
            ctx.arc(
                (debug.filteredCursor.x / window.innerWidth) * canvasWidth,
                (debug.filteredCursor.y / window.innerHeight) * canvasHeight,
                6,
                0,
                Math.PI * 2
            );
            ctx.fill();
        }
        ctx.restore();
    };

    const stopVideo = () => {
        if (videoAnimationFrameRef.current) {
            cancelAnimationFrame(videoAnimationFrameRef.current);
            videoAnimationFrameRef.current = null;
        }

        if (videoStreamRef.current) {
            videoStreamRef.current.getTracks().forEach(track => track.stop());
            videoStreamRef.current = null;
        }

        if (videoRef.current && videoRef.current.srcObject) {
            videoRef.current.srcObject.getTracks().forEach(track => track.stop());
            videoRef.current.srcObject = null;
        }
        setIsVideoOn(false);
        isVideoOnRef.current = false; // Update ref
        isVideoStartingRef.current = false;
        pinchFramesRef.current = 0;
        fistFramesRef.current = 0;
        isPinchingRef.current = false;
        handOsGestureRef.current = 'idle';
        handOsGestureCandidateRef.current = 'idle';
        handOsGestureFramesRef.current = 0;
        handOsReleaseFramesRef.current = 0;
        handOsSwipeStartRef.current = { x: null, y: null, t: 0 };
        lastHandOsScrollYRef.current = null;
        handPointFilterRef.current.reset();
        cursorEngineRef.current.reset({ width: window.innerWidth, height: window.innerHeight });
        gestureMachineRef.current.reset();
        setHandDebug(prev => ({ ...prev, state: 'IDLE', confidence: 0, clutch: false, interactionInside: false }));
        if (isHandOsDraggingRef.current && socket.connected) {
            socket.emit('hand_control_event', { type: 'mouse_up' });
        }
        isHandOsDraggingRef.current = false;
        activeDragElementRef.current = null;
        lastActiveDragElementRef.current = null;
        setActiveDragElement(null);
        videoBlobInFlightRef.current = false;
        lastVideoFrameSentRef.current = 0;
        lastVideoTimeRef.current = -1;
        setFps(0);
    };

    const toggleVideo = () => {
        if (isVideoOn) {
            stopVideo();
            if (socket) {
                socket.emit('set_vision_mode', { mode: 'none' });
            }
        } else {
            if (isScreenMode) {
                setIsScreenMode(false);
            }
            startVideo();
            if (socket) {
                socket.emit('set_vision_mode', { mode: 'camera' });
            }
        }
    };

    const toggleHandTracking = () => {
        const enabling = !isHandTrackingEnabled;
        setIsHandTrackingEnabled(enabling);
        if (socket.connected) {
            socket.emit('hand_control_toggle', { enabled: enabling });
        }
        if (enabling && !isVideoOn) {
            startVideo();
        }
        if (enabling) {
            ensureHandLandmarker();
        }
    };

    const toggleScreenMode = () => {
        const newMode = !isScreenMode;
        setIsScreenMode(newMode);
        if (newMode && isVideoOn) {
            stopVideo();
        }
        if (socket) {
            socket.emit('set_vision_mode', { mode: newMode ? 'screen' : 'none' });
        }
    };

    const addMessage = (sender, text) => {
        setMessages(prev => [...prev, { sender, text, time: new Date().toLocaleTimeString() }]);
    };

    const togglePower = () => {
        if (isConnected) {
            stopFrontendMic();
            socket.emit('stop_audio');
            setIsConnected(false);
            hasAutoConnectedRef.current = false; // Reset so auto-connect can fire again on next power-on
            setIsMuted(false); // Reset mute state
        } else {
            const index = micDevices.findIndex(d => d.deviceId === selectedMicId);
            const queryDevice = micDevices.find(d => d.deviceId === selectedMicId);
            const deviceName = queryDevice ? queryDevice.label : null;
            startFrontendMic(selectedMicId);
            socket.emit('start_audio', {
                device_index: index >= 0 ? index : null,
                device_name: deviceName,
                muted: false
            });
            setIsConnected(true);
            setIsMuted(false); // Start unmuted
        }
    };

    const toggleMute = () => {
        if (!isConnected) return; // Can't mute if not connected

        if (isMuted) {
            socket.emit('resume_audio');
            setIsMuted(false);
        } else {
            socket.emit('pause_audio');
            setIsMuted(true);
        }
    };

    const handleSend = (e) => {
        if (e.key === 'Enter' && inputValue.trim()) {
            socket.emit('user_input', { text: inputValue });
            addMessage('You', inputValue);
            setInputValue('');
        }
    };

    const handleMinimize = () => ipcRenderer.send('window-minimize');
    const handleMaximize = () => ipcRenderer.send('window-maximize');

    // Close Application - memory is now actively saved to project, no prompt needed
    const handleCloseRequest = () => {
        // Emit shutdown signal to backend for graceful shutdown
        // Use volatile emit with timeout fallback to ensure window closes even if server is unresponsive
        const closeWindow = () => ipcRenderer.send('window-close');

        if (socket.connected) {
            console.log('[APP] Sending shutdown signal to backend...');
            socket.emit('shutdown', {}, (ack) => {
                // This callback may not be called if server uses os._exit
                console.log('[APP] Shutdown acknowledged');
                closeWindow();
            });
            // Fallback: close after 500ms if ack doesn't come back
            setTimeout(closeWindow, 500);
        } else {
            // Socket not connected, just close
            closeWindow();
        }
    };

    const handleFileUpload = (e) => {
        const file = e.target.files[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = (event) => {
            try {
                const textContent = event.target.result;
                // Just send the text content directly
                if (typeof textContent === 'string' && textContent.length > 0) {
                    socket.emit('upload_memory', { memory: textContent });
                    addMessage('System', 'Uploading memory...');
                } else {
                    addMessage('System', 'Empty or invalid memory file');
                }
            } catch (err) {
                console.error("Error reading file:", err);
                addMessage('System', 'Error reading memory file');
            }
        };
        reader.readAsText(file);
    };

    // handleCancelClose removed - no longer using memory prompt

    const handleConfirmTool = () => {
        if (confirmationRequest) {
            socket.emit('confirm_tool', { id: confirmationRequest.id, confirmed: true });
            setConfirmationRequest(null);
        }
    };

    const handleDenyTool = () => {
        if (confirmationRequest) {
            socket.emit('confirm_tool', { id: confirmationRequest.id, confirmed: false });
            setConfirmationRequest(null);
        }
    };

    // Updated Bounds Checking Logic
    const updateElementPosition = (id, dx, dy) => {
        setElementPositions(prev => {
            const currentPos = prev[id];
            const size = elementSizes[id] || { w: 100, h: 100 }; // Fallback
            let newX = currentPos.x + dx;
            let newY = currentPos.y + dy;

            // Bounds Logic
            // Depends on anchor point.
            // Visualizer, Tools, Cad, Browser, Kasa: translate(-50%, -50%) -> Center Anchor
            // Chat: translate(-50%, 0) -> Top-Center Anchor
            // Video: Top-Left Anchor (default div)

            const width = window.innerWidth;
            const height = window.innerHeight;
            const margin = 0; // Strict bounds

            if (id === 'chat') {
                // Anchor: Top-Center (x is center, y is top)
                // X Bounds: size.w/2 <= x <= width - size.w/2
                newX = Math.max(size.w / 2 + margin, Math.min(width - size.w / 2 - margin, newX));
                // Y Bounds: 0 <= y <= height - size.h
                newY = Math.max(margin, Math.min(height - size.h - margin, newY));

            } else if (id === 'video') {
                // Anchor: Top-Left
                newX = Math.max(margin, Math.min(width - size.w - margin, newX));
                newY = Math.max(margin, Math.min(height - size.h - margin, newY));

            } else {
                // Anchor: Center
                newX = Math.max(size.w / 2 + margin, Math.min(width - size.w / 2 - margin, newX));
                newY = Math.max(size.h / 2 + margin, Math.min(height - size.h / 2 - margin, newY));
            }

            return {
                ...prev,
                [id]: {
                    x: newX,
                    y: newY
                }
            };
        });
    };

    // --- MOUSE DRAG HANDLERS ---
    const handleMouseDown = (e, id) => {
        console.log(`[MouseDrag] MouseDown on ${id}`, { target: e.target.tagName });

        // Fixed elements that should never be draggable (even in modular mode)
        const fixedElements = ['visualizer', 'chat', 'video', 'tools'];
        if (fixedElements.includes(id)) {
            console.log(`[MouseDrag] ${id} is a fixed element, not draggable`);
            return;
        }

        // Bring clicked element to front (z-index)
        bringToFront(id);

        // Prevent dragging if interacting with inputs, buttons, or canvas (for 3D controls)
        const tagName = e.target.tagName.toLowerCase();
        if (tagName === 'input' || tagName === 'button' || tagName === 'textarea' || tagName === 'canvas' || e.target.closest('button')) {
            console.log("[MouseDrag] Interaction blocked by interactive element");
            return;
        }

        // Check if clicking on a drag handle section (data-drag-handle attribute)
        const isDragHandle = e.target.closest('[data-drag-handle]');
        if (!isDragHandle && !isModularModeRef.current) {
            // If not clicking a drag handle and modular mode is off, don't drag
            // This allows popup windows to have dedicated drag areas
            console.log("[MouseDrag] Not a drag handle and modular mode off");
            return;
        }

        const elPos = elementPositions[id];
        if (!elPos) return;

        // Calculate offset based on anchor point
        // Most are Center Anchored (x, y is center)
        // Chat is Top-Center Anchored (x is center, y is top)
        // Video is Top-Left Anchored (x is left, y is top)

        // We want: MousePos = ElementPos + Offset
        // So: Offset = MousePos - ElementPos
        dragOffsetRef.current = {
            x: e.clientX - elPos.x,
            y: e.clientY - elPos.y
        };

        setActiveDragElement(id);
        activeDragElementRef.current = id;
        isDraggingRef.current = true;

        window.addEventListener('mousemove', handleMouseDrag);
        window.addEventListener('mouseup', handleMouseUp);
    };

    const handleMouseDrag = (e) => {
        if (!isDraggingRef.current || !activeDragElementRef.current) return;

        const id = activeDragElementRef.current;
        const currentPos = elementPositionsRef.current[id];
        if (!currentPos) return;

        // Target Position = MousePos - Offset
        // But we want delta for updateElementPosition??
        // actually updateElementPosition takes dx, dy.
        // Let's just set the position directly or calculate delta.
        // Since updateElementPosition has bounds logic, let's use it, but we need delta from PREVIOUS position?
        // OR we can refactor updateElementPosition to take absolute.
        // Let's stick to calculating new position and manually updating state with bounds logic inside a setter.

        // Actually, updateElementPosition uses setElementPositions(prev => ...).
        // Let's duplicate bounds logic for mouse drag to be precise or reuse.
        // reusing updateElementPosition requires calculating dx/dy from *current state* which might be lagging in the closure?
        // No, functional update is fine.

        // But for smooth mouse drag, absolute position is better.
        const rawNewX = e.clientX - dragOffsetRef.current.x;
        const rawNewY = e.clientY - dragOffsetRef.current.y;

        setElementPositions(prev => {
            const size = elementSizes[id] || { w: 100, h: 100 }; // Fallback
            let newX = rawNewX;
            let newY = rawNewY;

            const width = window.innerWidth;
            const height = window.innerHeight;
            const margin = 0;

            if (id === 'chat') {
                newX = Math.max(size.w / 2 + margin, Math.min(width - size.w / 2 - margin, newX));
                newY = Math.max(margin, Math.min(height - size.h - margin, newY));
            } else if (id === 'video') {
                newX = Math.max(margin, Math.min(width - size.w - margin, newX));
                newY = Math.max(margin, Math.min(height - size.h - margin, newY));
            } else {
                newX = Math.max(size.w / 2 + margin, Math.min(width - size.w / 2 - margin, newX));
                newY = Math.max(size.h / 2 + margin, Math.min(height - size.h / 2 - margin, newY));
            }

            return {
                ...prev,
                [id]: { x: newX, y: newY }
            };
        });
    };

    const handleMouseUp = () => {
        isDraggingRef.current = false;
        setActiveDragElement(null);
        activeDragElementRef.current = null;
        window.removeEventListener('mousemove', handleMouseDrag);
        window.removeEventListener('mouseup', handleMouseUp);
    };

    const audioAmp = useMemo(
        () => aiAudioData.reduce((a, b) => a + b, 0) / aiAudioData.length / 255,
        [aiAudioData]
    );

    const toggleKasaWindow = () => {
        if (!showKasaWindow) {
            // Maybe trigger discover instantly?
            if (kasaDevices.length === 0) socket.emit('discover_kasa');
        }
        setShowKasaWindow(!showKasaWindow);
    };

    const togglePrinterWindow = () => {
        setShowPrinterWindow(!showPrinterWindow);
    };

    const toggleChatWindow = () => {
        setShowChatWindow(prev => {
            const nextValue = !prev;
            if (nextValue) bringToFront('chat');
            return nextValue;
        });
    };



    if (isMobile) {
        return (
            <MobileApp
                socket={socket}
                isConnected={isConnected}
                isMuted={isMuted}
                togglePower={togglePower}
                toggleMute={toggleMute}
                messages={messages}
                aiAudioData={aiAudioData}
                audioAmp={audioAmp}
                inputValue={inputValue}
                setInputValue={setInputValue}
                handleSend={handleSend}
            />
        );
    }

    return (
        <div className={`ada-soft-shell h-screen w-screen text-[#10294d] font-mono overflow-hidden flex flex-col relative selection:bg-blue-100 selection:text-blue-900 ${isElectron ? 'electron-performance' : ''}`}>

            {/* Logic: Show AuthLock if we are NOT authenticated AND (Lock Screen is visible OR Auth is Enabled) 
                Actually, simpler: isLockScreenVisible is the source of truth for visibility.
                We set isLockScreenVisible = true via socket if auth is required.
             */}

            {isLockScreenVisible && (
                <AuthLock
                    socket={socket}
                    onAuthenticated={() => setIsAuthenticated(true)}
                    onAnimationComplete={() => setIsLockScreenVisible(false)}
                />
            )}

            {/* Écrans natifs de l'OS (Observabilité, Agents), ouverts depuis le dock central */}
            {!isLockScreenVisible && (
                <OsShell
                    socket={socket}
                    status={{ socketConnected, isAuthenticated, printerCount }}
                    screen={osScreen}
                    onClose={() => setOsScreen(null)}
                    onNavigate={(target) => {
                        if (target === 'home') { setOsScreen(null); return; }
                        const windows = {
                            terminal: () => setShowTerminalWindow(true),
                            domotique: () => setShowKasaWindow(true),
                            printer: () => setShowPrinterWindow(true),
                            cad: () => setShowCadWindow(true),
                            documents: () => setShowDocumentsWindow(true),
                            workspace: () => setShowWorkspaceWindow(true),
                            settings: () => setShowSettings(true),
                        };
                        if (windows[target]) windows[target]();
                        else setOsScreen(target); // écrans natifs (observability, agents)
                    }}
                />
            )}

            {/* Background light field */}
            <div
                className="absolute inset-0 z-0 pointer-events-none"
                style={{
                    backgroundImage: 'radial-gradient(circle at 50% 42%, rgba(60, 130, 246, 0.08), transparent 32%), radial-gradient(circle at 10% 20%, rgba(62, 139, 255, 0.08), transparent 18%)',
                }}
            ></div>

            {!isElectron && (
                <div
                    className="absolute top-[42%] left-1/2 -translate-x-1/2 -translate-y-1/2 w-[900px] h-[560px] bg-blue-200/20 blur-[90px] pointer-events-none"
                />
            )}

            {/* Top Bar (Draggable) */}
            <div className="z-50 flex items-center justify-between px-6 py-8 bg-transparent select-none sticky top-0" style={{ WebkitAppRegion: 'drag' }}>
                <div className="flex items-center gap-4 pl-2">
                    <h1 className="hidden text-2xl font-bold tracking-[0.02em] text-[#10294d]">
                        ADA – REDESIGN
                    </h1>
                    {/* FPS Counter */}
                    {isVideoOn && (
                        <div className="hidden text-[10px] text-emerald-600 border border-emerald-200 bg-white/60 px-2 py-0.5 rounded-full ml-2">
                            FPS: {fps}
                        </div>
                    )}
                    {/* Connected Printers Count */}
                    {printerCount > 0 && (
                        <div className="hidden items-center gap-1.5 text-[10px] text-emerald-700 border border-emerald-200 bg-white/60 px-2 py-0.5 rounded-full ml-2">
                            <Printer size={10} className="text-emerald-600" />
                            <span>{printerCount} Printer{printerCount !== 1 ? 's' : ''}</span>
                        </div>
                    )}
                    {/* Connected Smart Devices Count */}
                    {kasaDevices.length > 0 && (
                        <div className="hidden items-center gap-1.5 text-[10px] text-amber-700 border border-amber-200 bg-white/60 px-2 py-0.5 rounded-full ml-2">
                            <span>LIGHT</span>
                            <span>{kasaDevices.length} Device{kasaDevices.length !== 1 ? 's' : ''}</span>
                        </div>
                    )}
                </div>

                {/* Top Visualizer (User Mic) */}
                <div className="flex-1 flex justify-center mx-4 opacity-0 pointer-events-none">
                    <TopAudioBar audioData={micAudioData} audioDataRef={micAudioDataRef} />
                </div>

                <div className="flex items-center gap-2 pr-2" style={{ WebkitAppRegion: 'no-drag' }}>
                    {/* Live Clock */}
                    <div className="flex items-center gap-1.5 text-[11px] text-slate-500 font-mono px-2">
                        <Clock size={12} className="text-blue-500/60" />
                        <span>{currentTime.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                    </div>
                    <button onClick={handleMinimize} className="p-1 hover:bg-blue-50 rounded text-blue-600 transition-colors">
                        <Minus size={18} />
                    </button>
                    <button onClick={handleMaximize} className="p-1 hover:bg-blue-50 rounded text-blue-600 transition-colors">
                        <div className="w-[14px] h-[14px] border-2 border-current rounded-[2px]" />
                    </button>
                    <button onClick={handleCloseRequest} className="p-1 hover:bg-red-900/50 rounded text-red-500 transition-colors">
                        <X size={18} />
                    </button>
                </div>
            </div>

            {/* Main Content */}
            <div className="flex-1 relative z-10 flex flex-col items-center justify-center">
                {/* Central Visualizer (AI Audio) */}
                <div
                    id="visualizer"
                    className={`absolute flex items-center justify-center transition-all duration-200 overflow-visible
                        ${isModularMode ? (activeDragElement === 'visualizer' ? 'ring-2 ring-blue-400/40 bg-white/25' : 'ring-1 ring-blue-200/60 bg-white/10') + ' rounded-2xl pointer-events-auto' : 'pointer-events-none'}
                    `}
                    style={{
                        left: elementPositions.visualizer.x,
                        top: elementPositions.visualizer.y,
                        transform: 'translate(-50%, -50%)',
                        width: elementSizes.visualizer.w,
                        height: elementSizes.visualizer.h
                    }}
                    onMouseDown={(e) => handleMouseDown(e, 'visualizer')}
                >
                    <div className="relative z-20">
                        <Visualizer
                            audioData={aiAudioData}
                            audioDataRef={aiAudioDataRef}
                            isListening={isConnected && !isMuted}
                            intensity={isElectron ? null : audioAmp}
                            width={elementSizes.visualizer.w}
                            height={elementSizes.visualizer.h}
                            reduceMotion={isElectron}
                        />
                    </div>
                    {isModularMode && <div className={`absolute top-2 right-2 text-xs font-bold tracking-widest z-20 ${activeDragElement === 'visualizer' ? 'text-blue-600' : 'text-blue-400/60'}`}>VISUALIZER</div>}
                </div>

                {/* Video Feed Overlay */}
                {/* Floating Project Label */}
                <div className="absolute top-[86px] left-1/2 -translate-x-1/2 text-blue-700 text-xs font-mono tracking-widest pointer-events-none z-50 bg-white/55 px-3 py-1 rounded-full backdrop-blur-sm border border-white/80 shadow-[0_10px_30px_rgba(37,99,235,0.08)] opacity-0">
                    PROJECT: {currentProject?.toUpperCase()}
                </div>

                <div
                    id="video"
                    className={`fixed bottom-10 right-14 transition-all duration-300 
                        ${isVideoOn ? 'opacity-100' : 'opacity-0 pointer-events-none'} 
                        ada-camera-window backdrop-blur-xl rounded-[18px] p-5
                    `}
                    style={{ zIndex: 20 }}
                >
                    {/* Compact Display Container (1080p Source) */}
                    <div className="relative border border-white/60 rounded-[14px] overflow-hidden shadow-[0_18px_52px_rgba(37,99,235,0.20)] w-[480px] aspect-video bg-white/50">
                        {/* Hidden Video Element (Source) */}
                        <video ref={videoRef} autoPlay muted className="absolute inset-0 w-full h-full object-cover opacity-0" />

                        <div className="absolute left-4 top-4 z-20 text-lg text-white drop-shadow-sm">Caméra</div>
                        <button
                            type="button"
                            onClick={toggleVideo}
                            className="absolute right-4 top-4 z-20 text-white/90 transition hover:text-white"
                            aria-label="Fermer la caméra"
                            title="Fermer la caméra"
                        >
                            <X size={22} strokeWidth={1.8} />
                        </button>

                        {/* Canvas for Displaying Video + Skeleton (Ensures overlap) */}
                        <canvas
                            ref={canvasRef}
                            className="absolute inset-0 w-full h-full opacity-80"
                            style={{ transform: isCameraFlipped ? 'scaleX(-1)' : 'none' }}
                        />

                        {isHandTrackingEnabled && (
                            <div className="absolute bottom-2 left-2 z-10 text-[10px] leading-4 text-cyan-100 bg-black/70 backdrop-blur px-2 py-1 rounded border border-cyan-500/20">
                                <div>STATE: {handDebug.state}</div>
                                <div>PINCH: {handDebug.pinchRatio === null ? '--' : handDebug.pinchRatio.toFixed(3)}</div>
                                <div>CONF: {handDebug.confidence.toFixed(2)}</div>
                                <div>BOX: {handDebug.interactionInside ? 'IN' : 'EDGE'}</div>
                                <div>RAW: {handDebug.rawCursor ? `${Math.round(handDebug.rawCursor.x)},${Math.round(handDebug.rawCursor.y)}` : '--'}</div>
                                <div>CURSOR: {handDebug.filteredCursor ? `${Math.round(handDebug.filteredCursor.x)},${Math.round(handDebug.filteredCursor.y)}` : '--'}</div>
                                <div>DEAD: {handDebug.deadZone.toFixed(4)}</div>
                            </div>
                        )}
                        <div className="absolute bottom-4 left-1/2 z-20 flex -translate-x-1/2 items-center gap-5">
                            <button
                                type="button"
                                onClick={toggleMute}
                                className="ada-camera-control"
                                aria-label={isMuted ? 'Activer le micro' : 'Couper le micro'}
                                title={isMuted ? 'Activer le micro' : 'Couper le micro'}
                            >
                                {isMuted ? <MicOff size={22} /> : <Mic size={22} />}
                            </button>
                            <button
                                type="button"
                                onClick={toggleVideo}
                                className="ada-camera-control h-[58px] w-[58px]"
                                aria-label="Caméra"
                                title="Caméra"
                            >
                                <Video size={24} />
                            </button>
                            <button
                                type="button"
                                onClick={toggleHandTracking}
                                className={`ada-camera-control ${isHandTrackingEnabled ? 'is-active' : ''}`}
                                aria-label={isHandTrackingEnabled ? 'Désactiver le contrôle gestuel' : 'Activer le contrôle gestuel'}
                                title={isHandTrackingEnabled ? 'Désactiver le contrôle gestuel' : 'Activer le contrôle gestuel'}
                                aria-pressed={isHandTrackingEnabled}
                            >
                                <Hand size={21} />
                            </button>
                            <button
                                type="button"
                                onClick={() => setShowSettings(!showSettings)}
                                className="ada-camera-control"
                                aria-label="Paramètres caméra"
                                title="Paramètres"
                            >
                                <Settings size={21} />
                            </button>
                        </div>
                    </div>
                </div>

                {/* Settings Modal - Moved outside Video so it shows independently */}
                {showSettings && (
                    <SettingsWindow
                        socket={socket}
                        micDevices={micDevices}
                        speakerDevices={speakerDevices}
                        webcamDevices={webcamDevices}
                        selectedMicId={selectedMicId}
                        setSelectedMicId={setSelectedMicId}
                        selectedSpeakerId={selectedSpeakerId}
                        setSelectedSpeakerId={setSelectedSpeakerId}
                        selectedWebcamId={selectedWebcamId}
                        setSelectedWebcamId={setSelectedWebcamId}
                        cursorSensitivity={cursorSensitivity}
                        setCursorSensitivity={setCursorSensitivity}
                        isCameraFlipped={isCameraFlipped}
                        setIsCameraFlipped={setIsCameraFlipped}
                        handleFileUpload={handleFileUpload}
                        onClose={() => setShowSettings(false)}
                    />
                )}

                {/* CAD Window Overlay - Moved outside of Video so it can show independently */}
                {showCadWindow && (
                    <div
                        id="cad"
                        className={`absolute flex flex-col transition-all duration-200 
                        backdrop-blur-xl bg-black/40 border border-white/10 shadow-2xl overflow-hidden rounded-2xl
                        ${activeDragElement === 'cad' ? 'ring-2 ring-green-500 bg-green-500/10' : ''}
                    `}
                        style={{
                            left: elementPositions.cad?.x || window.innerWidth / 2,
                            top: elementPositions.cad?.y || window.innerHeight / 2,
                            transform: 'translate(-50%, -50%)',
                            width: `${elementSizes.cad.w}px`,
                            height: `${elementSizes.cad.h}px`,
                            pointerEvents: 'auto',
                            zIndex: getZIndex('cad')
                        }}
                        onMouseDown={(e) => handleMouseDown(e, 'cad')}
                    >
                        {/* Drag Handle Header */}
                        <div
                            data-drag-handle
                            className="h-8 bg-gray-900/80 border-b border-cyan-500/20 flex items-center justify-between px-3 cursor-grab active:cursor-grabbing shrink-0"
                        >
                            <span className="text-xs font-bold tracking-widest text-cyan-500/70">CAD PROTOTYPE</span>
                            <button
                                onClick={() => setShowCadWindow(false)}
                                className="text-gray-400 hover:text-red-400 hover:bg-red-500/20 p-1 rounded transition-colors"
                            >
                                ✕
                            </button>
                        </div>
                        <div className="absolute inset-0 bg-[url('https://grainy-gradients.vercel.app/noise.svg')] opacity-10 pointer-events-none mix-blend-overlay z-10"></div>
                        <div className="relative z-20 flex-1 min-h-0">
                            <CadWindow
                                data={cadData}
                                thoughts={cadThoughts}
                                retryInfo={cadRetryInfo}
                                onClose={() => setShowCadWindow(false)}
                                socket={socket}
                            />
                        </div>
                    </div>
                )}


                {/* Terminal Window */}
                {showTerminalWindow && (
                    <div
                        id="terminal"
                        className={`absolute flex flex-col transition-all duration-200
                        backdrop-blur-xl bg-black/40 border border-white/10 shadow-2xl overflow-hidden rounded-lg
                        ${activeDragElement === 'terminal' ? 'ring-2 ring-green-500 bg-green-500/10' : ''}
                    `}
                        style={{
                            left: elementPositions.terminal?.x || window.innerWidth / 2 + 100,
                            top: elementPositions.terminal?.y || window.innerHeight / 2 - 100,
                            transform: 'translate(-50%, -50%)',
                            width: '520px',
                            height: '340px',
                            pointerEvents: 'auto',
                            zIndex: getZIndex('terminal')
                        }}
                        onMouseDown={(e) => handleMouseDown(e, 'terminal')}
                    >
                        <div className="relative z-20 w-full h-full">
                            <TerminalWindow
                                entries={terminalEntries}
                                onClose={() => setShowTerminalWindow(false)}
                            />
                        </div>
                    </div>
                )}

                {/* Chat Module */}
                {showChatWindow && (
                    <ChatModule
                        messages={messages}
                        inputValue={inputValue}
                        setInputValue={setInputValue}
                        handleSend={handleSend}
                        isModularMode={isModularMode}
                        activeDragElement={activeDragElement}
                        position={elementPositions.chat}
                        width={elementSizes.chat.w}
                        height={elementSizes.chat.h}
                        zIndex={getZIndex('chat')}
                        onClose={() => setShowChatWindow(false)}
                        onMouseDown={(e) => handleMouseDown(e, 'chat')}
                    />
                )}

                {/* Footer Controls / Tools Module */}
                <div className="z-20 flex justify-center pb-10 pointer-events-none">
                    <ToolsModule
                        isConnected={isConnected}
                        isMuted={isMuted}
                        isVideoOn={isVideoOn}
                        isHandTrackingEnabled={isHandTrackingEnabled}
                        showSettings={showSettings}
                        onTogglePower={togglePower}
                        onToggleMute={toggleMute}
                        onToggleVideo={toggleVideo}
                        onToggleSettings={() => setShowSettings(!showSettings)}
                        onToggleChat={toggleChatWindow}
                        showChatWindow={showChatWindow}
                        onToggleHand={toggleHandTracking}
                        onToggleKasa={toggleKasaWindow}
                        showKasaWindow={showKasaWindow}
                        onTogglePrinter={togglePrinterWindow}
                        showPrinterWindow={showPrinterWindow}
                        onToggleCad={() => setShowCadWindow(!showCadWindow)}
                        showCadWindow={showCadWindow}
                        isScreenMode={isScreenMode}
                        onToggleScreenMode={toggleScreenMode}
                        onToggleDocuments={() => setShowDocumentsWindow(true)}
                        onToggleWorkspace={() => setShowWorkspaceWindow(true)}
                        showWorkspaceWindow={showWorkspaceWindow}
                        onOpenObservability={() => setOsScreen('observability')}
                        onOpenAgents={() => setOsScreen('agents')}
                        activeOsScreen={osScreen}
                        activeDragElement={activeDragElement}
                        isModularMode={isModularMode}
                        position={elementPositions.tools}
                        onMouseDown={(e) => handleMouseDown(e, 'tools')}
                    />
                </div>

                {/* Kasa Window */}
                {showKasaWindow && (
                    <KasaWindow
                        socket={socket}
                        position={elementPositions.kasa}
                        activeDragElement={activeDragElement}
                        setActiveDragElement={setActiveDragElement}
                        devices={kasaDevices}
                        onClose={() => setShowKasaWindow(false)}
                        onMouseDown={(e) => handleMouseDown(e, 'kasa')}
                        zIndex={getZIndex('kasa')}
                    />
                )}

                {/* Printer Window */}
                {showPrinterWindow && (
                    <PrinterWindow
                        socket={socket}
                        onClose={() => setShowPrinterWindow(false)}
                        position={elementPositions.printer}
                        onMouseDown={(e) => handleMouseDown(e, 'printer')}
                        activeDragElement={activeDragElement}
                        setActiveDragElement={setActiveDragElement}
                        zIndex={getZIndex('printer')}
                    />
                )}

                {/* Documents / RAG Window */}
                {showDocumentsWindow && (
                    <DocumentsWindow onClose={() => setShowDocumentsWindow(false)} />
                )}

                {showWorkspaceWindow && (
                    <WorkspaceShell
                        socket={socket}
                        workspaceState={workspaceState}
                        workspaceEvents={workspaceEvents}
                        workspaceStatus={workspaceStatus}
                        researchResult={workspaceResearchResult}
                        onClose={() => setShowWorkspaceWindow(false)}
                    />
                )}

                {/* Tool Confirmation Modal */}
                <ConfirmationPopup
                    request={confirmationRequest}
                    onConfirm={handleConfirmTool}
                    onDeny={handleDenyTool}
                />
            </div>
        </div>
    );
}

export default App;

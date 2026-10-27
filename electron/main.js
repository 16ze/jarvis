const { app, BrowserWindow, ipcMain, dialog, session, shell, systemPreferences, screen } = require('electron');
const path = require('path');
const { spawn } = require('child_process');

// Keep the Windows GPU workaround scoped to Windows. Forcing D3D/Vulkan on
// other platforms can make Electron's compositor noticeably less responsive.
if (process.platform === 'win32') {
    app.commandLine.appendSwitch('use-angle', 'd3d11');
    app.commandLine.appendSwitch('enable-features', 'Vulkan');
    app.commandLine.appendSwitch('ignore-gpu-blocklist');
}
app.commandLine.appendSwitch('disable-background-timer-throttling');
app.commandLine.appendSwitch('disable-renderer-backgrounding');

let mainWindow;
let pythonProcess;
let shuttingDown = false;
let backendHealthOk = false;
let pythonStderrBuf = '';

const reactiveBrainDefaults = {
    BRAIN_ENABLED: 'true',
    BRAIN_MODULATE_ALL: 'true',
    BRAIN_OBSERVE_ONLY: 'false',
    BRAIN_V3_ENABLED: 'true',
    BRAIN_V3_SHADOW_MODE: 'false',
    BRAIN_V3_REACTION_THRESHOLD: '0.35',
    BRAIN_V3_PROB_GATE_SLOPE: '3.5',
    BRAIN_V3_COST_OBJECT_NORMAL: '0.10',
    BRAIN_V3_COST_SCENE_NORMAL: '0.15',
    BRAIN_V3_ATTENTION_BUDGET_INIT: '1.4',
    BRAIN_V3_ATTENTION_BUDGET_MAX: '2.0',
    BRAIN_V3_REFRACTORY_VISION_OBJECT: '0.8',
    BRAIN_V3_REFRACTORY_VISION_SCENE: '3.0',
    BRAIN_V3_REFRACTORY_TEXT: '0.15',
    VISION_OBJECT_ENABLED: 'true',
};

function withReactiveBrainDefaults(env) {
    const merged = { ...env };
    for (const [key, value] of Object.entries(reactiveBrainDefaults)) {
        if (merged[key] === undefined || merged[key] === '') {
            merged[key] = value;
        }
    }
    return merged;
}

function isHttpUrl(url) {
    try {
        const parsed = new URL(url);
        return parsed.protocol === 'http:' || parsed.protocol === 'https:';
    } catch {
        return false;
    }
}

function safeOpenExternal(url) {
    if (isHttpUrl(url)) {
        shell.openExternal(url);
    }
}

function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1920,
        height: 1080,
        webPreferences: {
            nodeIntegration: true,
            contextIsolation: false, // For simple IPC/Socket.IO usage
            backgroundThrottling: false,
            // Navigateur intégré du Workspace. Le <webview> lui-même tourne
            // SANS intégration Node et dans une session isolée (voir
            // will-attach-webview ci-dessous) : le contenu web distant n'a
            // aucun accès aux API privilégiées de l'app.
            webviewTag: true,
        },
        backgroundColor: '#000000',
        frame: false, // Frameless for custom UI
        titleBarStyle: 'hidden',
        show: false, // Don't show until ready
    });

    // In dev, load Vite server. In prod, load index.html
    const isDev = process.env.NODE_ENV !== 'production';

    const loadFrontend = (retries = 3) => {
        const url = isDev ? 'http://localhost:5173' : null;
        const loadPromise = isDev
            ? mainWindow.loadURL(url)
            : mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));

        loadPromise
            .then(() => {
                console.log('Frontend loaded successfully!');
                windowWasShown = true;
                mainWindow.show();
                if (isDev && process.env.OPEN_DEVTOOLS === '1') {
                    mainWindow.webContents.openDevTools();
                }
            })
            .catch((err) => {
                console.error(`Failed to load frontend: ${err.message}`);
                if (retries > 0) {
                    console.log(`Retrying in 1 second... (${retries} retries left)`);
                    setTimeout(() => loadFrontend(retries - 1), 1000);
                } else {
                    console.error('Failed to load frontend after all retries. Keeping window open.');
                    windowWasShown = true;
                    mainWindow.show(); // Show anyway so user sees something
                }
            });
    };

    loadFrontend();

    // Vignette flottante Jarvis (fenêtre overlay indépendante, toujours au-dessus).
    createWidgetWindow();

    // ── Sécurité du navigateur intégré ────────────────────────────────────────
    // Le <webview> affiche du web arbitraire : on lui retire tout privilège
    // avant même son attachement. Sans ça, activer webviewTag serait dangereux
    // dans une fenêtre qui tourne en nodeIntegration.
    mainWindow.webContents.on('will-attach-webview', (_event, webPreferences, params) => {
        delete webPreferences.preload;
        webPreferences.nodeIntegration = false;
        webPreferences.nodeIntegrationInSubFrames = false;
        webPreferences.contextIsolation = true;
        webPreferences.sandbox = true;
        webPreferences.webSecurity = true;
        // Session dédiée : les cookies du web n'atteignent pas ceux de l'app.
        params.partition = 'persist:ada-browser';
        params.allowpopups = false;
    });

    mainWindow.on('closed', () => {
        mainWindow = null;
    });
}

// ─── VIGNETTE FLOTTANTE (mini-robot Jarvis + mini-chat) ──────────────────────
let widgetWindow = null;
let widgetDrag = null; // { offX, offY } pendant un déplacement
let widgetFullPrev = null; // bornes sauvegardées avant le plein écran
const WIDGET_COLLAPSED = { width: 92, height: 92 };
const WIDGET_EXPANDED = { width: 360, height: 560 };
const WIDGET_STATE_FILE = path.join(app.getPath('userData'), 'widget-state.json');
let widgetSaveTimer = null;

function loadWidgetPos() {
    try {
        const raw = JSON.parse(require('fs').readFileSync(WIDGET_STATE_FILE, 'utf8'));
        if (Number.isFinite(raw.x) && Number.isFinite(raw.y)) return { x: raw.x, y: raw.y };
    } catch { /* pas d'état sauvegardé */ }
    return null;
}

function saveWidgetPos(x, y) {
    clearTimeout(widgetSaveTimer);
    widgetSaveTimer = setTimeout(() => {
        try { require('fs').writeFileSync(WIDGET_STATE_FILE, JSON.stringify({ x, y })); } catch { /* best effort */ }
    }, 400);
}

function clampToDisplay(b) {
    const disp = screen.getDisplayMatching(b) || screen.getPrimaryDisplay();
    const wa = disp.workArea;
    const x = Math.min(Math.max(b.x, wa.x), wa.x + wa.width - b.width);
    const y = Math.min(Math.max(b.y, wa.y), wa.y + wa.height - b.height);
    return { x: Math.round(x), y: Math.round(y), width: b.width, height: b.height };
}

function createWidgetWindow() {
    if (widgetWindow) return;
    const isDev = process.env.NODE_ENV !== 'production';

    const primary = screen.getPrimaryDisplay().workArea;
    const saved = loadWidgetPos();
    const start = saved || {
        x: primary.x + primary.width - WIDGET_COLLAPSED.width - 24,
        y: primary.y + 28,
    };
    const startBounds = clampToDisplay({ ...start, ...WIDGET_COLLAPSED });

    widgetWindow = new BrowserWindow({
        ...startBounds,
        frame: false,
        transparent: true,
        resizable: false,
        maximizable: false,
        minimizable: false,
        fullscreenable: false,
        skipTaskbar: true,
        hasShadow: false,
        alwaysOnTop: true,
        backgroundColor: '#00000000',
        webPreferences: {
            nodeIntegration: true,
            contextIsolation: false,
            backgroundThrottling: false,
        },
        show: false,
    });

    widgetWindow.setAlwaysOnTop(true, 'floating');
    if (process.platform === 'darwin') {
        widgetWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
    }

    const loadPromise = isDev
        ? widgetWindow.loadURL('http://localhost:5173/widget.html')
        : widgetWindow.loadFile(path.join(__dirname, '../dist/widget.html'));
    loadPromise
        .then(() => { if (widgetWindow) widgetWindow.show(); })
        .catch((err) => console.error(`[Widget] Échec du chargement : ${err.message}`));

    widgetWindow.on('closed', () => { widgetWindow = null; });
}

function registerWidgetIpc() {
    // Déplacement : le renderer envoie la position écran du curseur, Electron
    // calcule la nouvelle position de la fenêtre (il connaît l'écran et les bornes).
    ipcMain.on('widget:drag-start', () => { widgetDrag = null; });
    ipcMain.on('widget:drag-move', (_e, { mx, my } = {}) => {
        if (!widgetWindow || !Number.isFinite(mx) || !Number.isFinite(my)) return;
        const b = widgetWindow.getBounds();
        if (!widgetDrag) widgetDrag = { offX: mx - b.x, offY: my - b.y };
        const nb = clampToDisplay({ x: mx - widgetDrag.offX, y: my - widgetDrag.offY, width: b.width, height: b.height });
        widgetWindow.setBounds(nb);
        saveWidgetPos(nb.x, nb.y);
    });
    ipcMain.on('widget:drag-end', () => { widgetDrag = null; });

    // Ouverture / fermeture du chat : on redimensionne la fenêtre en gardant
    // le coin haut-gauche (l'avatar) stable, reclampé dans l'écran.
    ipcMain.on('widget:set-open', (_e, { open } = {}) => {
        if (!widgetWindow) return;
        const b = widgetWindow.getBounds();
        const size = open ? WIDGET_EXPANDED : WIDGET_COLLAPSED;
        const nb = clampToDisplay({ x: b.x, y: b.y, width: size.width, height: size.height });
        widgetWindow.setBounds(nb);
        saveWidgetPos(nb.x, nb.y);
    });

    // Redimensionnement explicite piloté par le renderer (tailles S/M/L/XL +
    // ouverture du chat). On garde le coin haut-gauche stable et on reclampe.
    ipcMain.on('widget:resize', (_e, { w, h } = {}) => {
        if (!widgetWindow || !Number.isFinite(w) || !Number.isFinite(h)) return;
        if (widgetFullPrev) return; // ignoré pendant le plein écran
        const b = widgetWindow.getBounds();
        const nb = clampToDisplay({ x: b.x, y: b.y, width: Math.round(w), height: Math.round(h) });
        setWidgetBounds(nb);
        saveWidgetPos(nb.x, nb.y);
    });

    // Plein écran : la fenêtre widget (frameless, transparente, always-on-top)
    // s'étend à toute la zone de travail ; le visage est centré par le renderer.
    ipcMain.on('widget:fullscreen', (_e, { on } = {}) => {
        if (!widgetWindow) return;
        const disp = screen.getDisplayNearestPoint(widgetWindow.getBounds());
        const wa = (disp && disp.workArea) || screen.getPrimaryDisplay().workArea;
        if (on) {
            widgetFullPrev = widgetWindow.getBounds();
            setWidgetBounds({ x: wa.x, y: wa.y, width: wa.width, height: wa.height });
        } else if (widgetFullPrev) {
            setWidgetBounds(clampToDisplay(widgetFullPrev));
            saveWidgetPos(widgetFullPrev.x, widgetFullPrev.y);
            widgetFullPrev = null;
        }
    });
}

// Une fenêtre `resizable: false` IGNORE les setBounds qui changent la taille
// (macOS). On réautorise le redimensionnement le temps de l'appel programmatique,
// puis on le reverrouille pour empêcher tout redimensionnement à la souris.
function setWidgetBounds(nb) {
    if (!widgetWindow) return;
    const wasResizable = widgetWindow.isResizable();
    try {
        widgetWindow.setResizable(true);
        widgetWindow.setBounds(nb);
    } finally {
        if (!wasResizable) widgetWindow.setResizable(false);
    }
}

function resolvePythonBackendBinary() {
    const fs = require('fs');
    const envOverride = process.env.JARVIS_PYTHON || process.env.ADA_PYTHON;
    if (envOverride && fs.existsSync(envOverride)) {
        console.log(`Using Python from JARVIS_PYTHON / ADA_PYTHON: ${envOverride}`);
        return envOverride;
    }
    if (envOverride && !fs.existsSync(envOverride)) {
        console.warn(`JARVIS_PYTHON / ADA_PYTHON points to missing file: ${envOverride}`);
    }

    const home = process.env.HOME || process.env.USERPROFILE || '';
    const condaPaths = process.platform === 'win32'
        ? [
            path.join(process.env.USERPROFILE || '', 'miniconda3', 'envs', 'ada_v2', 'python.exe'),
            path.join(process.env.USERPROFILE || '', 'anaconda3', 'envs', 'ada_v2', 'python.exe'),
            path.join(process.env.USERPROFILE || '', 'mambaforge', 'envs', 'ada_v2', 'python.exe'),
            path.join(process.env.USERPROFILE || '', 'miniforge3', 'envs', 'ada_v2', 'python.exe'),
            path.join('C:', 'ProgramData', 'miniconda3', 'envs', 'ada_v2', 'python.exe'),
            path.join('C:', 'ProgramData', 'anaconda3', 'envs', 'ada_v2', 'python.exe'),
        ]
        : process.platform === 'darwin'
        ? [
            '/opt/homebrew/Caskroom/miniconda/base/envs/ada_v2/bin/python',
            '/usr/local/Caskroom/miniconda/base/envs/ada_v2/bin/python',
            path.join(home, 'miniconda3', 'envs', 'ada_v2', 'bin', 'python'),
            path.join(home, 'anaconda3', 'envs', 'ada_v2', 'bin', 'python'),
            path.join(home, 'mambaforge', 'envs', 'ada_v2', 'bin', 'python'),
            path.join(home, 'miniforge3', 'envs', 'ada_v2', 'bin', 'python'),
            '/opt/miniconda3/envs/ada_v2/bin/python',
            '/usr/local/miniconda3/envs/ada_v2/bin/python',
        ]
        : [
            path.join(home, 'miniconda3', 'envs', 'ada_v2', 'bin', 'python'),
            path.join(home, 'anaconda3', 'envs', 'ada_v2', 'bin', 'python'),
            path.join(home, 'mambaforge', 'envs', 'ada_v2', 'bin', 'python'),
            path.join(home, 'miniforge3', 'envs', 'ada_v2', 'bin', 'python'),
            '/opt/conda/envs/ada_v2/bin/python',
            '/opt/miniconda3/envs/ada_v2/bin/python',
        ];

    const found = condaPaths.find(p => fs.existsSync(p));
    if (found) {
        return found;
    }
    console.warn(
        'Aucun interpréteur conda "ada_v2" trouvé dans les chemins connus — repli sur "python3" ' +
        '(souvent incomplet : installe les deps du backend ou définis JARVIS_PYTHON).'
    );
    return 'python3';
}

function startPythonBackend() {
    const scriptPath = path.join(__dirname, '../backend/server.py');
    console.log(`Starting Python backend: ${scriptPath}`);

    pythonStderrBuf = '';
    const finalBin = resolvePythonBackendBinary();
    console.log(`Using Python binary: ${finalBin}`);

    pythonProcess = spawn(finalBin, ['-u', scriptPath], {
        cwd: path.join(__dirname, '../backend'),
        env: withReactiveBrainDefaults({ ...process.env, PYTHONUNBUFFERED: '1' }),
    });

    pythonProcess.on('error', (err) => {
        console.error(`[Python spawn error]: ${err.message}`);
        dialog.showErrorBox(
            'Backend Python introuvable',
            `Impossible de démarrer le backend Python.\n\nErreur : ${err.message}\n\nBinaire utilisé : ${finalBin}\n\n` +
            'Crée l\'environnement conda "ada_v2" (voir CLAUDE.md) ou définis JARVIS_PYTHON vers le Python du projet.'
        );
    });

    pythonProcess.on('exit', (code, signal) => {
        if (shuttingDown) {
            return;
        }
        if (code !== 0 && code !== null) {
            console.error(`[Python] Process exited with code ${code} (signal: ${signal})`);
        } else {
            console.log(`[Python] Process exited cleanly (code: ${code})`);
        }
        if (!backendHealthOk && code !== 0 && code !== null) {
            const tail = pythonStderrBuf.replace(/\r/g, '').trim().slice(-3500);
            dialog.showErrorBox(
                'Backend Python arrêté au démarrage',
                `Le processus serveur s'est terminé (code ${code}).\n\n` +
                'Cause fréquente : "python3" système sans les paquets du backend (ex. playwright).\n' +
                'Utilise le Python de l\'environnement conda ada_v2, ou définis :\n' +
                '  export JARVIS_PYTHON="/chemin/vers/ada_v2/bin/python"\n\n' +
                '--- stderr (extrait) ---\n' +
                (tail || '(pas de sortie stderr capturée)')
            );
        }
    });

    pythonProcess.stdout.on('data', (data) => {
        console.log(`[Python]: ${data}`);
    });

    pythonProcess.stderr.on('data', (data) => {
        const s = data.toString();
        pythonStderrBuf += s;
        if (pythonStderrBuf.length > 12000) {
            pythonStderrBuf = pythonStderrBuf.slice(-12000);
        }
        console.error(`[Python Error]: ${data}`);
    });
}

// ─── CONTENT SECURITY POLICY ─────────────────────────────────────────────────
function isAdaUiResponse(url, isDev) {
    if (isDev) {
        return url.startsWith('http://localhost:5173/') || url.startsWith('http://127.0.0.1:5173/');
    }
    return url.startsWith('file://');
}

function applyCSP() {
    const isDev = process.env.NODE_ENV !== 'production';

    // Dev: Vite HMR + React Fast Refresh → 'unsafe-inline' + 'unsafe-eval'.
    //      MediaPipe WebAssembly → 'wasm-unsafe-eval' (requis séparément depuis Chrome 121+).
    // Prod: 'wasm-unsafe-eval' uniquement — pas d'eval arbitraire, pas de scripts inline.
    const scriptSrc = isDev
        ? "script-src 'self' 'unsafe-inline' 'unsafe-eval' 'wasm-unsafe-eval'"
        : "script-src 'self' 'wasm-unsafe-eval'";

    // Socket.IO WebSocket + REST backend (always localhost).
    // ws://localhost:5173 = Vite HMR in dev only.
    const connectSrc = isDev
        ? "connect-src 'self' http://localhost:8000 http://127.0.0.1:8000 ws://localhost:8000 ws://127.0.0.1:8000 ws://localhost:5173"
        : "connect-src 'self' http://localhost:8000 http://127.0.0.1:8000 ws://localhost:8000 ws://127.0.0.1:8000";

    // The noise texture in ToolsModule is loaded from an external URL.
    // Listed here explicitly — avoid wildcard img-src.
    const imgSrc = "img-src 'self' data: blob: https://grainy-gradients.vercel.app";

    const csp = [
        "default-src 'self'",
        scriptSrc,
        "style-src 'self' 'unsafe-inline'",   // Tailwind uses inline styles
        imgSrc,
        "media-src 'self' blob:",              // Camera / microphone streams
        connectSrc,
        "worker-src blob: 'self'",             // MediaPipe web workers
        "font-src 'self'",
        "object-src 'none'",                   // Block <object>, <embed>
        "base-uri 'self'",                     // Prevent base-tag injection
        "frame-ancestors 'none'",              // Prevent clickjacking
    ].join('; ');

    session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
        if (!isAdaUiResponse(details.url, isDev)) {
            callback({ responseHeaders: details.responseHeaders });
            return;
        }

        callback({
            responseHeaders: {
                ...details.responseHeaders,
                'Content-Security-Policy': [csp],
                // Prevent MIME-type sniffing
                'X-Content-Type-Options': ['nosniff'],
                // Deny framing entirely
                'X-Frame-Options': ['DENY'],
            },
        });
    });

    console.log(`[CSP] Applied (${isDev ? 'dev' : 'prod'} mode)`);
}

app.whenReady().then(() => {
    applyCSP();
    registerWidgetIpc();

    // Autorise mic + caméra pour le renderer (sinon getUserMedia renvoie un stream
    // sans frames et enumerateDevices ne livre pas les labels).
    session.defaultSession.setPermissionRequestHandler((webContents, permission, callback) => {
        const allowed = new Set(['media', 'microphone', 'camera']);
        callback(allowed.has(permission));
    });
    session.defaultSession.setPermissionCheckHandler((webContents, permission) => {
        const allowed = new Set(['media', 'microphone', 'camera']);
        return allowed.has(permission);
    });

    // Demande TCC macOS pour mic ET caméra au démarrage.
    if (process.platform === 'darwin') {
        systemPreferences.askForMediaAccess('microphone')
            .then((g) => console.log(`[Permissions] Microphone access: ${g ? 'granted' : 'denied'}`))
            .catch((err) => console.error(`[Permissions] Microphone request failed: ${err.message}`));
        systemPreferences.askForMediaAccess('camera')
            .then((g) => console.log(`[Permissions] Camera access: ${g ? 'granted' : 'denied'}`))
            .catch((err) => console.error(`[Permissions] Camera request failed: ${err.message}`));
    }

    // Pilotage PC : la fenêtre principale se rétracte (laisse la vignette robot
    // flottante comme indicateur), puis se restaure à la fin — façon Claude.
    ipcMain.on('pc-control-active', () => {
        try { if (mainWindow && !mainWindow.isMinimized()) mainWindow.minimize(); } catch (e) {}
    });
    ipcMain.on('pc-control-idle', () => {
        try { if (mainWindow && mainWindow.isMinimized()) mainWindow.restore(); } catch (e) {}
    });

    ipcMain.on('window-minimize', () => {
        if (mainWindow) mainWindow.minimize();
    });

    ipcMain.on('window-maximize', () => {
        if (mainWindow) {
            if (mainWindow.isMaximized()) {
                mainWindow.unmaximize();
            } else {
                mainWindow.maximize();
            }
        }
    });

    ipcMain.on('window-close', () => {
        if (mainWindow) mainWindow.close();
    });

    ipcMain.on('ada-search-open-external', (event, payload = {}) => {
        safeOpenExternal(payload.url);
    });

    checkBackendPort(8000).then((isTaken) => {
        if (isTaken) {
            console.log('Port 8000 is taken. Assuming backend is already running manually.');
            waitForBackend().then(createWindow);
        } else {
            startPythonBackend();
            // Imports lourds + disque lent : laisser le temps avant le healthcheck
            setTimeout(() => {
                waitForBackend().then(createWindow);
            }, 3500);
        }
    });

    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });
});

function checkBackendPort(port) {
    return new Promise((resolve) => {
        const net = require('net');
        const server = net.createServer();
        server.once('error', (err) => {
            if (err.code === 'EADDRINUSE') {
                resolve(true);
            } else {
                resolve(false);
            }
        });
        server.once('listening', () => {
            server.close();
            resolve(false);
        });
        server.listen(port);
    });
}

function waitForBackend(maxRetries = 60) {
    return new Promise((resolve) => {
        let attempts = 0;

        const check = () => {
            const http = require('http');
            const req = http.get('http://127.0.0.1:8000/status', (res) => {
                if (res.statusCode === 200) {
                    console.log('Backend is ready!');
                    backendHealthOk = true;
                    resolve({ success: true });
                } else {
                    retry();
                }
            });

            req.on('error', () => {
                retry();
            });

            req.setTimeout(1000, () => {
                req.destroy();
                retry();
            });
        };

        const retry = () => {
            attempts++;
            if (attempts >= maxRetries) {
                console.error(`Backend did not start after ${maxRetries} seconds. Continuing anyway.`);
                dialog.showErrorBox(
                    'Backend non disponible',
                    `Le backend Python n'a pas répondu après ${maxRetries} secondes.\n\nL'application va s'ouvrir mais certaines fonctionnalités seront indisponibles.\n\nVérifiez les logs dans la console pour plus de détails.`
                );
                resolve({ success: false });
                return;
            }
            console.log(`Waiting for backend... (${attempts}/${maxRetries})`);
            setTimeout(check, 1000);
        };

        check();
    });
}

let windowWasShown = false;

app.on('window-all-closed', () => {
    // Only quit if the window was actually shown at least once
    // This prevents quitting during startup if window creation fails
    if (process.platform !== 'darwin' && windowWasShown) {
        app.quit();
    } else if (!windowWasShown) {
        console.log('Window was never shown - keeping app alive to allow retries');
    }
});

app.on('will-quit', () => {
    shuttingDown = true;
    console.log('App closing... Killing Python backend.');
    if (pythonProcess) {
        if (process.platform === 'win32') {
            // Windows: Force kill the process tree synchronously
            try {
                const { execSync } = require('child_process');
                execSync(`taskkill /pid ${pythonProcess.pid} /f /t`);
            } catch (e) {
                console.error('Failed to kill python process:', e.message);
            }
        } else {
            // Unix: SIGKILL
            pythonProcess.kill('SIGKILL');
        }
        pythonProcess = null;
    }
});

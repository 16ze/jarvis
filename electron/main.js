const { app, BrowserWindow, ipcMain, dialog, session } = require('electron');
const path = require('path');
const { spawn } = require('child_process');

// Use ANGLE D3D11 backend - more stable on Windows while keeping WebGL working
// This fixes "GPU state invalid after WaitForGetOffsetInRange" error
app.commandLine.appendSwitch('use-angle', 'd3d11');
app.commandLine.appendSwitch('enable-features', 'Vulkan');
app.commandLine.appendSwitch('ignore-gpu-blocklist');

let mainWindow;
let pythonProcess;

function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1920,
        height: 1080,
        webPreferences: {
            nodeIntegration: true,
            contextIsolation: false, // For simple IPC/Socket.IO usage
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
                if (isDev) {
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

    mainWindow.on('closed', () => {
        mainWindow = null;
    });
}

function startPythonBackend() {
    const scriptPath = path.join(__dirname, '../backend/server.py');
    console.log(`Starting Python backend: ${scriptPath}`);

    // Detect Python binary — multi-platform conda paths + fallback
    const fs = require('fs');
    const condaPaths = process.platform === 'win32'
        ? [
            path.join(process.env.USERPROFILE || '', 'miniconda3', 'envs', 'ada_v2', 'python.exe'),
            path.join(process.env.USERPROFILE || '', 'anaconda3', 'envs', 'ada_v2', 'python.exe'),
            path.join('C:', 'ProgramData', 'miniconda3', 'envs', 'ada_v2', 'python.exe'),
            path.join('C:', 'ProgramData', 'anaconda3', 'envs', 'ada_v2', 'python.exe'),
        ]
        : process.platform === 'darwin'
        ? [
            '/opt/homebrew/Caskroom/miniconda/base/envs/ada_v2/bin/python',
            path.join(process.env.HOME || '', 'miniconda3', 'envs', 'ada_v2', 'bin', 'python'),
            path.join(process.env.HOME || '', 'anaconda3', 'envs', 'ada_v2', 'bin', 'python'),
            '/opt/miniconda3/envs/ada_v2/bin/python',
        ]
        : [
            path.join(process.env.HOME || '', 'miniconda3', 'envs', 'ada_v2', 'bin', 'python'),
            path.join(process.env.HOME || '', 'anaconda3', 'envs', 'ada_v2', 'bin', 'python'),
            '/opt/conda/envs/ada_v2/bin/python',
        ];

    const condaPython = condaPaths.find(p => fs.existsSync(p));
    const pythonBin = condaPython || 'python3';
    const finalBin = (pythonBin === 'python3' && !condaPython) ? 'python3' : pythonBin;

    console.log(`Using Python binary: ${finalBin}`);

    pythonProcess = spawn(finalBin, [scriptPath], {
        cwd: path.join(__dirname, '../backend'),
    });

    pythonProcess.on('error', (err) => {
        console.error(`[Python spawn error]: ${err.message}`);
        dialog.showErrorBox(
            'Backend Python introuvable',
            `Impossible de démarrer le backend Python.\n\nErreur : ${err.message}\n\nBinaire utilisé : ${finalBin}\n\nVérifiez que l'environnement conda "ada_v2" est bien créé ou que python3 est installé.`
        );
    });

    pythonProcess.on('exit', (code, signal) => {
        if (code !== 0 && code !== null) {
            console.error(`[Python] Process exited with code ${code} (signal: ${signal})`);
        } else {
            console.log(`[Python] Process exited cleanly (code: ${code})`);
        }
    });

    pythonProcess.stdout.on('data', (data) => {
        console.log(`[Python]: ${data}`);
    });

    pythonProcess.stderr.on('data', (data) => {
        console.error(`[Python Error]: ${data}`);
    });
}

// ─── CONTENT SECURITY POLICY ─────────────────────────────────────────────────
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

    checkBackendPort(8000).then((isTaken) => {
        if (isTaken) {
            console.log('Port 8000 is taken. Assuming backend is already running manually.');
            waitForBackend().then(createWindow);
        } else {
            startPythonBackend();
            // Give it a moment to start, then wait for health check
            setTimeout(() => {
                waitForBackend().then(createWindow);
            }, 1000);
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

function waitForBackend(maxRetries = 30) {
    return new Promise((resolve) => {
        let attempts = 0;

        const check = () => {
            const http = require('http');
            const req = http.get('http://127.0.0.1:8000/status', (res) => {
                if (res.statusCode === 200) {
                    console.log('Backend is ready!');
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

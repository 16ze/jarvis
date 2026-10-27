import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

// https://vitejs.dev/config/
export default defineConfig({
    plugins: [react()],
    base: './', // Important for Electron
    server: {
        port: 5173,
        allowedHosts: true,
    },
    build: {
        rollupOptions: {
            input: {
                // UI principale
                main: resolve(__dirname, 'index.html'),
                // Vignette flottante Jarvis (fenêtre Electron séparée)
                widget: resolve(__dirname, 'widget.html'),
                // Client WebXR (casque VR/MR) — Couche A
                xr: resolve(__dirname, 'xr.html'),
            },
        },
    },
})

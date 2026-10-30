/// <reference types="vitest" />
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
                main: resolve(import.meta.dirname, 'index.html'),
                // Vignette flottante Jarvis (fenêtre Electron séparée)
                widget: resolve(import.meta.dirname, 'widget.html'),
                // Client WebXR (casque VR/MR) — Couche A
                xr: resolve(import.meta.dirname, 'xr.html'),
                // « Yeux » d'Ada : flux caméra (tél/webcam) -> vision — Couche B
                eye: resolve(import.meta.dirname, 'eye.html'),
            },
            output: {
                // Code-splitting : on isole les grosses dépendances vendors dans
                // des chunks dédiés pour que le chunk applicatif principal passe
                // sous le seuil de 500 kB (le warning rollup disparaît pour l'app).
                // Les vendors three.js restent volumineux — c'est attendu et isolé.
                manualChunks(id) {
                    if (!id.includes('node_modules')) return undefined
                    // Pile 3D (three + wrappers react-three) — gros par nature.
                    if (
                        /[\\/]node_modules[\\/](three|@react-three)[\\/]/.test(id)
                    ) {
                        return 'vendor-three'
                    }
                    // Pile Markdown (react-markdown + coloration + parsing micromark).
                    if (
                        /[\\/]node_modules[\\/](react-markdown|rehype-highlight|lowlight|highlight\.js|hast[^\\/]*|micromark[^\\/]*|mdast[^\\/]*|remark[^\\/]*|unified|unist[^\\/]*|vfile[^\\/]*|property-information|space-separated-tokens|comma-separated-tokens|devlop|decode-named-character-reference|character-entities[^\\/]*|html-url-attributes|trim-lines|zwitch|ccount|escape-string-regexp|markdown-table|bail|is-plain-obj|trough|extend)[\\/]/.test(
                            id
                        )
                    ) {
                        return 'vendor-markdown'
                    }
                    return undefined
                },
            },
        },
    },
    test: {
        environment: 'jsdom',
        globals: true,
        setupFiles: ['./src/test/setup.js'],
        include: ['src/**/*.{test,spec}.{js,jsx}'],
        css: false,
    },
})

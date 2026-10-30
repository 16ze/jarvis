#!/usr/bin/env node
/*
 * Smoke-test de rendu — garde-fou anti « écran blanc ».
 *
 * Suppose qu'un serveur vite sert déjà l'application (par défaut localhost:5173 ;
 * surchargeable via SMOKE_URL). La CI lance `npm run web` en arrière-plan puis
 * `npx wait-on tcp:5173` avant d'appeler ce script.
 *
 * Charge l'app en Chromium headless sur un gabarit desktop ET mobile et échoue
 * si une erreur de page survient au render (p.ex. un ReferenceError/TDZ comme
 * « Cannot access 'adaSpeaking' before initialization ») ou si #root reste vide.
 * Les erreurs console de WebSocket (pas de backend en CI) sont ignorées.
 *
 * Sortie : 0 si tout rend, 1 sinon.
 */
const URL = process.env.SMOKE_URL || 'http://localhost:5173/';
const MIN_ROOT_LEN = 500;
const VIEWPORTS = [
    { name: 'desktop', width: 1280, height: 800 },
    { name: 'mobile', width: 390, height: 844 },
];

(async () => {
    const { chromium } = require('playwright');
    let failed = false;
    let browser;
    try {
        // --no-sandbox : requis sur la plupart des runners CI (conteneur non-root).
        // --no-proxy-server : le serveur local ne doit jamais passer par un proxy
        // (sans effet en CI ; indispensable dans un environnement derrière proxy).
        browser = await chromium.launch({ args: ['--no-sandbox', '--no-proxy-server'] });
    } catch (e) {
        console.log(`::error::smoke: échec du lancement de Chromium — ${e.message.split('\n')[0]}`);
        process.exit(1);
    }
    try {
        for (const vp of VIEWPORTS) {
            const page = await browser.newPage({ viewport: { width: vp.width, height: vp.height } });
            const pageErrors = [];
            page.on('pageerror', (e) => pageErrors.push(String((e && (e.stack || e.message)) || e)));
            try {
                await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 20000 });
            } catch (e) {
                pageErrors.push('goto: ' + e.message);
            }
            // Attente active : sur un runner à froid, vite pré-optimise les deps au
            // 1er chargement → #root peut rester vide quelques secondes. On patiente
            // jusqu'à 20 s qu'il se remplisse (tant qu'aucune erreur de page).
            try {
                await page.waitForFunction(
                    (min) => (document.getElementById('root')?.innerHTML || '').length >= min,
                    MIN_ROOT_LEN,
                    { timeout: 20000 }
                );
            } catch (_) {
                /* restera signalé par rootLen ci-dessous */
            }
            const rootLen = await page.evaluate(
                () => (document.getElementById('root')?.innerHTML || '').length
            );
            await page.close();

            const ok = pageErrors.length === 0 && rootLen >= MIN_ROOT_LEN;
            console.log(`[smoke:${vp.name}] root=${rootLen} pageErrors=${pageErrors.length} -> ${ok ? 'OK' : 'ECHEC'}`);
            if (!ok) {
                failed = true;
                // Annotations GitHub (visibles même sans accès aux logs bruts).
                if (rootLen < MIN_ROOT_LEN) {
                    console.log(`::error::[smoke:${vp.name}] #root quasi vide (${rootLen} < ${MIN_ROOT_LEN})`);
                }
                pageErrors.slice(0, 3).forEach((e) => {
                    const line = e.split('\n')[0];
                    console.error('  - ' + line);
                    console.log(`::error::[smoke:${vp.name}] ${line}`);
                });
            }
        }
    } finally {
        if (browser) await browser.close().catch(() => {});
    }
    process.exit(failed ? 1 : 0);
})();

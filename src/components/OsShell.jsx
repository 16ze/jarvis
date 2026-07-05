import React, { useEffect, useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
    Menu, X, Home, Terminal as TerminalIcon, Activity, Cpu, Brain,
    Lightbulb, Printer, Box, FolderOpen, Globe, Settings, ChevronRight,
    Wifi, WifiOff, ShieldCheck, ShieldAlert,
} from 'lucide-react';

/**
 * OsShell — couche de navigation de l'OS IA Ada.
 *
 * Menu hamburger + drawer animé donnant accès à des écrans dédiés. La page
 * principale (visualiseur vocal) reste intacte : OsShell est une surcouche.
 *
 * Deux types d'écrans :
 *  - RÉUTILISÉS : ouvrent les fenêtres existantes via `openWindow(key)`
 *    (domotique, imprimante, CAO, documents, terminal, réglages, navigateur).
 *  - NATIFS : rendus plein-cadre par OsShell (accueil, observabilité, agents).
 *
 * Ada elle-même peut naviguer : le backend émet `os_navigate` { screen } sur
 * le socket → l'écran correspondant s'ouvre.
 */

// Catalogue des agents/capacités de Jarvis (écran "Agents").
const AGENTS = [
    { name: 'Recherche', desc: 'Recherche multi-sources approfondie', tool: 'run_research' },
    { name: 'Tâches', desc: 'Exécution autonome de tâches longues', tool: 'run_task' },
    { name: 'Anticipation', desc: 'Suggestions proactives selon le contexte', tool: 'anticipate' },
    { name: 'Monitoring', desc: 'Surveillance continue en arrière-plan', tool: 'start_monitoring' },
    { name: 'Contrôle PC', desc: 'Pilotage local du Mac (apps, saisie, actions)', tool: 'execute_pc_task' },
    { name: 'Navigateur', desc: 'Navigation web autonome (Playwright)', tool: 'advanced_web_navigation' },
    { name: 'CAO 3D', desc: 'Génération de modèles paramétriques + impression', tool: 'generate_cad' },
    { name: 'Vision', desc: 'Détection d\'objets et analyse de scène', tool: 'detect_objects' },
    { name: 'Domotique', desc: 'Lumières, prises, caméra PTZ (Tuya)', tool: 'control_light' },
    { name: 'Mémoire', desc: 'Mémoire vectorielle persistante (RAG)', tool: 'search_memory' },
    { name: 'Auto-correction', desc: 'Correction de ses propres erreurs de code', tool: 'self_correct_file' },
];

// Définition des entrées de navigation.
const NAV = [
    { key: 'home', label: 'Accueil', icon: Home, kind: 'native', group: 'Système' },
    { key: 'observability', label: 'Observabilité', icon: Activity, kind: 'native', group: 'Système' },
    { key: 'agents', label: 'Agents & capacités', icon: Cpu, kind: 'native', group: 'Système' },
    { key: 'terminal', label: 'Terminal', icon: TerminalIcon, kind: 'window', group: 'Système' },
    { key: 'domotique', label: 'Domotique', icon: Lightbulb, kind: 'window', group: 'Périphériques' },
    { key: 'printer', label: 'Impression 3D', icon: Printer, kind: 'window', group: 'Périphériques' },
    { key: 'cad', label: 'CAO', icon: Box, kind: 'window', group: 'Périphériques' },
    { key: 'documents', label: 'Documents', icon: FolderOpen, kind: 'window', group: 'Espace' },
    { key: 'workspace', label: 'Navigateur / Recherche', icon: Globe, kind: 'window', group: 'Espace' },
    { key: 'settings', label: 'Réglages', icon: Settings, kind: 'window', group: 'Système' },
];

const GROUP_ORDER = ['Système', 'Périphériques', 'Espace'];

export default function OsShell({ socket, status = {}, brain = null, openWindow }) {
    const [drawerOpen, setDrawerOpen] = useState(false);
    const [screen, setScreen] = useState(null); // écran natif actif (null = accueil vocal)
    const [logs, setLogs] = useState([]);

    // Flux d'observabilité : on agrège les événements déjà émis par le backend.
    useEffect(() => {
        if (!socket) return;
        const pushLog = (kind, text) => {
            setLogs((prev) => [
                { t: Date.now(), kind, text: String(text).slice(0, 400) },
                ...prev,
            ].slice(0, 200));
        };
        const onTerminal = (d) => pushLog('term', `${d.command ? d.command + ' → ' : ''}${d.output ?? ''}`);
        const onHealth = (d) => pushLog('health', typeof d === 'string' ? d : JSON.stringify(d));
        const onStatus = (d) => pushLog('status', d?.msg ?? JSON.stringify(d));
        const onNavigate = (d) => {
            const target = d?.screen;
            if (!target) return;
            const entry = NAV.find((n) => n.key === target);
            if (!entry) return;
            if (entry.kind === 'window') openWindow?.(entry.key);
            else setScreen(target === 'home' ? null : target);
            setDrawerOpen(false);
        };
        socket.on('terminal_output', onTerminal);
        socket.on('health_report', onHealth);
        socket.on('status', onStatus);
        socket.on('os_navigate', onNavigate);
        return () => {
            socket.off('terminal_output', onTerminal);
            socket.off('health_report', onHealth);
            socket.off('status', onStatus);
            socket.off('os_navigate', onNavigate);
        };
    }, [socket, openWindow]);

    const select = (entry) => {
        setDrawerOpen(false);
        if (entry.kind === 'window') {
            openWindow?.(entry.key);
            return;
        }
        setScreen(entry.key === 'home' ? null : entry.key);
    };

    const grouped = useMemo(() => {
        const g = {};
        for (const n of NAV) (g[n.group] ||= []).push(n);
        return g;
    }, []);

    return (
        <>
            {/* Bouton hamburger — coin haut-gauche, au-dessus de tout */}
            <button
                onClick={() => setDrawerOpen(true)}
                aria-label="Ouvrir le menu"
                className="fixed top-6 left-6 z-[60] w-11 h-11 rounded-2xl bg-white/70 backdrop-blur-md border border-blue-100 shadow-sm flex items-center justify-center text-[#10294d] hover:bg-white transition-colors"
                style={{ WebkitAppRegion: 'no-drag' }}
            >
                <Menu size={20} />
            </button>

            {/* Overlay + Drawer */}
            <AnimatePresence>
                {drawerOpen && (
                    <>
                        <motion.div
                            className="fixed inset-0 z-[65] bg-[#0a1830]/20 backdrop-blur-[2px]"
                            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                            onClick={() => setDrawerOpen(false)}
                        />
                        <motion.aside
                            className="fixed top-0 left-0 z-[70] h-full w-[320px] bg-white/85 backdrop-blur-xl border-r border-blue-100 shadow-2xl flex flex-col"
                            initial={{ x: -340 }} animate={{ x: 0 }} exit={{ x: -340 }}
                            transition={{ type: 'spring', stiffness: 320, damping: 32 }}
                        >
                            <div className="flex items-center justify-between px-6 py-6">
                                <div className="flex items-center gap-2 text-[#10294d]">
                                    <Brain size={20} />
                                    <span className="font-bold tracking-wide">ADA OS</span>
                                </div>
                                <button onClick={() => setDrawerOpen(false)} className="text-[#10294d]/60 hover:text-[#10294d]">
                                    <X size={20} />
                                </button>
                            </div>

                            <nav className="flex-1 overflow-y-auto px-3 pb-6">
                                {GROUP_ORDER.map((group) => (
                                    <div key={group} className="mb-4">
                                        <div className="px-3 mb-1 text-[10px] uppercase tracking-widest text-[#10294d]/40">{group}</div>
                                        {(grouped[group] || []).map((entry) => {
                                            const Icon = entry.icon;
                                            const active = screen === entry.key || (entry.key === 'home' && screen === null);
                                            return (
                                                <button
                                                    key={entry.key}
                                                    onClick={() => select(entry)}
                                                    className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-colors ${active ? 'bg-blue-500/10 text-blue-700' : 'text-[#10294d]/80 hover:bg-blue-500/5'}`}
                                                >
                                                    <Icon size={17} />
                                                    <span className="flex-1 text-left">{entry.label}</span>
                                                    <ChevronRight size={14} className="opacity-30" />
                                                </button>
                                            );
                                        })}
                                    </div>
                                ))}
                            </nav>

                            <StatusFooter status={status} />
                        </motion.aside>
                    </>
                )}
            </AnimatePresence>

            {/* Écrans natifs plein-cadre */}
            <AnimatePresence>
                {screen && (
                    <motion.div
                        className="fixed inset-0 z-[55] bg-[#f4f8ff]/95 backdrop-blur-xl overflow-y-auto"
                        initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 12 }}
                    >
                        <ScreenHeader title={NAV.find((n) => n.key === screen)?.label} onClose={() => setScreen(null)} />
                        <div className="max-w-5xl mx-auto px-8 pb-16">
                            {screen === 'observability' && <ObservabilityScreen logs={logs} status={status} brain={brain} />}
                            {screen === 'agents' && <AgentsScreen socket={socket} />}
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </>
    );
}

function ScreenHeader({ title, onClose }) {
    return (
        <div className="sticky top-0 z-10 flex items-center justify-between px-8 py-5 bg-[#f4f8ff]/80 backdrop-blur border-b border-blue-100">
            <h2 className="text-lg font-bold text-[#10294d] tracking-wide">{title}</h2>
            <button onClick={onClose} className="w-9 h-9 rounded-xl bg-white/70 border border-blue-100 flex items-center justify-center text-[#10294d]/70 hover:text-[#10294d]">
                <X size={18} />
            </button>
        </div>
    );
}

function StatusFooter({ status }) {
    const connected = !!status.socketConnected;
    const authed = !!status.isAuthenticated;
    return (
        <div className="px-6 py-4 border-t border-blue-100 flex items-center gap-4 text-[11px] text-[#10294d]/70">
            <span className="flex items-center gap-1.5">
                {connected ? <Wifi size={13} className="text-emerald-600" /> : <WifiOff size={13} className="text-red-500" />}
                {connected ? 'Connecté' : 'Hors ligne'}
            </span>
            <span className="flex items-center gap-1.5">
                {authed ? <ShieldCheck size={13} className="text-emerald-600" /> : <ShieldAlert size={13} className="text-amber-500" />}
                {authed ? 'Authentifié' : 'Verrouillé'}
            </span>
        </div>
    );
}

function ObservabilityScreen({ logs, status, brain }) {
    const tiles = [
        { label: 'Connexion', value: status.socketConnected ? 'active' : 'inactive' },
        { label: 'Authentification', value: status.isAuthenticated ? 'ok' : 'verrouillé' },
        { label: 'Imprimantes', value: String(status.printerCount ?? 0) },
        { label: 'Humeur (brain)', value: brain?.mood ?? '—' },
    ];
    return (
        <div className="pt-8">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
                {tiles.map((t) => (
                    <div key={t.label} className="rounded-2xl bg-white/70 border border-blue-100 px-4 py-3">
                        <div className="text-[10px] uppercase tracking-widest text-[#10294d]/40">{t.label}</div>
                        <div className="text-lg font-semibold text-[#10294d] mt-1">{t.value}</div>
                    </div>
                ))}
            </div>
            <div className="text-[11px] uppercase tracking-widest text-[#10294d]/40 mb-2">Flux d'activité</div>
            <div className="rounded-2xl bg-[#0a1830] text-[#cfe0ff] font-mono text-xs p-4 h-[52vh] overflow-y-auto">
                {logs.length === 0 && <div className="text-[#cfe0ff]/40">En attente d'activité…</div>}
                {logs.map((l, i) => (
                    <div key={i} className="py-0.5 leading-relaxed">
                        <span className="text-[#5b86c9]">{new Date(l.t).toLocaleTimeString()}</span>{' '}
                        <span className="text-[#7fa8e8]">[{l.kind}]</span>{' '}
                        <span className="whitespace-pre-wrap break-words">{l.text}</span>
                    </div>
                ))}
            </div>
        </div>
    );
}

function AgentsScreen({ socket }) {
    const trigger = (agent) => {
        // Laisse Ada exécuter : on envoie une intention textuelle simple.
        socket?.emit?.('user_input', { text: `Utilise l'agent ${agent.name}.` });
    };
    return (
        <div className="pt-8 grid grid-cols-1 md:grid-cols-2 gap-3">
            {AGENTS.map((a) => (
                <div key={a.name} className="rounded-2xl bg-white/70 border border-blue-100 px-5 py-4 flex items-start justify-between gap-3">
                    <div>
                        <div className="font-semibold text-[#10294d]">{a.name}</div>
                        <div className="text-xs text-[#10294d]/60 mt-0.5">{a.desc}</div>
                        <code className="text-[10px] text-blue-600/70">{a.tool}</code>
                    </div>
                    <button
                        onClick={() => trigger(a)}
                        className="shrink-0 text-xs px-3 py-1.5 rounded-lg bg-blue-500/10 text-blue-700 hover:bg-blue-500/20 transition-colors"
                    >
                        Lancer
                    </button>
                </div>
            ))}
        </div>
    );
}

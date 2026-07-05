import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Wifi, WifiOff, ShieldCheck, ShieldAlert } from 'lucide-react';

/**
 * OsShell — hôte des écrans natifs de l'OS Ada.
 *
 * La navigation se fait par le DOCK central existant (ToolsModule), pas par un
 * menu à part. OsShell est un simple conteneur contrôlé : App décide de l'écran
 * actif (`screen`) et OsShell le rend en plein cadre par-dessus la vue vocale
 * qui reste intacte.
 *
 * Écrans natifs : Observabilité (flux d'activité live) et Agents (capacités).
 * Ada peut aussi naviguer : le backend émet `os_navigate` { screen } →
 * `onNavigate` est appelé.
 */

const AGENTS = [
    { name: 'Recherche web', desc: 'Résultats web récents (Brave/DuckDuckGo)', tool: 'web_search' },
    { name: 'Recherche approfondie', desc: 'Recherche multi-sources', tool: 'run_research' },
    { name: 'Tâches', desc: 'Exécution autonome de tâches longues', tool: 'run_task' },
    { name: 'Anticipation', desc: 'Suggestions proactives selon le contexte', tool: 'anticipate' },
    { name: 'Monitoring', desc: 'Surveillance continue en arrière-plan', tool: 'start_monitoring' },
    { name: 'Contrôle PC', desc: 'Pilotage local du Mac (apps, saisie, actions)', tool: 'execute_pc_task' },
    { name: 'Navigateur', desc: 'Navigation web autonome (Playwright)', tool: 'advanced_web_navigation' },
    { name: 'CAO 3D', desc: 'Modèles paramétriques + impression', tool: 'generate_cad' },
    { name: 'Vision', desc: 'Détection d\'objets et analyse de scène', tool: 'detect_objects' },
    { name: 'Domotique', desc: 'Lumières, prises, caméra PTZ (Tuya)', tool: 'control_light' },
    { name: 'Mémoire', desc: 'Mémoire vectorielle persistante (RAG)', tool: 'search_memory' },
    { name: 'Auto-correction', desc: 'Correction de ses propres erreurs de code', tool: 'self_correct_file' },
];

const TITLES = { observability: 'Observabilité', agents: 'Agents & capacités' };

export default function OsShell({ socket, status = {}, brain = null, screen = null, onClose, onNavigate }) {
    const [logs, setLogs] = useState([]);

    // Flux d'observabilité : agrège les événements déjà émis par le backend.
    useEffect(() => {
        if (!socket) return;
        const push = (kind, text) => setLogs((prev) => [
            { t: Date.now(), kind, text: String(text).slice(0, 400) }, ...prev,
        ].slice(0, 200));
        const onTerminal = (d) => push('term', `${d.command ? d.command + ' → ' : ''}${d.output ?? ''}`);
        const onHealth = (d) => push('health', typeof d === 'string' ? d : JSON.stringify(d));
        const onStatus = (d) => push('status', d?.msg ?? JSON.stringify(d));
        const onNav = (d) => { if (d?.screen) onNavigate?.(d.screen); };
        socket.on('terminal_output', onTerminal);
        socket.on('health_report', onHealth);
        socket.on('status', onStatus);
        socket.on('os_navigate', onNav);
        return () => {
            socket.off('terminal_output', onTerminal);
            socket.off('health_report', onHealth);
            socket.off('status', onStatus);
            socket.off('os_navigate', onNav);
        };
    }, [socket, onNavigate]);

    return (
        <AnimatePresence>
            {screen && (
                <motion.div
                    className="fixed inset-0 z-[55] bg-[#f4f8ff]/95 backdrop-blur-xl overflow-y-auto"
                    initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 12 }}
                >
                    <div className="sticky top-0 z-10 flex items-center justify-between px-8 py-5 bg-[#f4f8ff]/80 backdrop-blur border-b border-blue-100">
                        <h2 className="text-lg font-bold text-[#10294d] tracking-wide">{TITLES[screen]}</h2>
                        <button onClick={onClose} className="w-9 h-9 rounded-xl bg-white/70 border border-blue-100 flex items-center justify-center text-[#10294d]/70 hover:text-[#10294d]">
                            <X size={18} />
                        </button>
                    </div>
                    <div className="max-w-5xl mx-auto px-8 pb-16">
                        {screen === 'observability' && <ObservabilityScreen logs={logs} status={status} brain={brain} />}
                        {screen === 'agents' && <AgentsScreen socket={socket} />}
                    </div>
                </motion.div>
            )}
        </AnimatePresence>
    );
}

function ObservabilityScreen({ logs, status, brain }) {
    const tiles = [
        { label: 'Connexion', value: status.socketConnected ? 'active' : 'inactive', icon: status.socketConnected ? <Wifi size={14} className="text-emerald-600" /> : <WifiOff size={14} className="text-red-500" /> },
        { label: 'Authentification', value: status.isAuthenticated ? 'ok' : 'verrouillé', icon: status.isAuthenticated ? <ShieldCheck size={14} className="text-emerald-600" /> : <ShieldAlert size={14} className="text-amber-500" /> },
        { label: 'Imprimantes', value: String(status.printerCount ?? 0) },
        { label: 'Humeur (brain)', value: brain?.mood ?? '—' },
    ];
    return (
        <div className="pt-8">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
                {tiles.map((t) => (
                    <div key={t.label} className="rounded-2xl bg-white/70 border border-blue-100 px-4 py-3">
                        <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-widest text-[#10294d]/40">{t.icon}{t.label}</div>
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
    const trigger = (agent) => socket?.emit?.('user_input', { text: `Utilise l'agent ${agent.name}.` });
    return (
        <div className="pt-8 grid grid-cols-1 md:grid-cols-2 gap-3">
            {AGENTS.map((a) => (
                <div key={a.name} className="rounded-2xl bg-white/70 border border-blue-100 px-5 py-4 flex items-start justify-between gap-3">
                    <div>
                        <div className="font-semibold text-[#10294d]">{a.name}</div>
                        <div className="text-xs text-[#10294d]/60 mt-0.5">{a.desc}</div>
                        <code className="text-[10px] text-blue-600/70">{a.tool}</code>
                    </div>
                    <button onClick={() => trigger(a)} className="shrink-0 text-xs px-3 py-1.5 rounded-lg bg-blue-500/10 text-blue-700 hover:bg-blue-500/20 transition-colors">
                        Lancer
                    </button>
                </div>
            ))}
        </div>
    );
}

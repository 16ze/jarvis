import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
    Activity,
    ArrowLeft,
    BookmarkPlus,
    ChevronLeft,
    ExternalLink,
    FileText,
    Folder,
    Globe,
    Plus,
    RotateCw,
    Search,
    X,
} from 'lucide-react';

const electronBridge = (() => {
    try {
        const electron = window.require('electron');
        return { ipcRenderer: electron.ipcRenderer };
    } catch {
        return { ipcRenderer: null };
    }
})();

let __tabIdCounter = 0;
const generateTabId = (prefix) => `${prefix}-${Date.now()}-${++__tabIdCounter}`;

const depthOptions = ['quick', 'standard', 'deep'];

const extractDomain = (url) => {
    try {
        return new URL(url).hostname.replace(/^www\./, '');
    } catch {
        return url;
    }
};

const normalizeHttpUrl = (url) => {
    if (!url) return '';
    const trimmed = String(url).trim();
    if (/^https?:\/\//i.test(trimmed)) return trimmed;
    if (/^\/\//.test(trimmed)) return `https:${trimmed}`;
    return `https://${trimmed}`;
};

const WorkspaceShell = ({
    socket,
    workspaceState,
    workspaceEvents,
    workspaceStatus,
    researchResult,
    onClose,
}) => {
    const [view, setView] = useState('menu');
    const [workspaceName, setWorkspaceName] = useState('');
    const [workspaceGoal, setWorkspaceGoal] = useState('');
    const [query, setQuery] = useState('');
    const [depth, setDepth] = useState('standard');
    const [noteTitle, setNoteTitle] = useState('');
    const [noteContent, setNoteContent] = useState('');

    const groupedItems = useMemo(() => {
        const groups = { note: [], source: [], artifact: [], capture: [], task: [] };
        for (const item of workspaceState?.items || []) {
            if (groups[item.kind]) groups[item.kind].push(item);
        }
        return groups;
    }, [workspaceState]);

    const createWorkspace = () => {
        if (!workspaceName.trim()) return;
        socket.emit('workspace_create', { name: workspaceName, goal: workspaceGoal });
        setWorkspaceName('');
        setWorkspaceGoal('');
    };

    const launchResearch = () => {
        if (!query.trim()) return;
        socket.emit('workspace_research', { query, depth, synthesize: false });
        setQuery('');
    };

    const saveNote = () => {
        if (!noteTitle.trim() || !noteContent.trim()) return;
        socket.emit('workspace_save_note', {
            title: noteTitle,
            content: noteContent,
            tags: ['ada-os'],
        });
        setNoteTitle('');
        setNoteContent('');
    };

    const shell = (
        <section className="fixed inset-6 z-[420] overflow-hidden rounded-ada-lg ada-float text-ink">
            <div className="absolute inset-0 pointer-events-none" />

            <header className="relative z-10 flex h-16 items-center justify-between border-b border-line px-6">
                <div className="min-w-0">
                    <div className="text-xs uppercase tracking-[0.08em] text-accent">ADA OS Workspace</div>
                    <h2 className="truncate text-lg font-semibold">{workspaceState?.activeWorkspace || 'default'}</h2>
                </div>
                <div className="flex items-center gap-2">
                    {view !== 'menu' && (
                        <button
                            type="button"
                            onClick={() => setView('menu')}
                            className="workspace-icon-button"
                            aria-label="Retour au menu Workspace"
                            title="Retour"
                        >
                            <ArrowLeft size={19} />
                        </button>
                    )}
                    <button
                        type="button"
                        onClick={onClose}
                        className="workspace-icon-button"
                        aria-label="Fermer le workspace"
                        title="Fermer"
                    >
                        <X size={20} />
                    </button>
                </div>
            </header>

            {view === 'menu' && (
                <WorkspaceMenu
                    groupedItems={groupedItems}
                    workspaceName={workspaceName}
                    workspaceGoal={workspaceGoal}
                    setWorkspaceName={setWorkspaceName}
                    setWorkspaceGoal={setWorkspaceGoal}
                    createWorkspace={createWorkspace}
                    setView={setView}
                    workspaceStatus={workspaceStatus}
                />
            )}

            {view === 'search' && (
                <AdaSearchView
                    socket={socket}
                    workspaceStatus={workspaceStatus}
                    researchResult={researchResult}
                />
            )}

            {view === 'notes' && (
                <NotesView
                    noteTitle={noteTitle}
                    noteContent={noteContent}
                    setNoteTitle={setNoteTitle}
                    setNoteContent={setNoteContent}
                    saveNote={saveNote}
                    notes={groupedItems.note}
                />
            )}

            {view === 'files' && <FilesView items={workspaceState?.items || []} />}

            {view === 'activity' && (
                <ActivityView workspaceStatus={workspaceStatus} workspaceEvents={workspaceEvents} />
            )}
        </section>
    );

    return createPortal(shell, document.body);
};

const WorkspaceMenu = ({
    groupedItems,
    workspaceName,
    workspaceGoal,
    setWorkspaceName,
    setWorkspaceGoal,
    createWorkspace,
    setView,
    workspaceStatus,
}) => {
    const actions = [
        {
            key: 'search',
            label: 'AdaSearch',
            meta: `${groupedItems.source.length} sources`,
            icon: <Search size={30} />,
            onClick: () => setView('search'),
        },
        {
            key: 'notes',
            label: 'Notes',
            meta: `${groupedItems.note.length} notes`,
            icon: <FileText size={30} />,
            onClick: () => setView('notes'),
        },
        {
            key: 'files',
            label: 'Fichiers',
            meta: `${groupedItems.artifact.length} livrables`,
            icon: <Folder size={30} />,
            onClick: () => setView('files'),
        },
        {
            key: 'activity',
            label: 'Activité',
            meta: `${groupedItems.task.length} tâches`,
            icon: <Activity size={30} />,
            onClick: () => setView('activity'),
        },
    ];

    return (
        <div className="relative z-10 grid h-[calc(100%-4rem)] grid-cols-[minmax(0,1fr)_310px] gap-6 p-8">
            <main className="flex min-h-0 flex-col items-center justify-center">
                <div className="grid w-full max-w-[820px] grid-cols-2 gap-7">
                    {actions.map((action) => (
                        <button
                            key={action.key}
                            type="button"
                            onClick={action.onClick}
                            className="workspace-action-glass group"
                            aria-label={action.label}
                            title={action.label}
                        >
                            <span className="workspace-action-icon">{action.icon}</span>
                            <span className="text-[26px] font-semibold leading-none text-ink">{action.label}</span>
                            <span className="text-xs uppercase tracking-[0.08em] text-accent">{action.meta}</span>
                        </button>
                    ))}
                </div>
            </main>

            <aside className="flex min-h-0 flex-col justify-center">
                <div className="ada-glass-panel rounded-ada p-4">
                    <div className="mb-3 text-xs uppercase tracking-[0.08em] text-accent">Workspace actif</div>
                    <input
                        value={workspaceName}
                        onChange={(event) => setWorkspaceName(event.target.value)}
                        placeholder="Nom"
                        className="workspace-field mb-2"
                    />
                    <textarea
                        value={workspaceGoal}
                        onChange={(event) => setWorkspaceGoal(event.target.value)}
                        placeholder="Objectif"
                        className="workspace-field h-24 resize-none py-2"
                    />
                    <button
                        type="button"
                        onClick={createWorkspace}
                        className="mt-3 flex h-10 w-full items-center justify-center gap-2 rounded-ada bg-accent px-3 text-sm font-medium text-white transition hover:bg-accent/90"
                    >
                        <Plus size={16} />
                        Créer / ouvrir
                    </button>
                    {workspaceStatus?.message && (
                        <div className="mt-3 rounded-ada border border-line bg-accent/10 px-3 py-2 text-xs text-accent">
                            {workspaceStatus.message}
                        </div>
                    )}
                </div>
            </aside>
        </div>
    );
};

// ─── AdaSearch : navigateur intégré à onglets ───────────────────────────────
// Layout type Arc/Safari : TabBar en haut, contenu plein écran en dessous.
// Plusieurs onglets Search en parallèle possibles + onglets Page (webview).

const createSearchTab = (overrides = {}) => ({
    id: generateTabId('search'),
    kind: 'search',
    title: 'Recherche',
    query: '',
    depth: 'standard',
    results: [],
    lastQuery: '',
    synthesized: false,
    loading: false,
    ...overrides,
});

const createPageTab = (result) => ({
    id: generateTabId('page'),
    kind: 'page',
    title: result.title || extractDomain(result.url),
    url: normalizeHttpUrl(result.url),
    initialUrl: normalizeHttpUrl(result.url),
    savedItemId: result.savedItemId || null,
});

const AdaSearchView = ({ socket, researchResult, workspaceStatus }) => {
    const [tabs, setTabs] = useState(() => [createSearchTab()]);
    const [activeTabId, setActiveTabId] = useState(() => tabs[0]?.id);
    const pendingSearchTabIdRef = useRef(null);

    // Réception du payload backend → écriture dans l'onglet qui a lancé la recherche.
    useEffect(() => {
        if (!researchResult) return;
        const targetId = pendingSearchTabIdRef.current;
        if (!targetId) return;
        setTabs((prev) =>
            prev.map((tab) =>
                tab.id === targetId && tab.kind === 'search'
                    ? {
                          ...tab,
                          results: researchResult.results || [],
                          lastQuery: researchResult.query || tab.query,
                          synthesized: Boolean(researchResult.synthesized),
                          loading: false,
                          title: researchResult.query ? `« ${researchResult.query} »` : tab.title,
                      }
                    : tab,
            ),
        );
        pendingSearchTabIdRef.current = null;
    }, [researchResult]);

    const activeTab = tabs.find((tab) => tab.id === activeTabId) || tabs[0];

    const updateTab = (tabId, patch) => {
        setTabs((prev) => prev.map((tab) => (tab.id === tabId ? { ...tab, ...patch } : tab)));
    };

    const openNewSearchTab = () => {
        const tab = createSearchTab();
        setTabs((prev) => [...prev, tab]);
        setActiveTabId(tab.id);
    };

    const openResultInNewTab = (result) => {
        const tab = createPageTab(result);
        setTabs((prev) => [...prev, tab]);
        setActiveTabId(tab.id);
    };

    const closeTab = (tabId) => {
        setTabs((prev) => {
            const closingIndex = prev.findIndex((tab) => tab.id === tabId);
            const next = prev.filter((tab) => tab.id !== tabId);
            if (next.length === 0) {
                const fresh = createSearchTab();
                setActiveTabId(fresh.id);
                return [fresh];
            }
            if (tabId === activeTabId) {
                const fallback = next[closingIndex] || next[closingIndex - 1] || next[0];
                setActiveTabId(fallback.id);
            }
            return next;
        });
    };

    const launchResearchInTab = (tabId, query, depth) => {
        if (!query.trim() || !socket) return;
        pendingSearchTabIdRef.current = tabId;
        updateTab(tabId, { loading: true });
        socket.emit('workspace_research', { query, depth, synthesize: false });
    };

    const saveResultAsNote = (result) => {
        if (!result || !socket) return;
        const snippet = result.snippet || 'Aucun extrait disponible.';
        const content = [
            `# ${result.title}`,
            `[${result.url}](${result.url})`,
            '',
            `> ${snippet}`,
            '',
            '---',
            '_notes:_',
        ].join('\n');
        socket.emit('workspace_save_note', {
            title: result.title,
            content,
            tags: ['ada-os', 'research'],
        });
    };

    const savePageAsNote = (tab) => {
        if (!tab || !socket) return;
        const content = [
            `# ${tab.title}`,
            `[${tab.url}](${tab.url})`,
            '',
            '---',
            '_notes:_',
        ].join('\n');
        socket.emit('workspace_save_note', {
            title: tab.title,
            content,
            tags: ['ada-os', 'research', 'page'],
        });
    };

    return (
        <div className="relative z-10 flex h-[calc(100%-4rem)] flex-col">
            <TabBar
                tabs={tabs}
                activeTabId={activeTabId}
                onSelect={setActiveTabId}
                onClose={closeTab}
                onNew={openNewSearchTab}
            />
            <div className="min-h-0 flex-1 overflow-hidden bg-surface/80 backdrop-blur-md">
                {activeTab?.kind === 'search' && (
                    <SearchTabContent
                        tab={activeTab}
                        workspaceStatus={workspaceStatus}
                        onChangeQuery={(value) => updateTab(activeTab.id, { query: value })}
                        onChangeDepth={(value) => updateTab(activeTab.id, { depth: value })}
                        onLaunch={() => launchResearchInTab(activeTab.id, activeTab.query, activeTab.depth)}
                        onOpenResult={openResultInNewTab}
                        onSaveResultAsNote={saveResultAsNote}
                    />
                )}
                {activeTab?.kind === 'page' && (
                    <PageTabContent
                        key={activeTab.id}
                        tab={activeTab}
                        socket={socket}
                        onTitleChange={(title) => updateTab(activeTab.id, { title })}
                        onUrlChange={(url) => updateTab(activeTab.id, { url })}
                        onSaveAsNote={() => savePageAsNote(activeTab)}
                    />
                )}
            </div>
        </div>
    );
};

const TabBar = ({ tabs, activeTabId, onSelect, onClose, onNew }) => (
    <div className="flex items-end gap-1 border-b border-line bg-surface2 px-3 pt-2">
        <div className="flex flex-1 items-end gap-1 overflow-x-auto pb-0">
            {tabs.map((tab) => {
                const isActive = tab.id === activeTabId;
                const Icon = tab.kind === 'search' ? Search : Globe;
                return (
                    <div
                        key={tab.id}
                        role="button"
                        tabIndex={0}
                        onClick={() => onSelect(tab.id)}
                        onKeyDown={(event) => {
                            if (event.key === 'Enter' || event.key === ' ') onSelect(tab.id);
                        }}
                        className={`group flex h-9 min-w-[140px] max-w-[220px] cursor-pointer items-center gap-2 rounded-t-md border border-b-0 px-3 text-xs transition ${
                            isActive
                                ? 'border-line bg-surface text-ink shadow-ada-sm'
                                : 'border-transparent bg-transparent text-muted hover:bg-surface/60'
                        }`}
                    >
                        <Icon size={13} className={isActive ? 'text-accent' : 'text-muted'} />
                        <span className="min-w-0 flex-1 truncate text-left font-medium">{tab.title}</span>
                        <span
                            role="button"
                            tabIndex={-1}
                            onClick={(event) => {
                                event.stopPropagation();
                                onClose(tab.id);
                            }}
                            className="grid h-5 w-5 place-items-center rounded text-muted opacity-0 transition group-hover:opacity-100 hover:bg-ink/10 hover:text-ink"
                            aria-label={`Fermer ${tab.title}`}
                        >
                            <X size={12} />
                        </span>
                    </div>
                );
            })}
        </div>
        <button
            type="button"
            onClick={onNew}
            className="mb-0 grid h-9 w-9 place-items-center rounded-t-md text-muted transition hover:bg-surface/60 hover:text-ink"
            aria-label="Nouvelle recherche"
            title="Nouvelle recherche"
        >
            <Plus size={16} />
        </button>
    </div>
);

const SearchTabContent = ({
    tab,
    workspaceStatus,
    onChangeQuery,
    onChangeDepth,
    onLaunch,
    onOpenResult,
    onSaveResultAsNote,
}) => {
    const hasResults = tab.results?.length > 0;

    return (
        <div className="flex h-full flex-col">
            <div className="border-b border-line bg-surface2 p-5">
                <div className="mx-auto flex w-full max-w-[760px] items-center gap-3 rounded-full border border-line bg-surface px-4 py-3 shadow-ada">
                    <Search size={19} className="shrink-0 text-accent" />
                    <input
                        value={tab.query}
                        onChange={(event) => onChangeQuery(event.target.value)}
                        onKeyDown={(event) => {
                            if (event.key === 'Enter') onLaunch();
                        }}
                        placeholder="AdaSearch — recherche Brave"
                        className="h-8 min-w-0 flex-1 bg-transparent text-sm outline-none"
                        autoFocus
                    />
                    <select
                        value={tab.depth}
                        onChange={(event) => onChangeDepth(event.target.value)}
                        className="h-8 rounded-full border border-line bg-surface2 px-3 text-xs text-ink outline-none"
                    >
                        {depthOptions.map((option) => (
                            <option key={option} value={option}>{option}</option>
                        ))}
                    </select>
                    <button
                        type="button"
                        onClick={onLaunch}
                        disabled={tab.loading}
                        className="h-8 rounded-full bg-accent px-4 text-xs font-medium text-white transition hover:bg-accent/90 disabled:opacity-60"
                    >
                        {tab.loading ? 'Recherche…' : 'Rechercher'}
                    </button>
                </div>
                {(workspaceStatus?.message || hasResults) && (
                    <div className="mx-auto mt-3 flex w-full max-w-[760px] items-center justify-between text-[11px] text-muted">
                        <div className="text-accent">{workspaceStatus?.message || ''}</div>
                        {hasResults && (
                            <div>
                                {tab.results.length} résultats pour <span className="font-medium text-ink">« {tab.lastQuery} »</span>
                                {tab.synthesized && (
                                    <span className="ml-2 rounded-full bg-warn/15 px-2 py-0.5 text-warn">synthèse IA</span>
                                )}
                            </div>
                        )}
                    </div>
                )}
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
                <div className="mx-auto w-full max-w-[760px]">
                    {hasResults ? (
                        <div className="space-y-2">
                            {tab.results.map((result) => (
                                <ResultCard
                                    key={`${result.url}-${result.savedItemId || ''}`}
                                    result={result}
                                    onOpen={() => onOpenResult(result)}
                                    onSaveAsNote={() => onSaveResultAsNote(result)}
                                />
                            ))}
                        </div>
                    ) : (
                        <div className="grid h-full place-items-center pt-12 text-center text-sm text-muted">
                            <div>
                                <div className="mx-auto mb-4 grid h-16 w-16 place-items-center rounded-full border border-line bg-accent/10 text-accent">
                                    <Search size={28} />
                                </div>
                                <div className="text-base font-semibold text-ink">AdaSearch</div>
                                <div className="mt-1 text-xs text-muted">propulsé par Brave Search</div>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

const PageTabContent = ({ tab, socket, onTitleChange, onUrlChange, onSaveAsNote }) => {
    const [currentUrl, setCurrentUrl] = useState(tab.url);
    const [loading, setLoading] = useState(true);
    const [failed, setFailed] = useState(null);   // message d'échec → repli externe
    const [canGoBack, setCanGoBack] = useState(false);
    const webviewRef = useRef(null);

    // Le <webview> Electron n'existe que dans l'app packagée : hors Electron
    // (mode web), on garde le repli « ouvrir à l'extérieur ».
    const canEmbed = Boolean(electronBridge.ipcRenderer);

    useEffect(() => {
        setCurrentUrl(tab.url);
        onUrlChange(tab.url);
        onTitleChange(tab.title || extractDomain(tab.url));
    }, [onTitleChange, onUrlChange, tab.title, tab.url]);

    // Branchement des événements du navigateur intégré.
    useEffect(() => {
        const view = webviewRef.current;
        if (!view || !canEmbed) return undefined;

        const onStart = () => { setLoading(true); setFailed(null); };
        const onStop = () => {
            setLoading(false);
            try {
                const url = view.getURL?.();
                if (url) { setCurrentUrl(url); onUrlChange(url); }
                setCanGoBack(Boolean(view.canGoBack?.()));
            } catch { /* webview pas encore prêt */ }
        };
        const onTitle = (e) => { if (e?.title) onTitleChange(e.title); };
        const onFail = (e) => {
            // -3 = ERR_ABORTED (navigation annulée) : sans gravité.
            if (e?.errorCode === -3) return;
            setLoading(false);
            setFailed(e?.errorDescription || 'Chargement impossible');
        };

        view.addEventListener('did-start-loading', onStart);
        view.addEventListener('did-stop-loading', onStop);
        view.addEventListener('page-title-updated', onTitle);
        view.addEventListener('did-fail-load', onFail);
        return () => {
            view.removeEventListener('did-start-loading', onStart);
            view.removeEventListener('did-stop-loading', onStop);
            view.removeEventListener('page-title-updated', onTitle);
            view.removeEventListener('did-fail-load', onFail);
        };
    }, [canEmbed, onTitleChange, onUrlChange]);

    // ── Pilotage par Ada (cf. backend/browser_bridge.py) ──────────────────────
    // Ada envoie des commandes structurées ; on les exécute ici sur le webview
    // et on renvoie le résultat. Aucune exécution de JS arbitraire venant du
    // modèle : chaque action correspond à un extrait figé, écrit ici.
    useEffect(() => {
        if (!socket || !canEmbed) return undefined;

        const handle = async ({ id, action, ...params } = {}) => {
            const view = webviewRef.current;
            const reply = (ok, data = '', error = '') =>
                socket.emit('browser_result', { id, ok, data, error });
            if (!view) return reply(false, '', 'aucune page ouverte');

            const js = {
                read: `(() => (document.body?.innerText || '').slice(0, 6000))()`,
                click: `(() => {
                    const cible = ${JSON.stringify(String(params.text || '').toLowerCase())};
                    const noeuds = [...document.querySelectorAll(
                        'a,button,input[type=submit],input[type=button],[role=button],[role=link]')];
                    const el = noeuds.find(n => (
                        (n.innerText || n.value || n.getAttribute('aria-label') || '')
                    ).trim().toLowerCase().includes(cible));
                    if (!el) return 'INTROUVABLE';
                    el.scrollIntoView({block:'center'});
                    el.click();
                    return 'CLIQUE';
                })()`,
                fill: `(() => {
                    const cible = ${JSON.stringify(String(params.field || '').toLowerCase())};
                    const valeur = ${JSON.stringify(String(params.value ?? ''))};
                    const champs = [...document.querySelectorAll('input,textarea,select')]
                        .filter(c => c.type !== 'hidden');
                    const décrit = (c) => {
                        const lab = c.labels && c.labels[0] ? c.labels[0].innerText : '';
                        return [lab, c.placeholder, c.name, c.id, c.getAttribute('aria-label'),
                                c.type].filter(Boolean).join(' ').toLowerCase();
                    };
                    const el = champs.find(c => décrit(c).includes(cible));
                    if (!el) return 'INTROUVABLE';
                    const proto = el instanceof HTMLTextAreaElement
                        ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
                    const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
                    el.focus();
                    if (setter) setter.call(el, valeur); else el.value = valeur;
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    return 'REMPLI';
                })()`,
                submit: `(() => {
                    const actif = document.activeElement;
                    const form = (actif && actif.form) || document.querySelector('form');
                    if (form) { form.requestSubmit ? form.requestSubmit() : form.submit(); return 'VALIDE'; }
                    return 'AUCUN_FORMULAIRE';
                })()`,
            };

            const libellés = {
                INTROUVABLE: 'élément introuvable sur la page',
                CLIQUE: 'Élément cliqué.',
                REMPLI: 'Champ rempli.',
                VALIDE: 'Formulaire validé.',
                AUCUN_FORMULAIRE: 'aucun formulaire sur la page',
            };

            try {
                if (action === 'navigate') {
                    const url = normalizeHttpUrl(String(params.url || ''));
                    if (!url) return reply(false, '', 'URL invalide');
                    view.loadURL(url);
                    return reply(true, `Page ouverte : ${url}`);
                }
                if (action === 'back') { view.goBack(); return reply(true, 'Retour effectué.'); }
                if (action === 'url') return reply(true, view.getURL?.() || '');

                const code = js[action];
                if (!code) return reply(false, '', `action non supportée : ${action}`);
                const res = await view.executeJavaScript(code, true);
                if (res === 'INTROUVABLE' || res === 'AUCUN_FORMULAIRE') {
                    return reply(false, '', libellés[res]);
                }
                return reply(true, libellés[res] ?? String(res ?? ''));
            } catch (e) {
                return reply(false, '', String(e?.message || e));
            }
        };

        socket.on('browser_command', handle);
        return () => socket.off('browser_command', handle);
    }, [canEmbed, socket]);

    const goBack = () => { try { webviewRef.current?.goBack(); } catch { /* ignore */ } };
    const reload = () => {
        setFailed(null);
        try { webviewRef.current?.reload(); } catch { /* ignore */ }
    };

    const openExternal = () => {
        electronBridge.ipcRenderer?.send('ada-search-open-external', { url: currentUrl || tab.initialUrl });
    };

    return (
        <div className="flex h-full flex-col">
            <div className="flex items-center gap-2 border-b border-line bg-surface2 px-3 py-2">
                <button
                    type="button"
                    onClick={goBack}
                    className="grid h-8 w-8 place-items-center rounded-md text-muted transition hover:bg-ink/5 disabled:text-muted/40 disabled:hover:bg-transparent"
                    title="Retour"
                    aria-label="Retour"
                    disabled={!canEmbed || !canGoBack}
                >
                    <ChevronLeft size={16} />
                </button>
                <button
                    type="button"
                    onClick={reload}
                    disabled={!canEmbed}
                    className="grid h-8 w-8 place-items-center rounded-md text-muted transition hover:bg-ink/5 disabled:text-muted/40 disabled:hover:bg-transparent"
                    title="Recharger"
                    aria-label="Recharger"
                >
                    <RotateCw size={15} className={loading && canEmbed ? 'animate-spin' : ''} />
                </button>
                <div className="flex h-8 min-w-0 flex-1 items-center gap-2 truncate rounded-full border border-line bg-surface px-3 text-xs text-muted">
                    <Globe size={13} className="shrink-0 text-muted" />
                    <span className="truncate">{currentUrl}</span>
                </div>
                <button
                    type="button"
                    onClick={openExternal}
                    className="grid h-8 w-8 place-items-center rounded-md text-muted transition hover:bg-ink/5"
                    title="Ouvrir dans le navigateur système"
                    aria-label="Ouvrir dans le navigateur système"
                >
                    <ExternalLink size={14} />
                </button>
                <button
                    type="button"
                    onClick={onSaveAsNote}
                    className="flex h-8 items-center gap-1.5 rounded-md border border-line bg-surface px-3 text-xs font-medium text-accent transition hover:bg-accent/10"
                    title="Sauvegarder cette page comme note"
                >
                    <BookmarkPlus size={14} />
                    Note
                </button>
            </div>
            <div className="relative min-h-0 flex-1 bg-surface">
                {canEmbed && !failed ? (
                    // Navigateur intégré. Le contenu distant tourne sans Node,
                    // en sandbox et dans une session isolée (cf. electron/main.js).
                    <webview
                        ref={webviewRef}
                        src={tab.url}
                        className="h-full w-full"
                        partition="persist:ada-browser"
                        allowpopups="false"
                    />
                ) : (
                    <div className="grid h-full place-items-center px-6 text-center">
                        <div className="max-w-md">
                            <div className="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-full border border-line bg-accent/10 text-accent">
                                <Globe size={24} />
                            </div>
                            <div className="text-base font-semibold text-ink">
                                {failed ? 'Page non affichable ici' : 'Navigation externe'}
                            </div>
                            <p className="mt-2 text-sm leading-6 text-muted">
                                {failed
                                    ? `${failed}. Certains sites refusent l’affichage intégré — ouvre-la dans ton navigateur.`
                                    : 'Le navigateur intégré n’est disponible que dans l’application Ada.'}
                            </p>
                            <div className="mt-5 flex items-center justify-center gap-2">
                                {failed && (
                                    <button
                                        type="button"
                                        onClick={reload}
                                        className="rounded-ada border border-line px-4 py-2 text-xs font-medium text-muted transition hover:bg-surface2"
                                    >
                                        Réessayer
                                    </button>
                                )}
                                <button
                                    type="button"
                                    onClick={openExternal}
                                    className="rounded-ada bg-accent px-4 py-2 text-xs font-medium text-white transition hover:bg-accent/90"
                                >
                                    Ouvrir la page
                                </button>
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

const ResultCard = ({ result, onOpen, onSaveAsNote }) => {
    const domain = extractDomain(result.url);
    return (
        <article
            onClick={onOpen}
            className="group cursor-pointer rounded-ada px-4 py-3 transition hover:bg-surface2"
        >
            <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                    <div className="truncate text-[11px] text-muted">{domain}</div>
                    <h3 className="mt-0.5 truncate text-base font-medium text-accent group-hover:underline">
                        {result.title}
                    </h3>
                    <p className="mt-1 line-clamp-2 text-sm leading-5 text-muted">
                        {result.snippet || 'Aucun extrait disponible.'}
                    </p>
                </div>
                <button
                    type="button"
                    onClick={(event) => {
                        event.stopPropagation();
                        onSaveAsNote();
                    }}
                    className="grid h-8 w-8 shrink-0 place-items-center rounded-md text-muted opacity-0 transition group-hover:opacity-100 hover:bg-surface hover:text-accent"
                    title="Sauvegarder en note"
                    aria-label="Sauvegarder en note"
                >
                    <BookmarkPlus size={15} />
                </button>
            </div>
            {result.savedItemId && (
                <div className="mt-2 inline-flex items-center gap-1 rounded-full bg-accent/10 px-2 py-0.5 text-[10px] uppercase tracking-wider text-accent">
                    sauvegardé
                </div>
            )}
        </article>
    );
};

const NotesView = ({ noteTitle, noteContent, setNoteTitle, setNoteContent, saveNote, notes }) => (
    <div className="relative z-10 grid h-[calc(100%-4rem)] grid-cols-[minmax(0,1fr)_360px] gap-5 p-5">
        <main className="ada-glass-panel rounded-ada p-5">
            <input
                value={noteTitle}
                onChange={(event) => setNoteTitle(event.target.value)}
                placeholder="Titre"
                className="workspace-field mb-3"
            />
            <textarea
                value={noteContent}
                onChange={(event) => setNoteContent(event.target.value)}
                placeholder="Contenu"
                className="workspace-field h-[calc(100%-4rem)] resize-none py-3"
            />
            <button type="button" onClick={saveNote} className="mt-3 h-10 rounded-ada bg-accent px-4 text-sm font-medium text-white transition hover:bg-accent/90">
                Sauvegarder
            </button>
        </main>
        <aside className="min-h-0 overflow-y-auto rounded-ada border border-line bg-surface p-4">
            {notes.map((note) => <SourceRow key={note.id} item={note} />)}
        </aside>
    </div>
);

const FilesView = ({ items }) => (
    <div className="relative z-10 h-[calc(100%-4rem)] overflow-y-auto p-6">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {items.map((item) => (
                <article key={item.id} className="rounded-ada border border-line bg-surface p-4 shadow-ada">
                    <div className="mb-2 inline-flex rounded bg-accent/10 px-2 py-1 text-[11px] uppercase text-accent">{item.kind}</div>
                    <div className="line-clamp-2 text-sm font-semibold text-ink">{item.title}</div>
                    {item.summary && <p className="mt-2 line-clamp-3 text-xs leading-5 text-muted">{item.summary}</p>}
                    {item.path && <div className="mt-2 truncate text-[11px] text-accent">{item.path}</div>}
                </article>
            ))}
        </div>
    </div>
);

const ActivityView = ({ workspaceStatus, workspaceEvents }) => (
    <div className="relative z-10 h-[calc(100%-4rem)] overflow-y-auto p-6">
        {workspaceStatus?.message && (
            <div className="mb-4 rounded-ada border border-line bg-accent/10 px-3 py-2 text-xs text-accent">
                {workspaceStatus.message}
            </div>
        )}
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {workspaceEvents.slice().reverse().map((event, index) => (
                <div key={`${event.type}-${index}`} className="rounded-ada border border-line bg-surface px-4 py-3 text-xs">
                    <div className="font-semibold text-ink">{event.type || 'event'}</div>
                    <div className="mt-1 line-clamp-3 text-muted">{event.query || event.mission || event.message || JSON.stringify(event)}</div>
                </div>
            ))}
        </div>
    </div>
);

const SourceRow = ({ item }) => (
    <div className="mb-2 rounded-ada border border-line bg-surface px-3 py-2 text-xs">
        <div className="line-clamp-2 font-semibold text-ink">{item.title}</div>
        {item.summary && <div className="mt-1 line-clamp-2 text-muted">{item.summary}</div>}
    </div>
);

export default WorkspaceShell;

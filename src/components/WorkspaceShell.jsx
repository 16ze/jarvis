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
        <section className="fixed inset-6 z-[420] overflow-hidden rounded-lg border border-white/75 bg-white/72 text-[#10294d] shadow-[0_30px_110px_rgba(15,43,82,0.20)] backdrop-blur-xl">
            <div className="absolute inset-0 pointer-events-none bg-[radial-gradient(circle_at_50%_8%,rgba(72,141,255,0.18),transparent_28%),linear-gradient(180deg,rgba(255,255,255,0.74),rgba(237,246,255,0.58))]" />

            <header className="relative z-10 flex h-16 items-center justify-between border-b border-white/80 px-6">
                <div className="min-w-0">
                    <div className="text-xs uppercase tracking-[0.08em] text-blue-500">ADA OS Workspace</div>
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
                            <span className="text-[26px] font-semibold leading-none text-[#10294d]">{action.label}</span>
                            <span className="text-xs uppercase tracking-[0.08em] text-blue-500">{action.meta}</span>
                        </button>
                    ))}
                </div>
            </main>

            <aside className="flex min-h-0 flex-col justify-center">
                <div className="ada-glass-panel rounded-lg p-4">
                    <div className="mb-3 text-xs uppercase tracking-[0.08em] text-blue-500">Workspace actif</div>
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
                        className="mt-3 flex h-10 w-full items-center justify-center gap-2 rounded-md bg-blue-600 px-3 text-sm font-medium text-white transition hover:bg-blue-700"
                    >
                        <Plus size={16} />
                        Créer / ouvrir
                    </button>
                    {workspaceStatus?.message && (
                        <div className="mt-3 rounded-md border border-blue-100 bg-blue-50 px-3 py-2 text-xs text-blue-800">
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
            <div className="min-h-0 flex-1 overflow-hidden bg-white/72 backdrop-blur-md">
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
    <div className="flex items-end gap-1 border-b border-white/70 bg-white/40 px-3 pt-2">
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
                                ? 'border-white/80 bg-white/85 text-[#10294d] shadow-[0_-4px_14px_rgba(15,43,82,0.08)]'
                                : 'border-transparent bg-white/30 text-slate-600 hover:bg-white/55'
                        }`}
                    >
                        <Icon size={13} className={isActive ? 'text-blue-600' : 'text-slate-500'} />
                        <span className="min-w-0 flex-1 truncate text-left font-medium">{tab.title}</span>
                        <span
                            role="button"
                            tabIndex={-1}
                            onClick={(event) => {
                                event.stopPropagation();
                                onClose(tab.id);
                            }}
                            className="grid h-5 w-5 place-items-center rounded text-slate-400 opacity-0 transition group-hover:opacity-100 hover:bg-slate-200 hover:text-slate-700"
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
            className="mb-0 grid h-9 w-9 place-items-center rounded-t-md text-slate-500 transition hover:bg-white/55 hover:text-[#10294d]"
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
            <div className="border-b border-white/60 bg-white/40 p-5">
                <div className="mx-auto flex w-full max-w-[760px] items-center gap-3 rounded-full border border-blue-100 bg-white px-4 py-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.92),0_14px_36px_rgba(37,99,235,0.10)]">
                    <Search size={19} className="shrink-0 text-blue-600" />
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
                        className="h-8 rounded-full border border-blue-100 bg-blue-50 px-3 text-xs text-blue-700 outline-none"
                    >
                        {depthOptions.map((option) => (
                            <option key={option} value={option}>{option}</option>
                        ))}
                    </select>
                    <button
                        type="button"
                        onClick={onLaunch}
                        disabled={tab.loading}
                        className="h-8 rounded-full bg-[#10294d] px-4 text-xs font-medium text-white transition hover:bg-blue-900 disabled:opacity-60"
                    >
                        {tab.loading ? 'Recherche…' : 'Rechercher'}
                    </button>
                </div>
                {(workspaceStatus?.message || hasResults) && (
                    <div className="mx-auto mt-3 flex w-full max-w-[760px] items-center justify-between text-[11px] text-slate-500">
                        <div className="text-blue-600">{workspaceStatus?.message || ''}</div>
                        {hasResults && (
                            <div>
                                {tab.results.length} résultats pour <span className="font-medium text-[#10294d]">« {tab.lastQuery} »</span>
                                {tab.synthesized && (
                                    <span className="ml-2 rounded-full bg-amber-50 px-2 py-0.5 text-amber-700">synthèse IA</span>
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
                        <div className="grid h-full place-items-center pt-12 text-center text-sm text-slate-500">
                            <div>
                                <div className="mx-auto mb-4 grid h-16 w-16 place-items-center rounded-full border border-blue-100 bg-blue-50 text-blue-600">
                                    <Search size={28} />
                                </div>
                                <div className="text-base font-semibold text-[#10294d]">AdaSearch</div>
                                <div className="mt-1 text-xs text-slate-500">propulsé par Brave Search</div>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

const PageTabContent = ({ tab, onTitleChange, onUrlChange, onSaveAsNote }) => {
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
            <div className="flex items-center gap-2 border-b border-white/60 bg-white/55 px-3 py-2">
                <button
                    type="button"
                    onClick={goBack}
                    className="grid h-8 w-8 place-items-center rounded-md text-slate-500 transition hover:bg-slate-100 disabled:text-slate-300 disabled:hover:bg-transparent"
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
                    className="grid h-8 w-8 place-items-center rounded-md text-slate-500 transition hover:bg-slate-100 disabled:text-slate-300 disabled:hover:bg-transparent"
                    title="Recharger"
                    aria-label="Recharger"
                >
                    <RotateCw size={15} className={loading && canEmbed ? 'animate-spin' : ''} />
                </button>
                <div className="flex h-8 min-w-0 flex-1 items-center gap-2 truncate rounded-full border border-slate-200 bg-white px-3 text-xs text-slate-600">
                    <Globe size={13} className="shrink-0 text-slate-400" />
                    <span className="truncate">{currentUrl}</span>
                </div>
                <button
                    type="button"
                    onClick={openExternal}
                    className="grid h-8 w-8 place-items-center rounded-md text-slate-500 transition hover:bg-slate-100"
                    title="Ouvrir dans le navigateur système"
                    aria-label="Ouvrir dans le navigateur système"
                >
                    <ExternalLink size={14} />
                </button>
                <button
                    type="button"
                    onClick={onSaveAsNote}
                    className="flex h-8 items-center gap-1.5 rounded-md border border-blue-200 bg-white px-3 text-xs font-medium text-blue-700 transition hover:bg-blue-50"
                    title="Sauvegarder cette page comme note"
                >
                    <BookmarkPlus size={14} />
                    Note
                </button>
            </div>
            <div className="relative min-h-0 flex-1 bg-white">
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
                            <div className="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-full border border-blue-100 bg-blue-50 text-blue-600">
                                <Globe size={24} />
                            </div>
                            <div className="text-base font-semibold text-[#10294d]">
                                {failed ? 'Page non affichable ici' : 'Navigation externe'}
                            </div>
                            <p className="mt-2 text-sm leading-6 text-slate-600">
                                {failed
                                    ? `${failed}. Certains sites refusent l’affichage intégré — ouvre-la dans ton navigateur.`
                                    : 'Le navigateur intégré n’est disponible que dans l’application Ada.'}
                            </p>
                            <div className="mt-5 flex items-center justify-center gap-2">
                                {failed && (
                                    <button
                                        type="button"
                                        onClick={reload}
                                        className="rounded-md border border-slate-200 px-4 py-2 text-xs font-medium text-slate-600 transition hover:bg-slate-50"
                                    >
                                        Réessayer
                                    </button>
                                )}
                                <button
                                    type="button"
                                    onClick={openExternal}
                                    className="rounded-md bg-[#10294d] px-4 py-2 text-xs font-medium text-white transition hover:bg-blue-900"
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
            className="group cursor-pointer rounded-md px-4 py-3 transition hover:bg-blue-50/50"
        >
            <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                    <div className="truncate text-[11px] text-slate-500">{domain}</div>
                    <h3 className="mt-0.5 truncate text-base font-medium text-blue-700 group-hover:underline">
                        {result.title}
                    </h3>
                    <p className="mt-1 line-clamp-2 text-sm leading-5 text-slate-600">
                        {result.snippet || 'Aucun extrait disponible.'}
                    </p>
                </div>
                <button
                    type="button"
                    onClick={(event) => {
                        event.stopPropagation();
                        onSaveAsNote();
                    }}
                    className="grid h-8 w-8 shrink-0 place-items-center rounded-md text-slate-400 opacity-0 transition group-hover:opacity-100 hover:bg-white hover:text-blue-700"
                    title="Sauvegarder en note"
                    aria-label="Sauvegarder en note"
                >
                    <BookmarkPlus size={15} />
                </button>
            </div>
            {result.savedItemId && (
                <div className="mt-2 inline-flex items-center gap-1 rounded-full bg-blue-50 px-2 py-0.5 text-[10px] uppercase tracking-wider text-blue-700">
                    sauvegardé
                </div>
            )}
        </article>
    );
};

const NotesView = ({ noteTitle, noteContent, setNoteTitle, setNoteContent, saveNote, notes }) => (
    <div className="relative z-10 grid h-[calc(100%-4rem)] grid-cols-[minmax(0,1fr)_360px] gap-5 p-5">
        <main className="ada-glass-panel rounded-lg p-5">
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
            <button type="button" onClick={saveNote} className="mt-3 h-10 rounded-md bg-blue-600 px-4 text-sm font-medium text-white">
                Sauvegarder
            </button>
        </main>
        <aside className="min-h-0 overflow-y-auto rounded-lg border border-white/80 bg-white/70 p-4">
            {notes.map((note) => <SourceRow key={note.id} item={note} />)}
        </aside>
    </div>
);

const FilesView = ({ items }) => (
    <div className="relative z-10 h-[calc(100%-4rem)] overflow-y-auto p-6">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {items.map((item) => (
                <article key={item.id} className="rounded-lg border border-white/80 bg-white/72 p-4 shadow-[0_16px_36px_rgba(37,99,235,0.10)]">
                    <div className="mb-2 inline-flex rounded bg-blue-50 px-2 py-1 text-[11px] uppercase text-blue-700">{item.kind}</div>
                    <div className="line-clamp-2 text-sm font-semibold">{item.title}</div>
                    {item.summary && <p className="mt-2 line-clamp-3 text-xs leading-5 text-slate-600">{item.summary}</p>}
                    {item.path && <div className="mt-2 truncate text-[11px] text-blue-500">{item.path}</div>}
                </article>
            ))}
        </div>
    </div>
);

const ActivityView = ({ workspaceStatus, workspaceEvents }) => (
    <div className="relative z-10 h-[calc(100%-4rem)] overflow-y-auto p-6">
        {workspaceStatus?.message && (
            <div className="mb-4 rounded-md border border-blue-100 bg-blue-50 px-3 py-2 text-xs text-blue-800">
                {workspaceStatus.message}
            </div>
        )}
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {workspaceEvents.slice().reverse().map((event, index) => (
                <div key={`${event.type}-${index}`} className="rounded-lg border border-white/80 bg-white/72 px-4 py-3 text-xs">
                    <div className="font-semibold">{event.type || 'event'}</div>
                    <div className="mt-1 line-clamp-3 text-slate-500">{event.query || event.mission || event.message || JSON.stringify(event)}</div>
                </div>
            ))}
        </div>
    </div>
);

const SourceRow = ({ item }) => (
    <div className="mb-2 rounded-md border border-blue-100 bg-white/72 px-3 py-2 text-xs">
        <div className="line-clamp-2 font-semibold text-[#10294d]">{item.title}</div>
        {item.summary && <div className="mt-1 line-clamp-2 text-slate-500">{item.summary}</div>}
    </div>
);

export default WorkspaceShell;

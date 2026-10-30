import React, { useMemo, useRef, useState } from 'react';
import { Cloud, CloudOff, Loader2, MessageSquare, Plus, Search, Trash2, X } from 'lucide-react';
import { filterConversations, getConversationMatchSnippet } from '../lib/conversationHistory';
import useDialogFocus from '../hooks/useDialogFocus';

export default function MobileConversationDrawer({
    open,
    conversations = [],
    activeId,
    disabled = false,
    syncStatus = 'local',
    onClose,
    onNew,
    onSelect,
    onDelete,
}) {
    const [query, setQuery] = useState('');
    const panelRef = useRef(null);
    const searchRef = useRef(null);
    const filtered = useMemo(
        () => filterConversations(conversations, query),
        [conversations, query]
    );
    useDialogFocus(open, panelRef, searchRef, onClose);

    if (!open) return null;

    const createConversation = () => {
        if (disabled) return;
        setQuery('');
        onNew?.();
        onClose?.();
    };

    const selectConversation = (id) => {
        if (disabled) return;
        onSelect?.(id);
        onClose?.();
    };

    const requestDelete = (id) => {
        if (disabled) return;
        onDelete?.(id);
        onClose?.();
    };

    return (
        <div className="fixed inset-0 z-[100] flex" role="dialog" aria-modal="true" aria-label="Historique des conversations">
            <button
                type="button"
                onClick={onClose}
                aria-label="Fermer l’historique"
                className="absolute inset-0 bg-black/25 backdrop-blur-[2px]"
            />
            <aside ref={panelRef} tabIndex={-1} className="relative flex h-full w-[88%] max-w-[360px] flex-col border-r border-line bg-bg p-4 shadow-ada-lg">
                <div className="flex items-center justify-between gap-3">
                    <h2 className="text-base font-semibold text-ink">Conversations</h2>
                    <button
                        type="button"
                        onClick={onClose}
                        aria-label="Fermer l’historique"
                        className="grid h-11 w-11 place-items-center rounded-ada text-muted hover:bg-ink/[0.05] hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/30"
                    >
                        <X size={18} />
                    </button>
                </div>

                <button
                    type="button"
                    onClick={createConversation}
                    disabled={disabled}
                    className="mt-4 flex h-11 items-center justify-center gap-2 rounded-ada border border-line bg-surface text-sm font-medium text-ink enabled:hover:bg-ink/[0.04] disabled:cursor-not-allowed disabled:opacity-40"
                >
                    <Plus size={16} />
                    Nouvelle conversation
                </button>

                <div className="mt-3 flex h-11 items-center gap-2 rounded-ada border border-line bg-surface pl-3 text-muted focus-within:border-accent/60 focus-within:text-ink">
                    <Search size={15} aria-hidden="true" />
                    <input
                        ref={searchRef}
                        value={query}
                        onChange={(event) => setQuery(event.target.value)}
                        onKeyDown={(event) => {
                            if (event.key === 'Escape') setQuery('');
                        }}
                        aria-label="Rechercher dans les conversations"
                        placeholder="Rechercher"
                        className="min-w-0 flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-muted"
                    />
                    {query && (
                        <button
                            type="button"
                            onClick={() => setQuery('')}
                            aria-label="Effacer la recherche"
                            className="grid h-11 w-11 shrink-0 place-items-center rounded-ada text-muted hover:text-ink"
                        >
                            <X size={14} />
                        </button>
                    )}
                </div>

                <div className="mt-3 min-h-0 flex-1 overflow-y-auto">
                    {conversations.length === 0 && (
                        <p className="px-3 py-8 text-center text-sm text-muted">Aucune conversation.</p>
                    )}
                    {conversations.length > 0 && filtered.length === 0 && (
                        <p className="px-3 py-8 text-center text-sm text-muted">Aucune conversation trouvée.</p>
                    )}
                    {filtered.map((conversation) => {
                        const active = conversation.id === activeId;
                        const snippet = getConversationMatchSnippet(conversation, query);
                        return (
                            <div
                                key={conversation.id}
                                className={`group mb-1 flex items-start gap-2 rounded-ada px-2 py-2.5 ${active ? 'bg-accent/10' : 'hover:bg-ink/[0.04]'}`}
                            >
                                <MessageSquare size={16} className={`mt-0.5 shrink-0 ${active ? 'text-accent' : 'text-muted'}`} />
                                <button
                                    type="button"
                                    onClick={() => selectConversation(conversation.id)}
                                    disabled={disabled}
                                    aria-current={active ? 'page' : undefined}
                                    className="min-w-0 flex-1 text-left disabled:cursor-not-allowed"
                                >
                                    <span className="block truncate text-sm text-ink">{conversation.title || 'Nouvelle conversation'}</span>
                                    {snippet && <span className="mt-0.5 block truncate text-xs text-muted">{snippet}</span>}
                                </button>
                                <button
                                    type="button"
                                    onClick={() => requestDelete(conversation.id)}
                                    disabled={disabled}
                                    aria-label={`Supprimer ${conversation.title || 'la conversation'}`}
                                    className="grid h-11 w-11 shrink-0 place-items-center rounded-ada text-muted enabled:hover:text-danger disabled:cursor-not-allowed disabled:opacity-35"
                                >
                                    <Trash2 size={15} />
                                </button>
                            </div>
                        );
                    })}
                </div>

                <div className="flex items-center gap-1.5 border-t border-line pt-3 text-xs text-muted">
                    {syncStatus === 'syncing' ? (
                        <Loader2 size={13} className="animate-spin" aria-hidden="true" />
                    ) : syncStatus === 'synced' ? (
                        <Cloud size={13} aria-hidden="true" />
                    ) : (
                        <CloudOff size={13} aria-hidden="true" />
                    )}
                    <span>
                        {syncStatus === 'syncing'
                            ? 'Synchronisation…'
                            : syncStatus === 'synced'
                            ? 'Synchronisé sur vos appareils'
                            : 'Sauvegarde locale'}
                    </span>
                </div>
            </aside>
        </div>
    );
}

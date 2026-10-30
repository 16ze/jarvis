import React, { useMemo, useState } from 'react';
import { Plus, MessageSquare, Trash2, Check, X, PanelLeftClose, PanelLeftOpen, Pencil, Search } from 'lucide-react';
import { filterConversations, getConversationMatchSnippet } from '../lib/conversationHistory';

/*
 * ConversationSidebar — rail d'historique des conversations, « propre comme Apple ».
 * 100 % tokenisé (bg/surface/surface2/ink/muted/line/accent), beau en clair/sombre.
 *
 * Props :
 *   conversations : [{ id, title, messages, updatedAt }]  (triées par le parent)
 *   activeId      : id de la conversation active
 *   collapsed     : bool
 *   onToggle()    : plier/déplier
 *   onNew()       : nouvelle conversation
 *   onSelect(id)  : sélectionner
 *   onDelete(id)  : supprimer
 *   onRename(id, title) : renommer
 *   disabled      : verrouille les mutations pendant une génération
 */
export default function ConversationSidebar({
    conversations = [],
    activeId,
    collapsed = false,
    onToggle,
    onNew,
    onSelect,
    onDelete,
    onRename,
    disabled = false,
}) {
    const [editingId, setEditingId] = useState(null);
    const [draft, setDraft] = useState('');
    const [searchQuery, setSearchQuery] = useState('');

    const filteredConversations = useMemo(
        () => filterConversations(conversations, searchQuery),
        [conversations, searchQuery]
    );

    const startRename = (c) => {
        if (disabled) return;
        setEditingId(c.id);
        setDraft(c.title || '');
    };
    const cancelRename = () => {
        setEditingId(null);
        setDraft('');
    };
    const commitRename = () => {
        if (editingId) onRename?.(editingId, draft);
        cancelRename();
    };

    // ── Rail replié : juste les icônes (nouveau + déplier) ───────────────────
    if (collapsed) {
        return (
            <div className="flex w-[52px] shrink-0 flex-col items-center gap-2 border-r border-line bg-surface/60 py-3">
                <button
                    onClick={onToggle}
                    title="Afficher l’historique"
                    className="grid h-9 w-9 place-items-center rounded-ada text-muted transition-colors hover:bg-ink/[0.06] hover:text-ink"
                >
                    <PanelLeftOpen size={18} />
                </button>
                <button
                    onClick={() => { setSearchQuery(''); onNew?.(); }}
                    disabled={disabled}
                    title="Nouvelle conversation"
                    className="grid h-9 w-9 place-items-center rounded-ada border border-line text-accent transition-colors enabled:hover:bg-accent/10 disabled:cursor-not-allowed disabled:opacity-35"
                >
                    <Plus size={18} />
                </button>
            </div>
        );
    }

    return (
        <div className="flex w-[260px] shrink-0 flex-col border-r border-line bg-surface/60">
            {/* En-tête : nouvelle conversation + replier */}
            <div className="flex items-center gap-2 p-3">
                <button
                    onClick={() => { setSearchQuery(''); onNew?.(); }}
                    disabled={disabled}
                    className="ada-btn flex h-9 flex-1 items-center justify-center gap-2 rounded-ada border border-line bg-surface text-sm font-medium text-ink transition-colors enabled:hover:bg-ink/[0.04] disabled:cursor-not-allowed disabled:opacity-40"
                >
                    <Plus size={16} />
                    Nouvelle conversation
                </button>
                <button
                    onClick={onToggle}
                    title="Masquer l’historique"
                    className="grid h-9 w-9 shrink-0 place-items-center rounded-ada text-muted transition-colors hover:bg-ink/[0.06] hover:text-ink"
                >
                    <PanelLeftClose size={18} />
                </button>
            </div>

            <div className="px-3 pb-3">
                <div className="flex h-9 items-center gap-2 rounded-ada border border-line bg-surface px-2.5 text-muted transition-colors focus-within:border-accent/60 focus-within:text-ink">
                    <Search size={15} aria-hidden="true" />
                    <input
                        value={searchQuery}
                        onChange={(event) => setSearchQuery(event.target.value)}
                        onKeyDown={(event) => {
                            if (event.key === 'Escape') setSearchQuery('');
                        }}
                        aria-label="Rechercher dans les conversations"
                        placeholder="Rechercher"
                        className="min-w-0 flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-muted"
                    />
                    {searchQuery && (
                        <button
                            type="button"
                            onClick={() => setSearchQuery('')}
                            aria-label="Effacer la recherche"
                            className="rounded p-0.5 text-muted transition-colors hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/30"
                        >
                            <X size={14} />
                        </button>
                    )}
                </div>
            </div>

            {/* Liste */}
            <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
                {conversations.length === 0 && (
                    <p className="px-3 py-6 text-center text-xs text-muted">Aucune conversation.</p>
                )}
                {conversations.length > 0 && filteredConversations.length === 0 && (
                    <div className="px-3 py-6 text-center">
                        <p className="text-xs text-muted">Aucune conversation trouvée.</p>
                        <button
                            type="button"
                            onClick={() => setSearchQuery('')}
                            className="mt-2 text-xs font-medium text-accent hover:underline focus:outline-none focus-visible:underline"
                        >
                            Effacer la recherche
                        </button>
                    </div>
                )}
                {filteredConversations.map((c) => {
                    const active = c.id === activeId;
                    const editing = editingId === c.id;
                    const matchSnippet = getConversationMatchSnippet(c, searchQuery);
                    return (
                        <div
                            key={c.id}
                            className={`group mb-0.5 flex items-center gap-2 rounded-ada px-2.5 py-2 text-sm transition-colors ${
                                active ? 'bg-accent/10 text-ink' : 'text-muted hover:bg-ink/[0.04] hover:text-ink'
                            }`}
                        >
                            <MessageSquare size={15} className={`shrink-0 ${matchSnippet ? 'mt-0.5 self-start' : ''} ${active ? 'text-accent' : 'text-muted'}`} />
                            {editing ? (
                                <input
                                    autoFocus
                                    value={draft}
                                    onChange={(e) => setDraft(e.target.value)}
                                    onKeyDown={(e) => {
                                        if (e.key === 'Enter') commitRename();
                                        if (e.key === 'Escape') cancelRename();
                                    }}
                                    onBlur={cancelRename}
                                    className="min-w-0 flex-1 rounded-sm border border-line bg-surface px-1.5 py-0.5 text-sm text-ink outline-none focus:border-accent"
                                />
                            ) : (
                                <button
                                    onClick={() => onSelect?.(c.id)}
                                    onDoubleClick={() => startRename(c)}
                                    disabled={disabled}
                                    aria-current={active ? 'page' : undefined}
                                    className="min-w-0 flex-1 text-left disabled:cursor-not-allowed"
                                    title={c.title}
                                >
                                    <span className="block truncate">{c.title || 'Nouvelle conversation'}</span>
                                    {matchSnippet && (
                                        <span className="mt-0.5 block truncate text-[11px] text-muted">{matchSnippet}</span>
                                    )}
                                </button>
                            )}

                            {editing ? (
                                <button
                                    onMouseDown={(event) => event.preventDefault()}
                                    onClick={commitRename}
                                    title="Valider"
                                    aria-label="Valider le nouveau nom"
                                    className="shrink-0 text-muted hover:text-positive"
                                >
                                    <Check size={15} />
                                </button>
                            ) : (
                                <div className="flex shrink-0 items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
                                    <button
                                        onClick={() => startRename(c)}
                                        disabled={disabled}
                                        title="Renommer"
                                        aria-label={`Renommer ${c.title || 'la conversation'}`}
                                        className="text-muted enabled:hover:text-ink disabled:cursor-not-allowed disabled:opacity-35"
                                    >
                                        <Pencil size={14} />
                                    </button>
                                    <button
                                        onClick={() => onDelete?.(c.id)}
                                        disabled={disabled}
                                        title="Supprimer"
                                        aria-label={`Supprimer ${c.title || 'la conversation'}`}
                                        className="text-muted enabled:hover:text-danger disabled:cursor-not-allowed disabled:opacity-35"
                                    >
                                        <Trash2 size={14} />
                                    </button>
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

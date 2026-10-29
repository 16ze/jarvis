import React, { useState } from 'react';
import { Plus, MessageSquare, Trash2, Check, X, PanelLeftClose, PanelLeftOpen, Pencil } from 'lucide-react';

/*
 * ConversationSidebar — rail d'historique des conversations, « propre comme Apple ».
 * 100 % tokenisé (bg/surface/surface2/ink/muted/line/accent), beau en clair/sombre.
 *
 * Props :
 *   conversations : [{ id, title, updatedAt }]  (triées par le parent, plus récent d'abord)
 *   activeId      : id de la conversation active
 *   collapsed     : bool
 *   onToggle()    : plier/déplier
 *   onNew()       : nouvelle conversation
 *   onSelect(id)  : sélectionner
 *   onDelete(id)  : supprimer
 *   onRename(id, title) : renommer
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
}) {
    const [editingId, setEditingId] = useState(null);
    const [draft, setDraft] = useState('');

    const startRename = (c) => { setEditingId(c.id); setDraft(c.title || ''); };
    const commitRename = () => {
        if (editingId) onRename?.(editingId, draft);
        setEditingId(null);
        setDraft('');
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
                    onClick={onNew}
                    title="Nouvelle conversation"
                    className="grid h-9 w-9 place-items-center rounded-ada border border-line text-accent transition-colors hover:bg-accent/10"
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
                    onClick={onNew}
                    className="ada-btn flex h-9 flex-1 items-center justify-center gap-2 rounded-ada border border-line bg-surface text-sm font-medium text-ink transition-colors hover:bg-ink/[0.04]"
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

            {/* Liste */}
            <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
                {conversations.length === 0 && (
                    <p className="px-3 py-6 text-center text-xs text-muted">Aucune conversation.</p>
                )}
                {conversations.map((c) => {
                    const active = c.id === activeId;
                    const editing = editingId === c.id;
                    return (
                        <div
                            key={c.id}
                            className={`group mb-0.5 flex items-center gap-2 rounded-ada px-2.5 py-2 text-sm transition-colors ${
                                active ? 'bg-accent/10 text-ink' : 'text-muted hover:bg-ink/[0.04] hover:text-ink'
                            }`}
                        >
                            <MessageSquare size={15} className={active ? 'text-accent' : 'text-muted'} />
                            {editing ? (
                                <input
                                    autoFocus
                                    value={draft}
                                    onChange={(e) => setDraft(e.target.value)}
                                    onKeyDown={(e) => {
                                        if (e.key === 'Enter') commitRename();
                                        if (e.key === 'Escape') { setEditingId(null); setDraft(''); }
                                    }}
                                    onBlur={commitRename}
                                    className="min-w-0 flex-1 rounded-sm border border-line bg-surface px-1.5 py-0.5 text-sm text-ink outline-none focus:border-accent"
                                />
                            ) : (
                                <button
                                    onClick={() => onSelect?.(c.id)}
                                    onDoubleClick={() => startRename(c)}
                                    className="min-w-0 flex-1 truncate text-left"
                                    title={c.title}
                                >
                                    {c.title || 'Nouvelle conversation'}
                                </button>
                            )}

                            {editing ? (
                                <button onClick={commitRename} title="Valider" className="shrink-0 text-muted hover:text-positive">
                                    <Check size={15} />
                                </button>
                            ) : (
                                <div className="flex shrink-0 items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                                    <button onClick={() => startRename(c)} title="Renommer" className="text-muted hover:text-ink">
                                        <Pencil size={14} />
                                    </button>
                                    <button onClick={() => onDelete?.(c.id)} title="Supprimer" className="text-muted hover:text-danger">
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

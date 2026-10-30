import React, { useEffect, useRef, useState } from 'react';
import { Check, Copy, Pencil, X } from 'lucide-react';

export default function EditableUserMessage({
    text,
    edited = false,
    disabled = false,
    alwaysShowActions = false,
    onCopy,
    onSave,
}) {
    const [isEditing, setIsEditing] = useState(false);
    const [draft, setDraft] = useState(text || '');
    const [copied, setCopied] = useState(false);
    const textareaRef = useRef(null);
    const copiedTimerRef = useRef(null);

    useEffect(() => {
        if (!isEditing) setDraft(text || '');
    }, [text, isEditing]);

    useEffect(() => () => {
        if (copiedTimerRef.current) clearTimeout(copiedTimerRef.current);
    }, []);

    const cancelEdit = () => {
        setDraft(text || '');
        setIsEditing(false);
    };

    const saveEdit = () => {
        const cleanText = draft.trim();
        if (!cleanText) return;
        if (cleanText === String(text || '').trim()) {
            setIsEditing(false);
            return;
        }
        const saved = onSave?.(cleanText);
        if (saved !== false) setIsEditing(false);
    };

    const copyMessage = async () => {
        await onCopy?.();
        setCopied(true);
        if (copiedTimerRef.current) clearTimeout(copiedTimerRef.current);
        copiedTimerRef.current = setTimeout(() => setCopied(false), 1500);
    };

    if (isEditing) {
        return (
            <div className="ada-msg-in flex justify-end">
                <div className="w-full max-w-[80%] rounded-ada-lg border border-accent/40 bg-surface p-3 shadow-ada-sm">
                    <textarea
                        ref={textareaRef}
                        autoFocus
                        value={draft}
                        onChange={(event) => setDraft(event.target.value)}
                        onKeyDown={(event) => {
                            if (event.key === 'Escape') cancelEdit();
                            if (event.key === 'Enter' && !event.shiftKey) {
                                event.preventDefault();
                                saveEdit();
                            }
                        }}
                        aria-label="Modifier le message"
                        rows={Math.min(6, Math.max(2, draft.split('\n').length))}
                        className="w-full resize-none bg-transparent text-sm leading-relaxed text-ink outline-none placeholder:text-muted"
                    />
                    <div className="mt-3 flex justify-end gap-2">
                        <button
                            type="button"
                            onClick={cancelEdit}
                            className="inline-flex h-8 items-center gap-1.5 rounded-ada px-3 text-xs font-medium text-muted transition-colors hover:bg-ink/[0.05] hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/30"
                        >
                            <X size={14} />
                            Annuler
                        </button>
                        <button
                            type="button"
                            onClick={saveEdit}
                            disabled={!draft.trim()}
                            aria-label="Enregistrer et renvoyer le message"
                            className="inline-flex h-8 items-center gap-1.5 rounded-ada bg-accent px-3 text-xs font-medium text-white transition enabled:hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/30"
                        >
                            <Check size={14} />
                            Envoyer
                        </button>
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className="ada-msg-in group flex flex-col items-end gap-1">
            <div className="max-w-[80%] whitespace-pre-wrap break-words rounded-ada-lg bg-accent px-4 py-2.5 text-sm leading-relaxed text-white shadow-ada-sm">
                {text}
            </div>
            <div className={`flex items-center gap-1 transition-opacity ${alwaysShowActions ? 'opacity-100' : 'opacity-0 group-hover:opacity-100 focus-within:opacity-100'}`}>
                {edited && <span className="mr-1 text-[10px] text-muted">Modifié</span>}
                <button
                    type="button"
                    onClick={copyMessage}
                    aria-label={copied ? 'Copié' : 'Copier le message'}
                    title={copied ? 'Copié' : 'Copier'}
                    className={`inline-flex items-center justify-center rounded-ada text-muted transition-colors hover:text-ink focus:outline-none focus-visible:text-ink ${alwaysShowActions ? 'h-11 w-11' : 'p-1.5'}`}
                >
                    {copied ? <Check size={14} /> : <Copy size={14} />}
                </button>
                <button
                    type="button"
                    onClick={() => setIsEditing(true)}
                    disabled={disabled}
                    aria-label="Modifier le message"
                    title={disabled ? 'Attendre la fin de la réponse' : 'Modifier'}
                    className={`inline-flex items-center justify-center rounded-ada text-muted transition-colors enabled:hover:text-ink disabled:cursor-not-allowed disabled:opacity-35 focus:outline-none focus-visible:text-ink ${alwaysShowActions ? 'h-11 w-11' : 'p-1.5'}`}
                >
                    <Pencil size={14} />
                </button>
            </div>
        </div>
    );
}

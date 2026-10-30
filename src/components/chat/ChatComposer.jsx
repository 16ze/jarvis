import React, { useCallback, useEffect, useLayoutEffect, useRef } from 'react';
import { ArrowUp, Square, Paperclip, X } from 'lucide-react';

const MAX_LINES = 6;

/**
 * Zone de saisie du chat — textarea auto-grow, pièce jointe image, envoi/arrêt,
 * style Apple-clean.
 *
 * @param {string}   value                       Contenu courant du textarea.
 * @param {(next:string) => void} onChange        Reçoit la NOUVELLE valeur (string), pas l'event.
 * @param {() => void} onSend                      Appelé sans argument pour envoyer.
 * @param {() => void} onStop                      Appelé sans argument pour stopper la génération.
 * @param {boolean}  isGenerating                 true → bouton Stop ; false → bouton Envoyer.
 * @param {boolean}  disabled                     Désactive la saisie et l'envoi.
 * @param {string}   placeholder                  Texte indicatif.
 * @param {{name?:string, previewUrl?:string}|null} attachment  Pièce jointe courante (ou null).
 * @param {(file:File) => void} onPickImage        Appelé avec le fichier image choisi.
 * @param {() => void} onClearAttachment           Retire la pièce jointe courante.
 */
export default function ChatComposer({
    value,
    onChange,
    onSend,
    onStop,
    isGenerating = false,
    disabled = false,
    placeholder = 'Écrire à Ada…',
    attachment = null,
    onPickImage,
    onClearAttachment,
}) {
    const textareaRef = useRef(null);
    const fileInputRef = useRef(null);

    // Auto-grow : ajuste la hauteur au contenu, plafonnée à ~6 lignes puis scroll.
    const resize = useCallback(() => {
        const el = textareaRef.current;
        if (!el) return;
        el.style.height = 'auto';
        const styles = window.getComputedStyle(el);
        const lineHeight = parseFloat(styles.lineHeight) || 20;
        const paddingY =
            parseFloat(styles.paddingTop) + parseFloat(styles.paddingBottom) || 0;
        const borderY =
            parseFloat(styles.borderTopWidth) + parseFloat(styles.borderBottomWidth) || 0;
        const maxHeight = lineHeight * MAX_LINES + paddingY + borderY;
        const next = Math.min(el.scrollHeight, maxHeight);
        el.style.height = `${next}px`;
        el.style.overflowY = el.scrollHeight > maxHeight ? 'auto' : 'hidden';
    }, []);

    useLayoutEffect(() => {
        resize();
    }, [value, resize]);

    useEffect(() => {
        resize();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const canSend = !disabled && (value.trim().length > 0 || !!attachment);

    const handleKeyDown = useCallback(
        (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                if (isGenerating) return;
                if (canSend) onSend?.();
            }
        },
        [canSend, isGenerating, onSend]
    );

    const handleClickAction = useCallback(() => {
        if (isGenerating) {
            onStop?.();
        } else if (canSend) {
            onSend?.();
        }
    }, [isGenerating, canSend, onSend, onStop]);

    const handleFileChange = useCallback(
        (e) => {
            const file = e.target.files && e.target.files[0];
            if (file && onPickImage) onPickImage(file);
            // Réinitialise pour permettre de re-choisir le même fichier.
            e.target.value = '';
        },
        [onPickImage]
    );

    return (
        <div className="flex flex-col gap-2 rounded-ada-lg border border-line bg-surface px-3 py-2 shadow-ada-sm transition-shadow duration-150 focus-within:shadow-[0_0_0_3px_rgb(var(--c-accent)/0.18)]">
            {/* Aperçu de la pièce jointe */}
            {attachment && (
                <div className="flex items-center gap-2 self-start rounded-ada border border-line bg-surface2 px-2 py-1.5">
                    {attachment.previewUrl && (
                        <img
                            src={attachment.previewUrl}
                            alt={attachment.name || 'pièce jointe'}
                            className="h-10 w-10 rounded-[6px] object-cover"
                        />
                    )}
                    <span className="max-w-[160px] truncate text-xs text-muted">
                        {attachment.name || 'Image'}
                    </span>
                    <button
                        type="button"
                        onClick={() => onClearAttachment?.()}
                        aria-label="Retirer la pièce jointe"
                        title="Retirer"
                        className="grid h-5 w-5 place-items-center rounded-full text-muted transition hover:bg-ink/[0.08] hover:text-danger"
                    >
                        <X size={13} strokeWidth={2.4} />
                    </button>
                </div>
            )}

            <div className="flex items-end gap-2">
                {/* Bouton pièce jointe */}
                <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/png,image/jpeg,image/webp,image/gif"
                    onChange={handleFileChange}
                    className="hidden"
                    aria-hidden="true"
                    tabIndex={-1}
                />
                <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={disabled}
                    aria-label="Joindre une image"
                    title="Joindre une image"
                    className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-muted transition enabled:hover:bg-ink/[0.06] enabled:hover:text-ink disabled:cursor-not-allowed disabled:opacity-40 focus:outline-none focus-visible:shadow-[0_0_0_3px_rgb(var(--c-accent)/0.18)]"
                >
                    <Paperclip size={18} strokeWidth={2.2} />
                </button>

                <textarea
                    ref={textareaRef}
                    value={value}
                    onChange={(e) => onChange?.(e.target.value)}
                    onKeyDown={handleKeyDown}
                    rows={1}
                    disabled={disabled}
                    placeholder={placeholder}
                    aria-label="Message pour Ada"
                    className="min-h-11 flex-1 resize-none border-0 bg-transparent py-[11px] text-[15px] leading-[22px] text-ink placeholder:text-muted focus:outline-none disabled:opacity-60 scrollbar-hide"
                />

                <button
                    type="button"
                    onClick={handleClickAction}
                    disabled={isGenerating ? false : !canSend}
                    aria-label={isGenerating ? 'Arrêter la génération' : 'Envoyer le message'}
                    title={isGenerating ? 'Arrêter' : 'Envoyer'}
                    className={
                        isGenerating
                            ? 'inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-line bg-surface2 text-ink transition hover:text-danger focus:outline-none focus-visible:shadow-[0_0_0_3px_rgb(var(--c-accent)/0.18)]'
                            : 'inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-accent text-white transition enabled:hover:brightness-110 disabled:cursor-not-allowed disabled:bg-muted/40 disabled:text-muted focus:outline-none focus-visible:shadow-[0_0_0_3px_rgb(var(--c-accent)/0.18)]'
                    }
                >
                    {isGenerating ? (
                        <Square size={16} strokeWidth={2.4} fill="currentColor" />
                    ) : (
                        <ArrowUp size={18} strokeWidth={2.4} />
                    )}
                </button>
            </div>
        </div>
    );
}

import React, { useCallback, useEffect, useLayoutEffect, useRef } from 'react';
import { ArrowUp, Square } from 'lucide-react';

const MAX_LINES = 6;

/**
 * Zone de saisie du chat — textarea auto-grow, envoi/arrêt, style Apple-clean.
 *
 * @param {string}   value                       Contenu courant du textarea.
 * @param {(next:string) => void} onChange        Reçoit la NOUVELLE valeur (string), pas l'event.
 * @param {() => void} onSend                      Appelé sans argument pour envoyer.
 * @param {() => void} onStop                      Appelé sans argument pour stopper la génération.
 * @param {boolean}  isGenerating                 true → bouton Stop ; false → bouton Envoyer.
 * @param {boolean}  disabled                     Désactive la saisie et l'envoi.
 * @param {string}   placeholder                  Texte indicatif.
 */
export default function ChatComposer({
    value,
    onChange,
    onSend,
    onStop,
    isGenerating = false,
    disabled = false,
    placeholder = 'Écrire à Ada…',
}) {
    const textareaRef = useRef(null);

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

    const canSend = !disabled && value.trim().length > 0;

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

    return (
        <div
            className="flex items-end gap-2 rounded-ada-lg border border-line bg-surface px-3 py-2 shadow-ada-sm transition-shadow duration-150 focus-within:shadow-[0_0_0_3px_rgb(var(--c-accent)/0.18)]"
        >
            <textarea
                ref={textareaRef}
                value={value}
                onChange={(e) => onChange?.(e.target.value)}
                onKeyDown={handleKeyDown}
                rows={1}
                disabled={disabled}
                placeholder={placeholder}
                aria-label="Message pour Ada"
                className="min-h-[24px] flex-1 resize-none border-0 bg-transparent py-1 text-[15px] leading-relaxed text-ink placeholder:text-muted focus:outline-none disabled:opacity-60 scrollbar-hide"
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
    );
}

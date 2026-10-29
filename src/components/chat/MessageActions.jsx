import React, { useCallback, useState } from 'react';
import { Check, Copy, RotateCcw } from 'lucide-react';

/**
 * Petite barre d'actions discrète sous un message (apparaît au survol).
 *
 * @param {() => (void|Promise<void>)} onCopy        Copie le contenu du message.
 * @param {() => void}                 onRegenerate  Régénère la réponse.
 * @param {boolean}                    canRegenerate Affiche le bouton Régénérer.
 */
export default function MessageActions({ onCopy, onRegenerate, canRegenerate = false }) {
    const [copied, setCopied] = useState(false);

    const handleCopy = useCallback(async () => {
        try {
            await onCopy?.();
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
        } catch {
            /* on ignore silencieusement une erreur de copie */
        }
    }, [onCopy]);

    const btnClass =
        'inline-flex items-center gap-1 rounded-ada px-1.5 py-1 text-xs text-muted transition-colors duration-150 hover:text-ink focus:outline-none focus-visible:text-ink';

    return (
        <div className="flex items-center gap-1 opacity-0 transition-opacity duration-150 group-hover:opacity-100 focus-within:opacity-100">
            <button
                type="button"
                onClick={handleCopy}
                className={btnClass}
                aria-label={copied ? 'Copié' : 'Copier le message'}
                title={copied ? 'Copié' : 'Copier'}
            >
                {copied ? <Check size={14} strokeWidth={2.2} /> : <Copy size={14} strokeWidth={2} />}
            </button>

            {canRegenerate && (
                <button
                    type="button"
                    onClick={onRegenerate}
                    className={btnClass}
                    aria-label="Régénérer la réponse"
                    title="Régénérer"
                >
                    <RotateCcw size={14} strokeWidth={2} />
                </button>
            )}
        </div>
    );
}

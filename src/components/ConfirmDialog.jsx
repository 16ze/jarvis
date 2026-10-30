import React, { useRef } from 'react';
import useDialogFocus from '../hooks/useDialogFocus';

export default function ConfirmDialog({
    open,
    title,
    description,
    confirmLabel = 'Confirmer',
    onCancel,
    onConfirm,
}) {
    const panelRef = useRef(null);
    const cancelRef = useRef(null);
    useDialogFocus(open, panelRef, cancelRef, onCancel);

    if (!open) return null;

    return (
        <div className="fixed inset-0 z-[220] grid place-items-center bg-black/30 p-4 backdrop-blur-[2px]">
            <div
                ref={panelRef}
                role="alertdialog"
                aria-modal="true"
                aria-labelledby="confirm-dialog-title"
                aria-describedby="confirm-dialog-description"
                tabIndex={-1}
                className="w-full max-w-sm rounded-ada-lg border border-line bg-surface p-5 shadow-ada-lg"
            >
                <h2 id="confirm-dialog-title" className="text-base font-semibold text-ink">{title}</h2>
                <p id="confirm-dialog-description" className="mt-2 text-sm leading-relaxed text-muted">{description}</p>
                <div className="mt-5 flex justify-end gap-2">
                    <button
                        ref={cancelRef}
                        type="button"
                        onClick={onCancel}
                        className="min-h-11 rounded-ada px-4 text-sm font-medium text-muted hover:bg-ink/[0.05] hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/30"
                    >
                        Annuler
                    </button>
                    <button
                        type="button"
                        onClick={onConfirm}
                        className="min-h-11 rounded-ada bg-danger px-4 text-sm font-medium text-white hover:brightness-105 focus:outline-none focus-visible:ring-2 focus-visible:ring-danger/30"
                    >
                        {confirmLabel}
                    </button>
                </div>
            </div>
        </div>
    );
}

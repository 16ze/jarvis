import { useEffect, useRef } from 'react';

const FOCUSABLE = [
    'button:not([disabled])',
    'input:not([disabled])',
    'textarea:not([disabled])',
    'select:not([disabled])',
    '[href]',
    '[tabindex]:not([tabindex="-1"])',
].join(',');

export default function useDialogFocus(open, containerRef, initialFocusRef, onClose) {
    const closeRef = useRef(onClose);
    closeRef.current = onClose;

    useEffect(() => {
        if (!open) return undefined;

        const previousFocus = document.activeElement;
        const container = containerRef.current;
        const focusables = () => Array.from(container?.querySelectorAll(FOCUSABLE) || []);
        const firstTarget = initialFocusRef?.current || focusables()[0] || container;
        firstTarget?.focus?.();

        const onKeyDown = (event) => {
            if (event.key === 'Escape') {
                event.preventDefault();
                closeRef.current?.();
                return;
            }
            if (event.key !== 'Tab') return;

            const items = focusables();
            if (!items.length) return;
            const first = items[0];
            const last = items[items.length - 1];
            if (!container?.contains(document.activeElement)) {
                event.preventDefault();
                first.focus();
            } else if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first.focus();
            }
        };

        document.addEventListener('keydown', onKeyDown);
        return () => {
            document.removeEventListener('keydown', onKeyDown);
            previousFocus?.focus?.();
        };
    }, [open, containerRef, initialFocusRef]);
}

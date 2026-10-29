import React, { useEffect, useRef } from 'react';
import { Terminal, X } from 'lucide-react';

const TerminalWindow = ({ entries, onClose }) => {
    const bottomRef = useRef(null);

    useEffect(() => {
        if (bottomRef.current) {
            bottomRef.current.scrollIntoView({ behavior: 'smooth' });
        }
    }, [entries]);

    return (
        <div className="w-full h-full flex flex-col bg-surface2 rounded-ada overflow-hidden border border-line shadow-ada font-mono text-xs">
            {/* Header */}
            <div data-drag-handle className="h-8 bg-surface border-b border-line flex items-center justify-between px-3 shrink-0 cursor-grab active:cursor-grabbing">
                <div className="flex items-center gap-2 text-ink">
                    <Terminal size={13} className="text-positive" />
                    <span>TERMINAL</span>
                </div>
                <button onClick={onClose} className="hover:bg-danger/10 text-muted hover:text-danger p-1 rounded transition-colors">
                    <X size={13} />
                </button>
            </div>

            {/* Output */}
            <div className="flex-1 overflow-y-auto p-3 space-y-3">
                {entries.length === 0 && (
                    <div className="text-muted animate-pulse">Waiting for commands...</div>
                )}
                {entries.map((entry, i) => (
                    <div key={i} className="space-y-1">
                        <div className="flex items-center gap-1 text-positive">
                            <span className="text-muted">$</span>
                            <span>{entry.command}</span>
                        </div>
                        <pre className="text-ink whitespace-pre-wrap break-words pl-3 border-l border-line leading-relaxed">
                            {entry.output}
                        </pre>
                    </div>
                ))}
                <div ref={bottomRef} />
            </div>
        </div>
    );
};

export default TerminalWindow;

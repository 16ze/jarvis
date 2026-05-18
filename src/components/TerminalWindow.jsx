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
        <div className="w-full h-full flex flex-col bg-white/70 rounded-lg overflow-hidden border border-blue-400/40 font-mono text-xs">
            {/* Header (chrome: white-glass) */}
            <div data-drag-handle className="h-8 bg-white/60 border-b border-blue-200 flex items-center justify-between px-3 shrink-0 cursor-grab active:cursor-grabbing">
                <div className="flex items-center gap-2 text-slate-700">
                    <Terminal size={13} className="text-blue-600" />
                    <span>TERMINAL</span>
                </div>
                <button onClick={onClose} className="hover:bg-red-50 text-slate-500 hover:text-red-500 p-1 rounded transition-colors">
                    <X size={13} />
                </button>
            </div>

            {/* Output (console pane stays dark for monospace readability) */}
            <div className="flex-1 overflow-y-auto p-3 space-y-3 bg-slate-900">
                {entries.length === 0 && (
                    <div className="text-slate-500 animate-pulse">Waiting for commands...</div>
                )}
                {entries.map((entry, i) => (
                    <div key={i} className="space-y-1">
                        <div className="flex items-center gap-1 text-green-400">
                            <span className="text-slate-500">$</span>
                            <span>{entry.command}</span>
                        </div>
                        <pre className="text-slate-100 whitespace-pre-wrap break-words pl-3 border-l border-slate-700 leading-relaxed">
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

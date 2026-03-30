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
        <div className="w-full h-full flex flex-col bg-[#0d0d0d] rounded-lg overflow-hidden border border-gray-800 font-mono text-xs">
            {/* Header */}
            <div data-drag-handle className="h-8 bg-[#1a1a1a] border-b border-gray-700 flex items-center justify-between px-3 shrink-0 cursor-grab active:cursor-grabbing">
                <div className="flex items-center gap-2 text-gray-300">
                    <Terminal size={13} className="text-green-400" />
                    <span>TERMINAL</span>
                </div>
                <button onClick={onClose} className="hover:bg-red-500/20 text-gray-400 hover:text-red-400 p-1 rounded transition-colors">
                    <X size={13} />
                </button>
            </div>

            {/* Output */}
            <div className="flex-1 overflow-y-auto p-3 space-y-3">
                {entries.length === 0 && (
                    <div className="text-gray-600 animate-pulse">Waiting for commands...</div>
                )}
                {entries.map((entry, i) => (
                    <div key={i} className="space-y-1">
                        <div className="flex items-center gap-1 text-green-400">
                            <span className="text-gray-500">$</span>
                            <span>{entry.command}</span>
                        </div>
                        <pre className="text-gray-300 whitespace-pre-wrap break-words pl-3 border-l border-gray-700 leading-relaxed">
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

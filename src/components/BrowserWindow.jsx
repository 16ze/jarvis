import React, { useEffect, useRef } from 'react';
import { Globe, X } from 'lucide-react';

const BrowserWindow = ({ imageSrc, logs, onClose, socket }) => {
    const [input, setInput] = React.useState('');
    const logsEndRef = useRef(null);

    // Auto-scroll logs to bottom
    useEffect(() => {
        if (logsEndRef.current) {
            logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
        }
    }, [logs]);

    const handleSend = () => {
        if (!input.trim()) return;
        if (socket) {
            socket.emit('prompt_web_agent', { prompt: input });
            // Optionally add a local log
            // But usually backend sends logs back.
        }
        setInput('');
    };

    return (
        <div className="w-full h-full relative group bg-surface2 rounded-ada overflow-hidden flex flex-col border border-line shadow-ada">
            {/* Header Bar - Drag Handle */}
            <div data-drag-handle className="h-8 bg-surface border-b border-line flex items-center justify-between px-2 shrink-0 cursor-grab active:cursor-grabbing">
                <div className="flex items-center gap-2 text-ink text-xs font-mono">
                    <Globe size={14} className="text-accent" />
                    <span>WEB_AGENT_VIEW</span>
                </div>
                <button onClick={onClose} className="hover:bg-danger/10 text-muted hover:text-danger p-1 rounded transition-colors">
                    <X size={14} />
                </button>
            </div>

            {/* Browser Content */}
            <div className="flex-1 relative bg-surface2 flex items-center justify-center overflow-hidden">
                {imageSrc ? (
                    <img
                        src={`data:image/png;base64,${imageSrc}`}
                        alt="Browser View"
                        className="max-w-full max-h-full object-contain"
                    />
                ) : (
                    <div className="flex flex-col items-center gap-2">
                        <div className="text-muted text-xs font-mono animate-pulse">Waiting for browser stream...</div>
                    </div>
                )}
            </div>

            {/* Input Bar */}
            <div className="h-10 bg-surface border-t border-line flex items-center px-2 gap-2">
                <span className="text-accent font-mono text-xs">{'>'}</span>
                <input
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleSend()}
                    placeholder="Enter command for Web Agent..."
                    className="flex-1 bg-transparent border-none outline-none text-ink text-xs font-mono placeholder-muted"
                />
            </div>

            {/* Logs Overlay (Bottom) */}
            <div className="h-24 bg-surface border-t border-line p-2 font-mono text-[10px] overflow-y-auto text-positive">
                {logs.slice(-100).map((log, i) => (
                    <div key={i} className="mb-1 border-l-2 border-accent/40 pl-1 break-words">
                        <span className="opacity-50 mr-2">[{new Date().toLocaleTimeString().split(' ')[0]}]</span>
                        {log}
                    </div>
                ))}
                <div ref={logsEndRef} />
            </div>
        </div>
    );
};

export default BrowserWindow;

import React, { useEffect, useRef } from 'react';
import { X } from 'lucide-react';

const ChatModule = ({
    messages,
    inputValue,
    setInputValue,
    handleSend,
    isModularMode,
    activeDragElement,
    position,
    width = 672, // default max-w-2xl
    height,
    isVisualMinimal = false,
    zIndex,
    onClose,
    onMouseDown
}) => {
    const messagesEndRef = useRef(null);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    return (
        <div
            id="chat"
            onMouseDown={onMouseDown}
            className={`absolute px-5 py-4 pointer-events-auto transition-all duration-200
            ${isVisualMinimal ? 'opacity-0 hover:opacity-100 focus-within:opacity-100 translate-y-6' : 'opacity-100'}
            ada-float rounded-ada-lg
            ${isModularMode ? (activeDragElement === 'chat' ? 'ring-2 ring-accent/50' : 'ring-1 ring-line') : ''}
        `}
            style={{
                left: position.x,
                top: position.y,
                transform: 'translate(-50%, 0)', // Aligned top-center
                width: width,
                height: height,
                zIndex
            }}
        >
            <div className="relative z-20 mb-3 flex items-center justify-between">
                <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-accent">Chat Ada</p>
                    <p className="text-xs text-muted">Ecris une tache locale ou une demande pour Ada.</p>
                </div>
                {onClose && (
                    <button
                        type="button"
                        onClick={onClose}
                        className="rounded-full border border-line bg-surface p-2 text-muted shadow-ada-sm transition hover:border-danger/40 hover:text-danger"
                        aria-label="Fermer le chat Ada"
                        title="Fermer le chat Ada"
                    >
                        <X size={16} strokeWidth={2} />
                    </button>
                )}
            </div>
            <div
                className="flex flex-col gap-3 overflow-y-auto mb-4 scrollbar-hide mask-image-gradient relative z-10"
                style={{ height: height ? `calc(${height}px - 112px)` : '15rem' }}
            >
                {messages.slice(-5).map((msg, i) => (
                    <div key={i} className="ada-msg-in text-sm border-l-2 border-accent/40 pl-3 py-1">
                        <span className="text-muted text-xs tabular-nums">[{msg.time}]</span> <span className="font-semibold text-ink">{msg.sender}</span>
                        <div className="text-muted mt-1 leading-relaxed">{msg.text}</div>
                    </div>
                ))}
                <div ref={messagesEndRef} />
            </div>

            <div className="flex gap-2 relative z-10 absolute bottom-4 left-6 right-6">
                <input
                    type="text"
                    value={inputValue}
                    onChange={(e) => setInputValue(e.target.value)}
                    onKeyDown={handleSend}
                    placeholder="Demande a Ada d'executer une tache..."
                    className="flex-1 bg-surface border border-line rounded-ada p-3 text-ink focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 transition-all placeholder:text-muted"
                />
            </div>
            {isModularMode && <div className={`absolute -top-6 left-0 text-xs font-semibold tracking-widest ${activeDragElement === 'chat' ? 'text-accent' : 'text-muted'}`}>CHAT MODULE</div>}
        </div>
    );
};

export default ChatModule;

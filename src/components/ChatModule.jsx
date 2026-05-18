import React, { useEffect, useRef } from 'react';

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
            backdrop-blur-xl bg-white/45 border border-white/80 shadow-[0_20px_48px_rgba(37,99,235,0.10)] rounded-2xl
            ${isModularMode ? (activeDragElement === 'chat' ? 'ring-2 ring-blue-400/50' : 'ring-1 ring-blue-200/70') : ''}
        `}
            style={{
                left: position.x,
                top: position.y,
                transform: 'translate(-50%, 0)', // Aligned top-center
                width: width,
                height: height
            }}
        >
            <div
                className="flex flex-col gap-3 overflow-y-auto mb-4 scrollbar-hide mask-image-gradient relative z-10"
                style={{ height: height ? `calc(${height}px - 70px)` : '15rem' }}
            >
                {messages.slice(-5).map((msg, i) => (
                    <div key={i} className="text-sm border-l-2 border-blue-300/70 pl-3 py-1">
                        <span className="text-blue-500 font-mono text-xs opacity-70">[{msg.time}]</span> <span className="font-bold text-[#10294d]">{msg.sender}</span>
                        <div className="text-slate-600 mt-1 leading-relaxed">{msg.text}</div>
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
                    placeholder="INITIALIZE COMMAND..."
                    className="flex-1 bg-white/70 border border-blue-200/80 rounded-xl p-3 text-[#10294d] focus:outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-300/70 transition-all placeholder:text-slate-400 backdrop-blur-sm"
                />
            </div>
            {isModularMode && <div className={`absolute -top-6 left-0 text-xs font-bold tracking-widest ${activeDragElement === 'chat' ? 'text-blue-600' : 'text-blue-400/60'}`}>CHAT MODULE</div>}
        </div>
    );
};

export default ChatModule;

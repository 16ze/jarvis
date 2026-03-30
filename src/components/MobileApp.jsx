import React, { useRef, useEffect, useState } from 'react';
import { Power, Mic, MicOff, Send } from 'lucide-react';

const MobileApp = ({
    socket,
    isConnected,
    isMuted,
    togglePower,
    toggleMute,
    messages,
    aiAudioData,
    audioAmp,
    inputValue,
    setInputValue,
    handleSend,
}) => {
    const messagesEndRef = useRef(null);
    const [showChat, setShowChat] = useState(false);

    useEffect(() => {
        if (messagesEndRef.current) {
            messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
        }
    }, [messages]);

    const orbSize = 120 + (audioAmp || 0) * 80;
    const orbGlow = `0 0 ${40 + (audioAmp || 0) * 60}px rgba(6,182,212,${0.3 + (audioAmp || 0) * 0.5})`;

    return (
        <div className="h-screen w-screen bg-black text-cyan-100 font-mono flex flex-col overflow-hidden select-none">

            {/* Header */}
            <div className="flex items-center justify-between px-6 pt-12 pb-4 shrink-0">
                <div className="flex flex-col">
                    <span className="text-xs text-cyan-500 tracking-widest uppercase">A.D.A</span>
                    <span className="text-[10px] text-cyan-900 tracking-wider">
                        {isConnected ? 'CONNECTÉE' : 'HORS LIGNE'}
                    </span>
                </div>
                <div className="flex items-center gap-3">
                    {/* Chat toggle */}
                    <button
                        onClick={() => setShowChat(!showChat)}
                        className={`text-xs px-3 py-1 rounded-full border transition-all ${
                            showChat
                                ? 'border-cyan-500 text-cyan-400 bg-cyan-900/20'
                                : 'border-cyan-900 text-cyan-700'
                        }`}
                    >
                        {showChat ? 'ORBE' : 'CHAT'}
                    </button>
                    {/* Power */}
                    <button
                        onClick={togglePower}
                        className={`w-8 h-8 rounded-full border-2 flex items-center justify-center transition-all ${
                            isConnected
                                ? 'border-green-500 text-green-500'
                                : 'border-gray-700 text-gray-600'
                        }`}
                    >
                        <Power size={14} />
                    </button>
                </div>
            </div>

            {/* Main area */}
            <div className="flex-1 flex flex-col overflow-hidden">
                {showChat ? (
                    /* Chat view */
                    <div className="flex-1 overflow-y-auto px-4 py-2 space-y-3">
                        {messages.slice(-30).map((msg, i) => (
                            <div
                                key={i}
                                className={`flex flex-col gap-1 ${msg.sender === 'Bryan' ? 'items-end' : 'items-start'}`}
                            >
                                <span className="text-[9px] text-cyan-800 tracking-wider uppercase">
                                    {msg.sender}
                                </span>
                                <div className={`max-w-[85%] px-3 py-2 rounded-2xl text-xs leading-relaxed ${
                                    msg.sender === 'Bryan'
                                        ? 'bg-cyan-900/40 border border-cyan-800/50 text-cyan-100'
                                        : 'bg-gray-900/60 border border-gray-800/50 text-cyan-200'
                                }`}>
                                    {msg.text}
                                </div>
                            </div>
                        ))}
                        <div ref={messagesEndRef} />
                    </div>
                ) : (
                    /* Orb view */
                    <div className="flex-1 flex items-center justify-center">
                        <div className="relative flex items-center justify-center">
                            {/* Outer pulse rings */}
                            {isConnected && !isMuted && (
                                <>
                                    <div
                                        className="absolute rounded-full border border-cyan-500/10 animate-ping"
                                        style={{ width: orbSize + 60, height: orbSize + 60 }}
                                    />
                                    <div
                                        className="absolute rounded-full border border-cyan-500/20 animate-ping"
                                        style={{
                                            width: orbSize + 30,
                                            height: orbSize + 30,
                                            animationDelay: '0.3s'
                                        }}
                                    />
                                </>
                            )}
                            {/* Main orb */}
                            <div
                                className="rounded-full bg-gradient-to-br from-cyan-900/60 to-black border border-cyan-500/30 flex items-center justify-center transition-all duration-100"
                                style={{
                                    width: orbSize,
                                    height: orbSize,
                                    boxShadow: orbGlow,
                                }}
                            >
                                <div className="text-center">
                                    <div className="text-2xl font-light text-cyan-400 tracking-widest">ADA</div>
                                    <div className="text-[9px] text-cyan-700 tracking-wider mt-1">
                                        {!isConnected ? 'OFFLINE' : isMuted ? 'EN VEILLE' : 'À L\'ÉCOUTE'}
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                )}
            </div>

            {/* Text input */}
            <div className="px-4 pb-2 flex gap-2">
                <input
                    type="text"
                    value={inputValue}
                    onChange={(e) => setInputValue(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleSend()}
                    placeholder="Écrire à Ada..."
                    className="flex-1 bg-gray-900/60 border border-cyan-900/50 rounded-full px-4 py-2.5 text-xs text-cyan-100 placeholder-cyan-900 outline-none focus:border-cyan-700"
                />
                <button
                    onClick={handleSend}
                    disabled={!inputValue.trim()}
                    className="w-10 h-10 rounded-full bg-cyan-900/30 border border-cyan-800 flex items-center justify-center text-cyan-500 disabled:opacity-30"
                >
                    <Send size={14} />
                </button>
            </div>

            {/* Mic button */}
            <div className="flex justify-center pb-12 pt-2 shrink-0">
                <button
                    onClick={toggleMute}
                    disabled={!isConnected}
                    className={`w-20 h-20 rounded-full border-2 flex items-center justify-center transition-all duration-300 ${
                        !isConnected
                            ? 'border-gray-800 text-gray-800'
                            : isMuted
                            ? 'border-red-500 bg-red-500/10 text-red-400 shadow-[0_0_20px_rgba(239,68,68,0.2)]'
                            : 'border-cyan-400 bg-cyan-500/10 text-cyan-400 shadow-[0_0_30px_rgba(6,182,212,0.4)]'
                    }`}
                >
                    {isMuted ? <MicOff size={28} /> : <Mic size={28} />}
                </button>
            </div>
        </div>
    );
};

export default MobileApp;

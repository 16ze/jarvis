import React, { useEffect, useRef, useState } from 'react';
import io from 'socket.io-client';

// Même contrat Socket.IO que l'UI principale (src/App.jsx) :
//   emit('user_input', { text })          -> envoie un message
//   on('transcription', { sender, text }) -> réponse en streaming (append par chunk)
//   on('tool_confirmation_request', { id, tool, args }) -> demande d'approbation
//   emit('confirm_tool', { id, confirmed })             -> réponse Autoriser/Refuser
const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';
const ADA_TOKEN = import.meta.env.VITE_ADA_API_TOKEN || '';

export default function MiniChat({ onClose }) {
    const [connected, setConnected] = useState(false);
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState('');
    const [confirmation, setConfirmation] = useState(null);
    const socketRef = useRef(null);
    const endRef = useRef(null);

    useEffect(() => {
        const socket = io(BACKEND_URL, {
            transports: ['websocket'],
            upgrade: false,
            auth: ADA_TOKEN ? { token: ADA_TOKEN } : undefined,
        });
        socketRef.current = socket;

        socket.on('connect', () => setConnected(true));
        socket.on('disconnect', () => setConnected(false));

        // Streaming texte — même logique d'append par expéditeur que l'app principale.
        socket.on('transcription', (data) => {
            if (!data || !data.text) return;
            setMessages((prev) => {
                const last = prev[prev.length - 1];
                if (last && last.sender === data.sender) {
                    return [...prev.slice(0, -1), { ...last, text: last.text + data.text }];
                }
                return [...prev, { sender: data.sender, text: data.text }];
            });
        });

        socket.on('status', (data) => {
            if (data && data.message) {
                setMessages((prev) => [...prev, { sender: 'System', text: data.message }]);
            }
        });

        socket.on('error', (data) => {
            const msg = typeof data === 'string' ? data : (data && data.message) || 'Erreur';
            setMessages((prev) => [...prev, { sender: 'System', text: `⚠️ ${msg}` }]);
        });

        // Approbation d'une action sensible (modèle hybride : seules les actions
        // qui modifient qqch arrivent ici).
        socket.on('tool_confirmation_request', (data) => setConfirmation(data));

        return () => socket.close();
    }, []);

    useEffect(() => {
        endRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages, confirmation]);

    const send = () => {
        const text = input.trim();
        if (!text || !socketRef.current) return;
        socketRef.current.emit('user_input', { text });
        setMessages((prev) => [...prev, { sender: 'You', text }]);
        setInput('');
    };

    const respond = (confirmed) => {
        if (confirmation && socketRef.current) {
            socketRef.current.emit('confirm_tool', { id: confirmation.id, confirmed });
        }
        setConfirmation(null);
    };

    const senderClass = (s) => {
        if (s === 'You') return 'you';
        if (s === 'System') return 'system';
        return 'ada';
    };

    return (
        <div className="jv-panel">
            <div className="jv-head">
                <span className={`jv-dot ${connected ? 'on' : ''}`} />
                <span className="jv-title">Jarvis</span>
                <button className="jv-close" onClick={onClose} title="Réduire">×</button>
            </div>

            <div className="jv-msgs">
                {messages.length === 0 && (
                    <div className="jv-bubble system">Dis-moi quelque chose…</div>
                )}
                {messages.map((m, i) => (
                    <div key={i} className={`jv-bubble ${senderClass(m.sender)}`}>
                        {m.sender !== 'You' && m.sender !== 'System' && (
                            <span className="jv-sender">{m.sender}</span>
                        )}
                        {m.text}
                    </div>
                ))}
                <div ref={endRef} />
            </div>

            {confirmation && (
                <div className="jv-approve">
                    <div className="jv-ap-title">Autorisation requise</div>
                    <div className="jv-ap-tool">{confirmation.tool || 'action'}</div>
                    {confirmation.args && (
                        <pre>{JSON.stringify(confirmation.args, null, 2)}</pre>
                    )}
                    <div className="jv-ap-actions">
                        <button className="jv-btn ok" onClick={() => respond(true)}>Autoriser</button>
                        <button className="jv-btn no" onClick={() => respond(false)}>Refuser</button>
                    </div>
                </div>
            )}

            <div className="jv-input-row">
                <input
                    className="jv-input"
                    value={input}
                    placeholder="Message…"
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') send(); }}
                />
                <button className="jv-send" onClick={send} disabled={!input.trim()} title="Envoyer">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" /></svg>
                </button>
            </div>
        </div>
    );
}

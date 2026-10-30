import React, { useRef, useEffect, useState } from 'react';
import { History, Power, Mic, MicOff } from 'lucide-react';
import Face from '../widget/Face';
import ChatComposer from './chat/ChatComposer';
import EditableUserMessage from './chat/EditableUserMessage';
import MarkdownMessage from './chat/MarkdownMessage';
import MobileConversationDrawer from './MobileConversationDrawer';

/*
 * MobileApp — interface mobile ET tablette d'Ada, « propre comme Apple ».
 *
 * Consomme le design system déjà posé (tokens clair/sombre : bg/surface/ink/
 * muted/line/accent, rayons rounded-ada, ombres shadow-ada, boutons ada-btn).
 * Aucune couleur n'est codée en dur : tout passe par les tokens → beau en clair
 * comme en sombre. Le câblage (socket, props, handlers, <Face/>) est conservé.
 *
 *  - Téléphone  : plein écran, visage central, bascule Visage/Conversation,
 *                 saisie + micro ancrés en bas au-dessus de la safe-area.
 *  - Tablette   : deux colonnes (présence à gauche, conversation à droite),
 *                 mise en page aérée façon iPad (≥ 768px, confortable ≤ 1180px).
 */
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
    handleStopGeneration,
    handleEditMessage,
    handleCopyMessage,
    conversations = [],
    activeConversationId,
    conversationSyncStatus = 'local',
    onNewConversation,
    onSelectConversation,
    onDeleteConversation,
    adaAffect = null,
    adaSpeaking = false,
    adaPiloting = false,
    micRef = null,
    audioError = '',
}) => {
    const messagesEndRef = useRef(null);
    const [showChat, setShowChat] = useState(false);
    const [showHistory, setShowHistory] = useState(false);

    // Largeur de fenêtre → choix des tailles (visage, colonnes). Le composant est
    // rendu jusqu'à ~1180px ; on adapte donc le visage au palier téléphone/tablette.
    const [vw, setVw] = useState(() =>
        typeof window !== 'undefined' ? window.innerWidth : 390
    );
    useEffect(() => {
        const onResize = () => setVw(window.innerWidth);
        window.addEventListener('resize', onResize);
        return () => window.removeEventListener('resize', onResize);
    }, []);
    const isWide = vw >= 768;

    useEffect(() => {
        if (messagesEndRef.current) {
            messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
        }
    }, [messages]);

    const amp = audioAmp || 0;
    // Le disque respire légèrement avec l'amplitude audio — sobre, sans glow.
    const diskSize = Math.round((isWide ? 300 : 216) + amp * (isWide ? 64 : 48));
    const faceSize = Math.round(diskSize * 0.74);
    const live = isConnected && !isMuted;

    const statusLabel = !isConnected
        ? 'Hors ligne'
        : adaSpeaking
        ? 'Ada répond…'
        : isMuted
        ? 'En veille'
        : 'À l’écoute';

    // ── Briques réutilisées par les deux mises en page ───────────────────────
    const Brand = (
        <div className="flex items-center gap-2.5">
            <span
                className={`inline-block h-2 w-2 rounded-full transition-colors ${
                    isConnected ? 'bg-positive' : 'bg-muted/50'
                }`}
            />
            <div className="flex flex-col leading-tight">
                <span className="text-sm font-semibold tracking-[0.18em] text-ink">ADA</span>
                <span className="text-[11px] text-muted">
                    {isConnected ? 'Connectée' : 'Hors ligne'}
                </span>
            </div>
        </div>
    );

    const PowerButton = (
        <button
            onClick={togglePower}
            aria-label={isConnected ? 'Éteindre Ada' : 'Allumer Ada'}
            className={`grid h-11 w-11 place-items-center rounded-full border transition-all active:scale-95 ${
                isConnected
                    ? 'border-positive/40 text-positive bg-positive/10'
                    : 'border-line text-muted bg-surface'
            }`}
        >
            <Power size={16} />
        </button>
    );

    const MicButton = (
        <div className="flex flex-col items-center gap-2">
            {audioError ? (
                <p className="max-w-[280px] text-center text-[11px] leading-relaxed text-danger">{audioError}</p>
            ) : (
                isMuted && <p className="text-[11px] tracking-wide text-muted">Touche le micro pour parler</p>
            )}
            <button
                onClick={toggleMute}
                disabled={!isConnected}
                aria-label={isMuted ? 'Réactiver le micro' : 'Mettre en veille'}
                className={`grid h-[72px] w-[72px] place-items-center rounded-full border transition-all duration-300 active:scale-95 shadow-ada ${
                    !isConnected
                        ? 'border-line text-muted/60 bg-surface'
                        : isMuted
                        ? 'border-danger/40 text-danger bg-danger/10'
                        : 'border-accent/40 text-accent bg-accent/10'
                }`}
            >
                {isMuted ? <MicOff size={26} /> : <Mic size={26} />}
            </button>
        </div>
    );

    const FaceStage = (
        <div className="relative flex flex-col items-center justify-center gap-4">
            <div className="relative grid place-items-center">
                {/* Anneau d'écoute : pulsation discrète en accent (pas de néon) */}
                {live && (
                    <span
                        className="pointer-events-none absolute rounded-full border border-accent/25 animate-ping"
                        style={{ width: diskSize + 28, height: diskSize + 28 }}
                    />
                )}
                {/* Disque de présence : surface douce, bordure fine, ombre Apple */}
                <div
                    className="grid place-items-center rounded-full bg-surface2 border border-line shadow-ada-md"
                    style={{
                        width: diskSize,
                        height: diskSize,
                        transition: 'width .15s var(--ada-ease), height .15s var(--ada-ease)',
                    }}
                >
                    <Face
                        affect={adaAffect}
                        talking={adaSpeaking || amp > 0.06}
                        acting={adaPiloting}
                        micRef={isMuted ? null : micRef}
                        size={faceSize}
                    />
                </div>
            </div>
            <span className="text-[13px] font-medium tracking-wide text-muted">
                {statusLabel}
            </span>
        </div>
    );

    const renderMessages = () => (
        <div className="flex h-full flex-col gap-3 overflow-y-auto px-1">
            {messages.length === 0 && (
                <div className="flex h-full flex-col items-center justify-center text-center">
                    <p className="text-sm text-muted">Aucun message pour l’instant.</p>
                    <p className="mt-1 text-xs text-muted/70">
                        Écris un message ou parle à Ada.
                    </p>
                </div>
            )}
            {messages.slice(-100).map((msg, i) => {
                const mine = msg.sender === 'Bryan';
                const messageIndex = Math.max(0, messages.length - 100) + i;
                if (msg.sender === 'System') {
                    return (
                        <div key={messageIndex} className="ada-msg-in mx-auto max-w-[90%] text-center">
                            <span className="rounded-full border border-line bg-surface px-3 py-1 text-[11px] text-muted">{msg.text}</span>
                        </div>
                    );
                }
                if (mine) {
                    return (
                        <EditableUserMessage
                            key={messageIndex}
                            text={msg.text}
                            edited={msg.edited}
                            disabled={adaSpeaking}
                            alwaysShowActions
                            onCopy={() => handleCopyMessage?.(msg.text)}
                            onSave={(nextText) => handleEditMessage?.(messageIndex, nextText)}
                        />
                    );
                }
                return (
                    <div
                        key={messageIndex}
                        className="ada-msg-in flex flex-col items-start gap-1"
                    >
                        <span className="px-1 text-[10px] font-medium tracking-wide text-muted">
                            Ada
                        </span>
                        <div className="max-w-[92%] rounded-ada border border-line bg-surface px-3.5 py-2.5 text-sm leading-relaxed text-ink shadow-ada-sm">
                            <MarkdownMessage text={msg.text} />
                        </div>
                    </div>
                );
            })}
            <div ref={messagesEndRef} />
        </div>
    );

    const InputBar = (
        <ChatComposer
            value={inputValue}
            onChange={setInputValue}
            onSend={() => handleSend?.()}
            onStop={handleStopGeneration}
            isGenerating={adaSpeaking}
            disabled={!socket?.connected}
            placeholder="Écrire à Ada…"
        />
    );

    return (
        <div
            className="flex h-screen w-screen select-none flex-col overflow-hidden bg-bg text-ink"
            style={{
                paddingTop: 'env(safe-area-inset-top)',
                paddingBottom: 'env(safe-area-inset-bottom)',
                paddingLeft: 'env(safe-area-inset-left)',
                paddingRight: 'env(safe-area-inset-right)',
            }}
        >
            <MobileConversationDrawer
                open={showHistory}
                conversations={conversations}
                activeId={activeConversationId}
                disabled={adaSpeaking}
                syncStatus={conversationSyncStatus}
                onClose={() => setShowHistory(false)}
                onNew={() => {
                    onNewConversation?.();
                    setShowChat(true);
                }}
                onSelect={(id) => {
                    onSelectConversation?.(id);
                    setShowChat(true);
                }}
                onDelete={onDeleteConversation}
            />

            {/* ── En-tête téléphone (masqué en tablette) ─────────────────────── */}
            <header className="flex shrink-0 items-center justify-between px-5 pb-3 pt-4 md:hidden">
                {Brand}
                <div className="flex items-center gap-2.5">
                    <button
                        type="button"
                        onClick={() => setShowHistory(true)}
                        aria-label="Afficher l’historique"
                        className="grid h-11 w-11 place-items-center rounded-full border border-line text-muted transition active:scale-95"
                    >
                        <History size={16} />
                    </button>
                    <button
                        onClick={() => setShowChat(!showChat)}
                        className={`min-h-11 rounded-full border px-3.5 py-1.5 text-xs font-medium transition-all active:scale-95 ${
                            showChat
                                ? 'border-accent/40 bg-accent/10 text-accent'
                                : 'border-line text-muted'
                        }`}
                    >
                        {showChat ? 'Visage' : 'Conversation'}
                    </button>
                    {PowerButton}
                </div>
            </header>

            {/* ── Contenu : 1 colonne (téléphone) / 2 colonnes (tablette) ─────── */}
            <div className="mx-auto flex w-full min-h-0 max-w-6xl flex-1 flex-col md:flex-row md:gap-6 md:px-6 md:py-5">
                {/* Présence : visage + contrôles */}
                <section
                    className={`${showChat ? 'hidden' : 'flex'} min-h-0 flex-1 flex-col md:flex md:max-w-[46%] md:rounded-ada-lg md:border md:border-line md:bg-surface md:p-6 md:shadow-ada`}
                >
                    {/* Marque + power (tablette uniquement) */}
                    <div className="hidden items-center justify-between md:flex">
                        {Brand}
                        <div className="flex items-center gap-2">
                            <button
                                type="button"
                                onClick={() => setShowHistory(true)}
                                aria-label="Afficher l’historique"
                                className="grid h-11 w-11 place-items-center rounded-full border border-line text-muted hover:bg-ink/[0.05]"
                            >
                                <History size={17} />
                            </button>
                            {PowerButton}
                        </div>
                    </div>

                    <div className="grid flex-1 place-items-center">{FaceStage}</div>

                    {/* Micro (tablette : sous le visage) */}
                    <div className="hidden justify-center pt-2 md:flex">{MicButton}</div>
                </section>

                {/* Conversation : fil + saisie */}
                <section
                    className={`${showChat ? 'flex' : 'hidden'} min-h-0 flex-1 flex-col md:flex md:rounded-ada-lg md:border md:border-line md:bg-surface md:p-5 md:shadow-ada`}
                >
                    <div className="min-h-0 flex-1 px-4 py-2 md:px-0 md:py-0">
                        {renderMessages()}
                    </div>
                    {/* Saisie (tablette : au bas de la colonne) */}
                    <div className="hidden pt-4 md:block">{InputBar}</div>
                </section>
            </div>

            {/* ── Barre basse téléphone : saisie + micro (masquée en tablette) ── */}
            <div className="shrink-0 px-4 pb-4 pt-1 md:hidden">
                <div className="pb-3">{InputBar}</div>
                <div className="flex justify-center">{MicButton}</div>
            </div>
        </div>
    );
};

export default MobileApp;

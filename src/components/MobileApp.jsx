import React, { useRef, useEffect, useState } from 'react';
import { Power, Mic, MicOff, Send } from 'lucide-react';
import Face from '../widget/Face';

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
    adaAffect = null,
    adaSpeaking = false,
    adaPiloting = false,
    micRef = null,
}) => {
    const messagesEndRef = useRef(null);
    const [showChat, setShowChat] = useState(false);

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

    const statusLabel = !isConnected ? 'Hors ligne' : isMuted ? 'En veille' : 'À l’écoute';

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
            className={`grid h-10 w-10 place-items-center rounded-full border transition-all active:scale-95 ${
                isConnected
                    ? 'border-positive/40 text-positive bg-positive/10'
                    : 'border-line text-muted bg-surface'
            }`}
        >
            <Power size={16} />
        </button>
    );

    const MicButton = (
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
            {messages.slice(-30).map((msg, i) => {
                const mine = msg.sender === 'Bryan';
                return (
                    <div
                        key={i}
                        className={`ada-msg-in flex flex-col gap-1 ${mine ? 'items-end' : 'items-start'}`}
                    >
                        <span className="px-1 text-[10px] font-medium tracking-wide text-muted">
                            {msg.sender}
                        </span>
                        <div
                            className={`max-w-[85%] rounded-ada px-3.5 py-2.5 text-sm leading-relaxed shadow-ada-sm ${
                                mine
                                    ? 'bg-accent text-white'
                                    : 'border border-line bg-surface text-ink'
                            }`}
                        >
                            {msg.text}
                        </div>
                    </div>
                );
            })}
            <div ref={messagesEndRef} />
        </div>
    );

    const InputBar = (
        <div className="flex items-center gap-2">
            <input
                type="text"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSend()}
                placeholder="Écrire à Ada…"
                className="h-11 flex-1 rounded-full border border-line bg-surface px-4 text-sm text-ink placeholder:text-muted outline-none transition-all focus:border-accent focus:shadow-[0_0_0_3px_rgb(var(--c-accent)/0.18)]"
            />
            <button
                onClick={handleSend}
                disabled={!inputValue.trim()}
                aria-label="Envoyer"
                className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-accent text-white transition-all active:scale-95 disabled:opacity-30"
            >
                <Send size={17} />
            </button>
        </div>
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
            {/* ── En-tête téléphone (masqué en tablette) ─────────────────────── */}
            <header className="flex shrink-0 items-center justify-between px-5 pb-3 pt-4 lg:hidden">
                {Brand}
                <div className="flex items-center gap-2.5">
                    <button
                        onClick={() => setShowChat(!showChat)}
                        className={`rounded-full border px-3.5 py-1.5 text-xs font-medium transition-all active:scale-95 ${
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
            <div className="mx-auto flex w-full min-h-0 max-w-6xl flex-1 flex-col lg:flex-row lg:gap-6 lg:px-6 lg:py-5">
                {/* Présence : visage + contrôles */}
                <section
                    className={`${showChat ? 'hidden' : 'flex'} min-h-0 flex-1 flex-col lg:flex lg:max-w-[46%] lg:rounded-ada-lg lg:border lg:border-line lg:bg-surface lg:p-6 lg:shadow-ada`}
                >
                    {/* Marque + power (tablette uniquement) */}
                    <div className="hidden items-center justify-between lg:flex">
                        {Brand}
                        {PowerButton}
                    </div>

                    <div className="grid flex-1 place-items-center">{FaceStage}</div>

                    {/* Micro (tablette : sous le visage) */}
                    <div className="hidden justify-center pt-2 lg:flex">{MicButton}</div>
                </section>

                {/* Conversation : fil + saisie */}
                <section
                    className={`${showChat ? 'flex' : 'hidden'} min-h-0 flex-1 flex-col lg:flex lg:rounded-ada-lg lg:border lg:border-line lg:bg-surface lg:p-5 lg:shadow-ada`}
                >
                    <div className="min-h-0 flex-1 px-4 py-2 lg:px-0 lg:py-0">
                        {renderMessages()}
                    </div>
                    {/* Saisie (tablette : au bas de la colonne) */}
                    <div className="hidden pt-4 lg:block">{InputBar}</div>
                </section>
            </div>

            {/* ── Barre basse téléphone : saisie + micro (masquée en tablette) ── */}
            <div className="shrink-0 px-4 pb-4 pt-1 lg:hidden">
                <div className="pb-3">{InputBar}</div>
                <div className="flex justify-center">{MicButton}</div>
            </div>
        </div>
    );
};

export default MobileApp;

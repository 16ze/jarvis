import React, { useEffect, useRef, useState } from 'react';
import { Mic, MicOff, Settings, Power, Video, VideoOff, Hand, Lightbulb, Printer, Box, Monitor, BookOpen, MessageSquareText, Layout, Activity, Cpu, Wrench, X } from 'lucide-react';

const ToolBubble = ({ icon, label, active, disabled, onClick, title, className = '' }) => (
    <button
        type="button"
        onClick={disabled ? undefined : onClick}
        disabled={disabled}
        title={title || label}
        aria-label={title || label}
        className={`ada-glass-circle group flex h-[86px] w-[86px] flex-col items-center justify-center gap-1.5 text-[11px] font-medium text-ink transition-all duration-300 hover:-translate-y-1 hover:scale-[1.03] disabled:opacity-40 disabled:hover:translate-y-0 disabled:hover:scale-100 ${active ? 'text-accent ring-2 ring-accent/40' : ''} ${className}`}
    >
        <span className={`${active ? 'text-accent' : 'text-accent/90'} transition-colors`}>
            {icon}
        </span>
        <span className="max-w-[68px] truncate leading-none">{label}</span>
    </button>
);

const MenuIcon = ({ open }) => (
    <span className="relative block h-6 w-7 text-accent">
        <span
            className={`absolute left-0 top-[7px] h-[2px] w-7 rounded-full bg-current transition-transform duration-300 ${open ? 'translate-y-1 rotate-45' : ''}`}
        />
        <span
            className={`absolute left-0 top-[15px] h-[2px] w-7 rounded-full bg-current transition-transform duration-300 ${open ? '-translate-y-1 -rotate-45' : ''}`}
        />
    </span>
);

const ToolsModule = ({
    isConnected,
    isMuted,
    isVideoOn,
    isHandTrackingEnabled,
    showSettings,
    onTogglePower,
    onToggleMute,
    onToggleVideo,
    onToggleSettings,
    onToggleChat,
    showChatWindow,

    onToggleHand,
    onToggleKasa,
    showKasaWindow,
    onTogglePrinter,
    showPrinterWindow,
    onToggleCad,
    showCadWindow,
    isScreenMode,
    onToggleScreenMode,
    onToggleDocuments,
    onToggleWorkspace,
    showWorkspaceWindow,
    onOpenObservability,
    onOpenAgents,
    activeOsScreen,
    activeDragElement,
    isModularMode = false,

    position,
    onMouseDown
}) => {
    const [isOpen, setIsOpen] = useState(false);
    const menuRef = useRef(null);

    useEffect(() => {
        if (showChatWindow) {
            setIsOpen(false);
        }
    }, [showChatWindow]);

    useEffect(() => {
        if (!isOpen || isModularMode) return undefined;

        const closeOnOutsideClick = (event) => {
            if (!menuRef.current?.contains(event.target)) setIsOpen(false);
        };
        const closeOnEscape = (event) => {
            if (event.key === 'Escape') setIsOpen(false);
        };

        document.addEventListener('pointerdown', closeOnOutsideClick);
        document.addEventListener('keydown', closeOnEscape);
        return () => {
            document.removeEventListener('pointerdown', closeOnOutsideClick);
            document.removeEventListener('keydown', closeOnEscape);
        };
    }, [isOpen, isModularMode]);

    const runToolAction = (action) => {
        setIsOpen(false);
        action?.();
    };

    const tools = [
        {
            key: 'camera',
            label: 'Camera',
            icon: isVideoOn ? <Video size={27} strokeWidth={1.8} /> : <VideoOff size={27} strokeWidth={1.8} />,
            active: isVideoOn,
            onClick: onToggleVideo,
        },
        {
            key: 'workspace',
            label: 'Workspace',
            icon: <Layout size={27} strokeWidth={1.8} />,
            active: showWorkspaceWindow,
            onClick: onToggleWorkspace,
        },
        {
            key: 'documents',
            label: 'Documents',
            icon: <BookOpen size={27} strokeWidth={1.8} />,
            active: false,
            onClick: onToggleDocuments,
        },
        {
            key: 'chat',
            label: 'Chat',
            icon: <MessageSquareText size={27} strokeWidth={1.8} />,
            active: showChatWindow,
            onClick: onToggleChat,
        },
        {
            key: 'settings',
            label: 'Parametres',
            icon: <Settings size={27} strokeWidth={1.8} />,
            active: showSettings,
            onClick: onToggleSettings,
        },
        {
            key: 'mic',
            label: isMuted ? 'Muet' : 'Micro',
            icon: isMuted ? <MicOff size={27} strokeWidth={1.8} /> : <Mic size={27} strokeWidth={1.8} />,
            active: !isMuted && isConnected,
            disabled: !isConnected,
            onClick: onToggleMute,
        },
        {
            key: 'screenwatcher',
            label: 'Ecran',
            icon: <Monitor size={27} strokeWidth={1.8} />,
            active: isScreenMode,
            onClick: onToggleScreenMode,
        },
        {
            key: 'cad',
            label: 'CAD',
            icon: <Box size={25} strokeWidth={1.8} />,
            active: showCadWindow,
            onClick: onToggleCad,
        },
        {
            key: 'printer',
            label: 'Printer',
            icon: <Printer size={25} strokeWidth={1.8} />,
            active: showPrinterWindow,
            onClick: onTogglePrinter,
        },
        {
            key: 'home',
            label: 'Maison',
            icon: <Lightbulb size={25} strokeWidth={1.8} />,
            active: showKasaWindow,
            onClick: onToggleKasa,
        },
        {
            key: 'hand',
            label: 'Main',
            icon: <Hand size={25} strokeWidth={1.8} />,
            active: isHandTrackingEnabled,
            onClick: onToggleHand,
        },
        {
            key: 'observability',
            label: 'Activité',
            icon: <Activity size={25} strokeWidth={1.8} />,
            active: activeOsScreen === 'observability',
            onClick: onOpenObservability,
        },
        {
            key: 'agents',
            label: 'Agents',
            icon: <Cpu size={25} strokeWidth={1.8} />,
            active: activeOsScreen === 'agents',
            onClick: onOpenAgents,
        },
        {
            key: 'power',
            label: 'Power',
            icon: <Power size={25} strokeWidth={1.8} />,
            active: isConnected,
            onClick: onTogglePower,
        },
    ];

    if (!isModularMode) {
        const conversationTools = tools.filter((tool) => tool.key !== 'chat');

        return (
            <div
                id="tools"
                ref={menuRef}
                className="pointer-events-auto fixed right-5 top-[112px] z-[500]"
            >
                <button
                    type="button"
                    onClick={() => setIsOpen((open) => !open)}
                    className="inline-flex h-11 items-center gap-2 rounded-full border border-line bg-surface px-4 text-sm font-medium text-ink shadow-ada transition hover:bg-surface2 focus:outline-none focus-visible:shadow-[0_0_0_3px_rgb(var(--c-accent)/0.18)]"
                    aria-expanded={isOpen}
                    aria-controls="conversation-tools-menu"
                    aria-label={isOpen ? 'Fermer les outils' : 'Ouvrir les outils'}
                >
                    {isOpen ? <X size={17} /> : <Wrench size={17} />}
                    <span>Outils</span>
                </button>

                {isOpen && (
                    <div
                        id="conversation-tools-menu"
                        role="dialog"
                        aria-label="Outils Ada"
                        className="absolute right-0 top-[52px] w-[min(440px,calc(100vw-32px))] rounded-ada-lg border border-line bg-surface p-3 shadow-ada-lg"
                    >
                        <div className="mb-2 px-1 text-xs font-semibold uppercase tracking-[0.12em] text-muted">
                            Capacités d’Ada
                        </div>
                        <div className="grid max-h-[min(520px,calc(100vh-150px))] grid-cols-2 gap-2 overflow-y-auto p-1 sm:grid-cols-3">
                            {conversationTools.map(({ key, icon, label, active, disabled, onClick }) => (
                                <button
                                    key={key}
                                    type="button"
                                    onClick={() => runToolAction(onClick)}
                                    disabled={disabled}
                                    aria-pressed={Boolean(active)}
                                    className={`flex min-h-16 items-center gap-3 rounded-ada border px-3 py-2.5 text-left text-sm transition focus:outline-none focus-visible:shadow-[0_0_0_3px_rgb(var(--c-accent)/0.18)] disabled:cursor-not-allowed disabled:opacity-40 ${
                                        active
                                            ? 'border-accent/40 bg-accent/10 text-accent'
                                            : 'border-line bg-surface2 text-ink hover:border-accent/30 hover:bg-accent/5'
                                    }`}
                                >
                                    <span className="shrink-0 text-accent">{icon}</span>
                                    <span className="min-w-0 truncate font-medium">{label}</span>
                                </button>
                            ))}
                        </div>
                    </div>
                )}
            </div>
        );
    }

    return (
        <div
            id="tools"
            onMouseDown={onMouseDown}
            className={`fixed transition-opacity duration-200 ${showChatWindow ? 'pointer-events-none opacity-0' : 'pointer-events-auto opacity-100'}`}
            style={{
                left: '50%',
                bottom: 0,
                transform: 'translateX(-50%)',
                width: 560,
                height: 320,
                zIndex: 500,
            }}
        >
            <div
                className={`absolute left-1/2 top-[88px] h-[190px] w-[610px] -translate-x-1/2 rounded-full bg-ink/5 blur-2xl transition-opacity duration-300 ${isOpen ? 'opacity-100' : 'opacity-0'}`}
                aria-hidden="true"
            />
            <div className={`absolute inset-0 transition-opacity duration-300 ${isOpen ? 'opacity-100' : 'pointer-events-none opacity-0'}`}>
                {tools.slice(0, 6).map((tool, index) => {
                    const { key, ...toolProps } = tool;
                    const positions = [
                        { left: 280, top: 38 },
                        { left: 170, top: 82 },
                        { left: 390, top: 82 },
                        { left: 116, top: 178 },
                        { left: 280, top: 158 },
                        { left: 444, top: 178 },
                    ];
                    return (
                        <div
                            key={key}
                            className="absolute transition-all duration-300"
                            style={{
                                left: positions[index].left,
                                top: positions[index].top,
                                transform: isOpen ? 'translate(-50%, -50%) scale(1)' : 'translate(-50%, 25%) scale(0.7)',
                                transitionDelay: `${index * 28}ms`,
                            }}
                        >
                            <ToolBubble {...toolProps} onClick={() => runToolAction(toolProps.onClick)} />
                        </div>
                    );
                })}
            </div>

            <div className={`absolute inset-0 transition-opacity duration-300 ${isOpen && isModularMode ? 'opacity-100' : 'pointer-events-none opacity-0'}`}>
                {tools.slice(6).map((tool, index) => {
                    const { key, ...toolProps } = tool;
                    return (
                        <div
                            key={key}
                            className="absolute transition-all duration-300"
                            style={{
                                left: 96 + index * 92,
                                top: 28,
                                transform: isOpen ? 'translate(-50%, -50%) scale(0.86)' : 'translate(-50%, 35%) scale(0.6)',
                            }}
                        >
                            <ToolBubble {...toolProps} onClick={() => runToolAction(toolProps.onClick)} className="h-[68px] w-[68px] text-[10px]" />
                        </div>
                    );
                })}
            </div>

            <div className="absolute left-1/2 top-[238px] z-30 -translate-x-1/2 -translate-y-1/2">
                <button
                    type="button"
                    onClick={() => setIsOpen(prev => !prev)}
                    className="ada-glass-circle flex h-[76px] w-[76px] items-center justify-center text-accent transition-all duration-300 hover:-translate-y-1 hover:scale-[1.03]"
                    aria-label={isOpen ? 'Fermer le menu' : 'Ouvrir le menu'}
                    title={isOpen ? 'Fermer le menu' : 'Ouvrir le menu'}
                >
                    <MenuIcon open={isOpen} />
                </button>
            </div>
        </div>
    );
};

export default ToolsModule;

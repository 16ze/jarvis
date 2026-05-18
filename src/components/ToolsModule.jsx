import React, { useState } from 'react';
import { Mic, MicOff, Settings, Power, Video, VideoOff, Hand, Lightbulb, Printer, Box, Monitor, BookOpen, Image } from 'lucide-react';

const ToolBubble = ({ icon, label, active, disabled, onClick, title, className = '' }) => (
    <button
        type="button"
        onClick={disabled ? undefined : onClick}
        disabled={disabled}
        title={title || label}
        aria-label={title || label}
        className={`ada-glass-circle group flex h-[86px] w-[86px] flex-col items-center justify-center gap-1.5 text-[11px] font-medium text-[#10294d] transition-all duration-300 hover:-translate-y-1 hover:scale-[1.03] disabled:opacity-40 disabled:hover:translate-y-0 disabled:hover:scale-100 ${active ? 'text-blue-600 ring-2 ring-blue-400/40' : ''} ${className}`}
    >
        <span className={`${active ? 'text-blue-600' : 'text-blue-600/90'} transition-colors`}>
            {icon}
        </span>
        <span className="max-w-[68px] truncate leading-none">{label}</span>
    </button>
);

const MenuIcon = ({ open }) => (
    <span className="relative block h-6 w-7 text-blue-600">
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
    activeDragElement,
    isModularMode = false,

    position,
    onMouseDown
}) => {
    const [isOpen, setIsOpen] = useState(false);

    const tools = [
        {
            key: 'camera',
            label: 'Camera',
            icon: isVideoOn ? <Video size={27} strokeWidth={1.8} /> : <VideoOff size={27} strokeWidth={1.8} />,
            active: isVideoOn,
            onClick: onToggleVideo,
        },
        {
            key: 'documents',
            label: 'Documents',
            icon: <BookOpen size={27} strokeWidth={1.8} />,
            active: false,
            onClick: onToggleDocuments,
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
            key: 'gallery',
            label: 'Galerie',
            icon: <Image size={27} strokeWidth={1.8} />,
            active: false,
            onClick: onToggleDocuments,
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
            key: 'power',
            label: 'Power',
            icon: <Power size={25} strokeWidth={1.8} />,
            active: isConnected,
            onClick: onTogglePower,
        },
    ];

    return (
        <div
            id="tools"
            onMouseDown={onMouseDown}
            className="absolute pointer-events-auto"
            style={{
                left: position.x,
                top: position.y,
                transform: 'translate(-50%, -50%)',
                width: 560,
                height: 320,
                zIndex: 80,
            }}
        >
            <div
                className={`absolute left-1/2 top-[88px] h-[190px] w-[610px] -translate-x-1/2 rounded-full bg-white/70 blur-xl transition-opacity duration-300 ${isOpen ? 'opacity-100' : 'opacity-0'}`}
                aria-hidden="true"
            />
            <div className={`absolute inset-0 transition-opacity duration-300 ${isOpen ? 'opacity-100' : 'pointer-events-none opacity-0'}`}>
                {tools.slice(0, 5).map((tool, index) => {
                    const { key, ...toolProps } = tool;
                    const positions = [
                        { left: 280, top: 38 },
                        { left: 164, top: 96 },
                        { left: 396, top: 96 },
                        { left: 116, top: 210 },
                        { left: 444, top: 210 },
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
                            <ToolBubble {...toolProps} />
                        </div>
                    );
                })}
            </div>

            <div className={`absolute inset-0 transition-opacity duration-300 ${isOpen && isModularMode ? 'opacity-100' : 'pointer-events-none opacity-0'}`}>
                {tools.slice(5).map((tool, index) => {
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
                            <ToolBubble {...toolProps} className="h-[68px] w-[68px] text-[10px]" />
                        </div>
                    );
                })}
            </div>

            <div className="absolute left-1/2 top-[238px] -translate-x-1/2 -translate-y-1/2">
                <button
                    type="button"
                    onClick={() => setIsOpen(prev => !prev)}
                    className="ada-glass-circle flex h-[76px] w-[76px] items-center justify-center text-blue-600 transition-all duration-300 hover:-translate-y-1 hover:scale-[1.03]"
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

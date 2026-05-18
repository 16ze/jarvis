import React, { useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
    Mic, MicOff, Settings, Power, Video, VideoOff,
    Hand, Lightbulb, Printer, Box, Monitor, BookOpen,
} from 'lucide-react';
import GlassButton from './GlassButton';

const HamburgerIcon = ({ isOpen }) => (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
        <motion.line
            x1="4" y1="9" x2="20" y2="9"
            animate={isOpen ? { rotate: 45, y: 3 } : { rotate: 0, y: 0 }}
            style={{ originX: '12px', originY: '9px' }}
            transition={{ type: 'spring', stiffness: 300, damping: 22 }}
        />
        <motion.line
            x1="4" y1="15" x2="20" y2="15"
            animate={isOpen ? { rotate: -45, y: -3 } : { rotate: 0, y: 0 }}
            style={{ originX: '12px', originY: '15px' }}
            transition={{ type: 'spring', stiffness: 300, damping: 22 }}
        />
    </svg>
);

const HamburgerMenu = ({
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
    position,
    onMouseDown,
}) => {
    const [isOpen, setIsOpen] = useState(false);

    const tools = [
        { id: 'power', icon: <Power size={22} />, isActive: isConnected, accent: 'green', onClick: onTogglePower, title: 'Power' },
        { id: 'mic', icon: isMuted ? <MicOff size={22} /> : <Mic size={22} />, isActive: !isMuted && isConnected, accent: isMuted ? 'red' : 'cyan', disabled: !isConnected, onClick: onToggleMute, title: isMuted ? 'Unmute' : 'Mute' },
        { id: 'video', icon: isVideoOn ? <Video size={22} /> : <VideoOff size={22} />, isActive: isVideoOn, accent: 'purple', onClick: onToggleVideo, title: isVideoOn ? 'Disable video' : 'Enable video' },
        { id: 'settings', icon: <Settings size={22} />, isActive: showSettings, accent: 'cyan', onClick: onToggleSettings, title: 'Settings' },
        { id: 'hand', icon: <Hand size={22} />, isActive: isHandTrackingEnabled, accent: 'orange', onClick: onToggleHand, title: 'Hand tracking' },
        { id: 'kasa', icon: <Lightbulb size={22} />, isActive: showKasaWindow, accent: 'yellow', onClick: onToggleKasa, title: 'Smart devices' },
        { id: 'printer', icon: <Printer size={22} />, isActive: showPrinterWindow, accent: 'green', onClick: onTogglePrinter, title: '3D printers' },
        { id: 'cad', icon: <Box size={22} />, isActive: showCadWindow, accent: 'cyan', onClick: onToggleCad, title: 'CAD agent' },
        { id: 'screen', icon: <Monitor size={22} />, isActive: isScreenMode, accent: 'emerald', onClick: onToggleScreenMode, title: 'Screen mode' },
        { id: 'documents', icon: <BookOpen size={22} />, isActive: false, accent: 'violet', onClick: onToggleDocuments, title: 'Documents' },
    ];

    return (
        <div
            id="tools"
            onMouseDown={onMouseDown}
            className="absolute flex flex-col items-center gap-3 pointer-events-auto"
            style={{
                left: position.x,
                top: position.y,
                transform: 'translate(-50%, -50%)',
            }}
        >
            <AnimatePresence>
                {isOpen && (
                    <motion.div
                        key="tools-row"
                        initial={{ opacity: 0, y: 20 }}
                        animate={{
                            opacity: 1,
                            y: 0,
                            transition: { staggerChildren: 0.03, type: 'spring', stiffness: 300, damping: 24 },
                        }}
                        exit={{ opacity: 0, y: 10, transition: { duration: 0.15 } }}
                        className="flex flex-wrap justify-center gap-3 max-w-[640px]"
                    >
                        {tools.map((tool) => (
                            <motion.div
                                key={tool.id}
                                initial={{ opacity: 0, y: 10 }}
                                animate={{ opacity: 1, y: 0 }}
                                exit={{ opacity: 0 }}
                            >
                                <GlassButton
                                    icon={tool.icon}
                                    isActive={tool.isActive}
                                    accentColor={tool.accent}
                                    disabled={tool.disabled}
                                    onClick={tool.onClick}
                                    title={tool.title}
                                />
                            </motion.div>
                        ))}
                    </motion.div>
                )}
            </AnimatePresence>

            <GlassButton
                icon={<HamburgerIcon isOpen={isOpen} />}
                isActive={isOpen}
                accentColor="blue"
                onClick={() => setIsOpen(!isOpen)}
                title={isOpen ? 'Fermer' : 'Ouvrir le menu'}
                ariaLabel="Menu"
                size="lg"
            />
        </div>
    );
};

export default HamburgerMenu;

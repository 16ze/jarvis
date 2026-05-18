import React from 'react';
import { motion } from 'framer-motion';

const ACCENT_PRESETS = {
    blue: {
        idleText: 'text-blue-600',
        activeBg: 'bg-blue-500',
        activeText: 'text-white',
        glow: 'shadow-[0_8px_32px_rgba(59,130,246,0.18)]',
        glowHover: 'shadow-[0_12px_40px_rgba(59,130,246,0.30)]',
        border: 'border-blue-400/40',
        borderActive: 'border-blue-300/80',
    },
    green: {
        idleText: 'text-green-600',
        activeBg: 'bg-green-500',
        activeText: 'text-white',
        glow: 'shadow-[0_8px_32px_rgba(34,197,94,0.18)]',
        glowHover: 'shadow-[0_12px_40px_rgba(34,197,94,0.30)]',
        border: 'border-green-400/40',
        borderActive: 'border-green-300/80',
    },
    red: {
        idleText: 'text-red-600',
        activeBg: 'bg-red-500',
        activeText: 'text-white',
        glow: 'shadow-[0_8px_32px_rgba(239,68,68,0.18)]',
        glowHover: 'shadow-[0_12px_40px_rgba(239,68,68,0.30)]',
        border: 'border-red-400/40',
        borderActive: 'border-red-300/80',
    },
    purple: {
        idleText: 'text-purple-600',
        activeBg: 'bg-purple-500',
        activeText: 'text-white',
        glow: 'shadow-[0_8px_32px_rgba(168,85,247,0.18)]',
        glowHover: 'shadow-[0_12px_40px_rgba(168,85,247,0.30)]',
        border: 'border-purple-400/40',
        borderActive: 'border-purple-300/80',
    },
    orange: {
        idleText: 'text-orange-600',
        activeBg: 'bg-orange-500',
        activeText: 'text-white',
        glow: 'shadow-[0_8px_32px_rgba(249,115,22,0.18)]',
        glowHover: 'shadow-[0_12px_40px_rgba(249,115,22,0.30)]',
        border: 'border-orange-400/40',
        borderActive: 'border-orange-300/80',
    },
    yellow: {
        idleText: 'text-yellow-600',
        activeBg: 'bg-yellow-400',
        activeText: 'text-slate-900',
        glow: 'shadow-[0_8px_32px_rgba(253,224,71,0.25)]',
        glowHover: 'shadow-[0_12px_40px_rgba(253,224,71,0.40)]',
        border: 'border-yellow-400/50',
        borderActive: 'border-yellow-300/90',
    },
    cyan: {
        idleText: 'text-cyan-600',
        activeBg: 'bg-cyan-500',
        activeText: 'text-white',
        glow: 'shadow-[0_8px_32px_rgba(34,211,238,0.18)]',
        glowHover: 'shadow-[0_12px_40px_rgba(34,211,238,0.30)]',
        border: 'border-cyan-400/40',
        borderActive: 'border-cyan-300/80',
    },
    emerald: {
        idleText: 'text-emerald-600',
        activeBg: 'bg-emerald-500',
        activeText: 'text-white',
        glow: 'shadow-[0_8px_32px_rgba(52,211,153,0.18)]',
        glowHover: 'shadow-[0_12px_40px_rgba(52,211,153,0.30)]',
        border: 'border-emerald-400/40',
        borderActive: 'border-emerald-300/80',
    },
    violet: {
        idleText: 'text-violet-600',
        activeBg: 'bg-violet-500',
        activeText: 'text-white',
        glow: 'shadow-[0_8px_32px_rgba(139,92,246,0.18)]',
        glowHover: 'shadow-[0_12px_40px_rgba(139,92,246,0.30)]',
        border: 'border-violet-400/40',
        borderActive: 'border-violet-300/80',
    },
};

const GlassButton = ({
    icon,
    isActive = false,
    accentColor = 'blue',
    disabled = false,
    onClick,
    title,
    ariaLabel,
    size = 'md',
}) => {
    const preset = ACCENT_PRESETS[accentColor] || ACCENT_PRESETS.blue;
    const padding = size === 'lg' ? 'p-4' : 'p-3';

    const baseClasses = [
        'relative rounded-full overflow-hidden',
        'transition-all duration-200',
        padding,
        'border',
        isActive ? preset.borderActive : preset.border,
        'backdrop-blur-xl backdrop-saturate-150',
        isActive ? preset.activeBg : 'bg-gradient-to-br from-white/70 to-white/40',
        isActive ? preset.activeText : preset.idleText,
        'shadow-[inset_0_1px_0_rgba(255,255,255,0.8)]',
        isActive ? preset.glowHover : preset.glow,
        disabled ? 'opacity-40 pointer-events-none' : 'cursor-pointer',
    ].join(' ');

    return (
        <motion.button
            type="button"
            onClick={disabled ? undefined : onClick}
            disabled={disabled}
            title={title}
            aria-label={ariaLabel || title}
            whileHover={disabled ? {} : { y: -2 }}
            whileTap={disabled ? {} : { y: 0, scale: 0.96 }}
            transition={{ type: 'spring', stiffness: 400, damping: 25 }}
            className={baseClasses}
        >
            <span
                className="absolute inset-0 pointer-events-none rounded-full glass-reflet"
                aria-hidden="true"
            />
            <span className="relative z-10 flex items-center justify-center">
                {icon}
            </span>
        </motion.button>
    );
};

export default GlassButton;

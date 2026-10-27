import React, { useEffect, useState } from 'react';

// Visage robot expressif d'Ada (inspiré d'EMO/LOOI, « volé » à PIO).
// Yeux cyan glow qui clignent, suivent le curseur, et changent d'humeur selon
// l'état réel d'Ada : au repos, elle parle, elle agit (pilotage PC).
const MOODS = {
    idle:     { color: '#22d3ee', eyeH: 1.0, glow: 3 },
    speaking: { color: '#38dcf0', eyeH: 1.0, glow: 6 },
    acting:   { color: '#fbbf24', eyeH: 0.55, glow: 7 }, // « sharingan » ambré quand elle agit
};

function Eye({ cx, cy, color, scaleY, dx, dy }) {
    // Œil = capsule arrondie lumineuse, décalée selon le regard, écrasée au clignement.
    return (
        <g transform={`translate(${cx + dx} ${cy + dy})`}>
            <g transform={`scale(1 ${scaleY})`}>
                <rect x="-4.6" y="-6" width="9.2" height="12" rx="4.6" fill={color} />
                <circle cx="-1.4" cy="-2.6" r="1.5" fill="#eafcff" opacity="0.9" />
            </g>
        </g>
    );
}

export default function Eyes({ mood = 'idle', look = { x: 0, y: 0 }, size = 40 }) {
    const [blink, setBlink] = useState(false);

    useEffect(() => {
        let t;
        const schedule = () => {
            t = setTimeout(() => {
                setBlink(true);
                setTimeout(() => setBlink(false), 110);
                schedule();
            }, 2600 + Math.random() * 3200);
        };
        schedule();
        return () => clearTimeout(t);
    }, []);

    const m = MOODS[mood] || MOODS.idle;
    const dx = Math.max(-1, Math.min(1, look.x)) * 2.6;
    const dy = Math.max(-1, Math.min(1, look.y)) * 2.2;
    const scaleY = blink ? 0.08 : m.eyeH;

    return (
        <svg
            width={size}
            height={size}
            viewBox="0 0 48 48"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            style={{ filter: `drop-shadow(0 0 ${m.glow}px ${m.color})`, transition: 'filter 0.25s ease' }}
            aria-hidden="true"
        >
            {/* antenne */}
            <line x1="24" y1="5" x2="24" y2="10" stroke={m.color} strokeWidth="2.2" strokeLinecap="round" />
            <circle cx="24" cy="4" r="2.2" fill={m.color} />
            {/* tête */}
            <rect x="9" y="11" width="30" height="24" rx="8" fill="rgba(8,20,24,0.55)" stroke={m.color} strokeWidth="2" opacity="0.85" />
            {/* yeux */}
            <Eye cx={18.5} cy={23} color={m.color} scaleY={scaleY} dx={dx} dy={dy} />
            <Eye cx={29.5} cy={23} color={m.color} scaleY={scaleY} dx={dx} dy={dy} />
            {/* bouche : barre qui pulse quand elle parle, sourire discret sinon */}
            {mood === 'speaking' ? (
                <rect x="20" y="29.5" width="8" height="2.4" rx="1.2" fill={m.color}>
                    <animate attributeName="width" values="4;10;6;9;5" dur="0.7s" repeatCount="indefinite" />
                    <animate attributeName="x" values="22;19;21;19.5;21.5" dur="0.7s" repeatCount="indefinite" />
                </rect>
            ) : (
                <path d="M20 30 q4 2.4 8 0" stroke={m.color} strokeWidth="1.8" strokeLinecap="round" fill="none" opacity="0.7" />
            )}
        </svg>
    );
}

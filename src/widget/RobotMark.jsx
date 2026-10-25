import React from 'react';

// Monogramme Jarvis — mini-robot, lisible même à petite taille.
export default function RobotMark({ size = 40 }) {
    return (
        <svg
            width={size}
            height={size}
            viewBox="0 0 48 48"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            aria-hidden="true"
        >
            {/* antenne */}
            <line x1="24" y1="5" x2="24" y2="11" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
            <circle cx="24" cy="4" r="2.4" fill="currentColor" />
            {/* tête */}
            <rect
                x="9" y="11" width="30" height="24" rx="8"
                fill="rgba(8,20,24,0.55)"
                stroke="currentColor" strokeWidth="2.4"
            />
            {/* yeux */}
            <circle cx="18.5" cy="23" r="3.1" fill="currentColor" />
            <circle cx="29.5" cy="23" r="3.1" fill="currentColor" />
            {/* bouche / barre d'onde */}
            <line x1="18" y1="30" x2="30" y2="30" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" opacity="0.7" />
            {/* oreilles */}
            <rect x="5.5" y="19" width="3.5" height="8" rx="1.75" fill="currentColor" opacity="0.8" />
            <rect x="39" y="19" width="3.5" height="8" rx="1.75" fill="currentColor" opacity="0.8" />
            {/* col */}
            <line x1="24" y1="35" x2="24" y2="39" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
            <path d="M16 43c0-3 3.6-5 8-5s8 2 8 5" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" fill="none" />
        </svg>
    );
}

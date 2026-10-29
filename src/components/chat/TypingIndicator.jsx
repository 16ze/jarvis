import React from 'react';
import { motion, useReducedMotion } from 'framer-motion';

/**
 * Trois points animés (pulsation douce) dans une bulle cohérente avec les
 * bulles d'Ada. Respecte prefers-reduced-motion (points statiques et atténués
 * si l'utilisateur a demandé moins d'animations).
 */
export default function TypingIndicator() {
    const reduceMotion = useReducedMotion();

    const dots = [0, 1, 2];

    return (
        <div
            className="inline-flex items-center gap-1.5 rounded-ada-lg border border-line bg-surface px-3.5 py-2.5 shadow-ada-sm"
            role="status"
            aria-label="Ada est en train d'écrire"
        >
            {dots.map((i) =>
                reduceMotion ? (
                    <span
                        key={i}
                        className="block h-1.5 w-1.5 rounded-full bg-muted/70"
                    />
                ) : (
                    <motion.span
                        key={i}
                        className="block h-1.5 w-1.5 rounded-full bg-accent"
                        initial={{ opacity: 0.3, scale: 0.8 }}
                        animate={{ opacity: [0.3, 1, 0.3], scale: [0.8, 1, 0.8] }}
                        transition={{
                            duration: 1.2,
                            ease: 'easeInOut',
                            repeat: Infinity,
                            delay: i * 0.18,
                        }}
                    />
                )
            )}
        </div>
    );
}

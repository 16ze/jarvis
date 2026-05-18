// Variantes Framer Motion partagées par toutes les fenêtres modales
// pour cohérence visuelle de l'ouverture/fermeture.
//
// Origine de la transformation : 'center bottom' — la fenêtre "jaillit"
// depuis la zone du hamburger menu situé au centre-bas.

export const windowVariants = {
    initial: { scale: 0.6, opacity: 0 },
    animate: {
        scale: 1,
        opacity: 1,
        transition: { type: 'spring', stiffness: 280, damping: 24 },
    },
    exit: {
        scale: 0.85,
        opacity: 0,
        transition: { duration: 0.18, ease: 'easeIn' },
    },
};

// Variante allégée pour le mode electron-performance — fade simple.
export const reduceMotionWindowVariants = {
    initial: { opacity: 0 },
    animate: { opacity: 1, transition: { duration: 0.15 } },
    exit: { opacity: 0, transition: { duration: 0.1 } },
};

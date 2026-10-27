import React, { useEffect, useMemo, useRef, useState } from 'react';

/*
 * Face.jsx — le vrai visage d'Ada, piloté par son brain.
 *
 * Visage « écran » façon EMO/companion : une plaque sombre, des yeux / sourcils /
 * bouche lumineux qui se DÉFORMENT selon l'émotion. L'émotion n'est pas inventée :
 * elle vient de get_brain().get_affect_snapshot() (hormones -> mood), diffusée par
 * le backend sur le socket `ada_affect`.
 *
 * Props :
 *   affect  : { mood, cortisol, dopamine, oxytocine, serotonine,
 *               self_confidence, mental_load, momentum } | null
 *   talking : bool  — Ada parle (bouche qui s'anime), indépendant de l'humeur
 *   acting  : bool  — Ada pilote l'écran (regard focalisé ambré)
 *   look    : {x,y} — -1..1, les yeux suivent le curseur
 *   size    : px
 *
 * SVG pur, viewBox 100x100, 0 dépendance. Les déformations passent par des
 * transforms CSS (transition douce) ; les changements d'humeur sont espacés donc
 * le coût reste négligeable (pas de boucle rAF).
 */

// ── Familles d'émotion : chaque mood du brain tombe dans une famille ──────────
const MOOD_FAMILY = {
    // Joie
    Euphorie: 'joy', Jubilation: 'joy', Enthousiasme: 'joy', Joie: 'joy',
    Gaieté: 'joy', Optimisme: 'joy',
    // Amour / attachement
    Passion: 'love', Tendresse: 'love', Chaleureux: 'love', Empathie: 'love',
    Sympathie: 'love',
    // Fierté / assertivité
    Fierté: 'pride', Assertif: 'pride',
    // Curiosité
    Curieux: 'curious', Intérêt: 'curious',
    // Sérénité
    Sérénité: 'serene',
    // Peur
    Panique: 'fear', Terreur: 'fear', Anxiété: 'fear', Inquiétude: 'fear',
    'Fight/Flight': 'fear', Défensif: 'fear',
    // Colère
    Rage: 'anger', Indignation: 'anger', Irritation: 'anger', Agacement: 'anger',
    // Dégoût
    Mépris: 'disgust', Dédain: 'disgust',
    // Tristesse
    Détresse: 'sad', Désespoir: 'sad', Tristesse: 'sad', Chagrin: 'sad',
    Mélancolie: 'sad', Nostalgie: 'sad',
    // Honte
    Honte: 'shame', Culpabilité: 'shame', Humilité: 'shame',
    // Ennui / apathie
    Apathie: 'bored', Spleen: 'bored',
    // Fatigue
    Léthargique: 'tired', Fatigué: 'tired',
    // Sarcasme
    Sarcastique: 'sarcastic',
    // Rupture (débordé)
    Rupture: 'overwhelmed',
};

// Paramètres d'expression par famille.
//  lidTop/lidBottom : fermeture de paupière (0 ouvert → 1 fermé)
//  browA            : inclinaison des sourcils (+ = colère, - = tristesse/peur)
//  browY            : décalage vertical des sourcils (- = levés)
//  eyeScale         : taille des yeux (surprise/peur > 1)
//  mouthCurve       : -1 (∩ triste) → +1 (∪ sourire)
//  mouthOpen        : 0..1, mouthW : largeur
//  tint             : couleur lumineuse ; asym : sourcil droit levé (dubitatif)
//  tear/sweat/shake : décorations
const FAMILIES = {
    neutral:   { lidTop: .08, lidBottom: 0,  browA: 0,  browY: 0,  eyeScale: 1,    mouthCurve: .12, mouthOpen: 0,   mouthW: 1,   tint: '#22d3ee' },
    joy:       { lidTop: 0,   lidBottom: .42, browA: -4, browY: -3, eyeScale: 1,    mouthCurve: .9,  mouthOpen: .25, mouthW: 1.1, tint: '#2ee6c6' },
    love:      { lidTop: .12, lidBottom: .3, browA: -6, browY: -2, eyeScale: 1,    mouthCurve: .7,  mouthOpen: 0,   mouthW: 1,   tint: '#ff86cf' },
    pride:     { lidTop: .1,  lidBottom: .12, browA: -8, browY: -3, eyeScale: 1,    mouthCurve: .55, mouthOpen: 0,   mouthW: 1,   tint: '#49d0ff' },
    curious:   { lidTop: 0,   lidBottom: 0,  browA: -3, browY: -6, eyeScale: 1.08, mouthCurve: .2,  mouthOpen: .1,  mouthW: .9,  tint: '#5ad1ff', asym: true },
    serene:    { lidTop: .22, lidBottom: .14, browA: -2, browY: -1, eyeScale: .98,  mouthCurve: .45, mouthOpen: 0,   mouthW: 1,   tint: '#39d7bd' },
    fear:      { lidTop: 0,   lidBottom: 0,  browA: -10, browY: -8, eyeScale: 1.22, mouthCurve: -.3, mouthOpen: .45, mouthW: .85, tint: '#b98cff', sweat: true, shake: .6 },
    anger:     { lidTop: .2,  lidBottom: .1, browA: 16, browY: 2,  eyeScale: 1,    mouthCurve: -.6, mouthOpen: .1,  mouthW: 1,   tint: '#ff5a46', shake: .25 },
    disgust:   { lidTop: .28, lidBottom: .12, browA: 8,  browY: 1,  eyeScale: .95,  mouthCurve: -.4, mouthOpen: 0,   mouthW: .85, tint: '#c3a24b', asym: true },
    sad:       { lidTop: .32, lidBottom: 0,  browA: -14, browY: 3,  eyeScale: .98,  mouthCurve: -.7, mouthOpen: 0,   mouthW: .9,  tint: '#5aa6ff', tear: true },
    shame:     { lidTop: .4,  lidBottom: 0,  browA: -8, browY: 3,  eyeScale: .9,   mouthCurve: -.3, mouthOpen: 0,   mouthW: .8,  tint: '#6f88c0', lookDown: true },
    bored:     { lidTop: .5,  lidBottom: 0,  browA: 2,  browY: 2,  eyeScale: .95,  mouthCurve: -.1, mouthOpen: 0,   mouthW: .9,  tint: '#788690' },
    tired:     { lidTop: .62, lidBottom: .05, browA: -3, browY: 3,  eyeScale: .92,  mouthCurve: -.15, mouthOpen: .15, mouthW: .9, tint: '#6b7a85', droop: true },
    sarcastic: { lidTop: .34, lidBottom: .08, browA: 4,  browY: -2, eyeScale: .98,  mouthCurve: .3,  mouthOpen: 0,   mouthW: 1,   tint: '#7fd4c0', asym: true, smirk: true },
    overwhelmed:{ lidTop: 0,  lidBottom: 0,  browA: -6, browY: -6, eyeScale: 1.1,  mouthCurve: -.5, mouthOpen: .6,  mouthW: .8,  tint: '#ff4d6d', sweat: true, shake: 1 },
    focus:     { lidTop: .34, lidBottom: .22, browA: 6,  browY: 0,  eyeScale: .96,  mouthCurve: 0,   mouthOpen: 0,   mouthW: .9,  tint: '#fbbf24' }, // pilotage PC
};

const clamp = (v, lo = 0, hi = 1) => Math.max(lo, Math.min(hi, v));

function familyFor(affect, acting) {
    if (acting) return 'focus';
    if (!affect) return 'neutral';
    const fam = MOOD_FAMILY[affect.mood];
    if (fam) return fam;
    // Repli : si le mood est inconnu, on déduit la famille des hormones.
    const d = affect.dopamine ?? 0, c = affect.cortisol ?? 0;
    const s = affect.serotonine ?? 0, o = affect.oxytocine ?? 0;
    if (c > 0.6) return 'fear';
    if (o > 0.55 && d > 0.4) return 'love';
    if (d > 0.5 && s > 0.4) return 'joy';
    if (s < 0.3 && d < 0.3) return 'sad';
    if (d > 0.45) return 'curious';
    return 'neutral';
}

export default function Face({
    affect = null, talking = false, acting = false, listening = false,
    look = { x: 0, y: 0 }, size = 120, followCursor = false, micRef = null, speakRef = null,
}) {
    const [blink, setBlink] = useState(false);
    const [sacc, setSacc] = useState({ x: 0, y: 0 }); // micro-saccades oculaires
    const [curLook, setCurLook] = useState({ x: 0, y: 0 }); // suivi curseur interne
    const [micHot, setMicHot] = useState(false); // Bryan parle au micro
    const [aiHot, setAiHot] = useState(false); // Ada émet du son (elle parle)
    const svgRef = useRef(null);
    const uid = useRef('f' + Math.random().toString(36).slice(2, 8)).current;

    // Écoute : le visage est attentif tant qu'une émotion forte (pilotage) ne prime pas.
    const isListening = (listening || micHot) && !acting;
    const fam = familyFor(affect, acting);
    const base = FAMILIES[fam] || FAMILIES.neutral;
    const E = isListening
        ? { ...base, browY: (base.browY || 0) - 2.5, eyeScale: (base.eyeScale || 1) * 1.06 }
        : base;

    // Éveil (arousal) : dilate les yeux, accélère clignement & respiration.
    const arousal = affect
        ? clamp((affect.cortisol ?? 0) * 0.6 + (affect.dopamine ?? 0) * 0.5 + (affect.mental_load ?? 0) * 0.2)
        : 0.25;

    // Clignement périodique (plus fréquent si éveillé).
    useEffect(() => {
        let t;
        const loop = () => {
            const base = 4200 - arousal * 2200; // 2s (éveillé) → 4.2s (calme)
            t = setTimeout(() => {
                setBlink(true);
                setTimeout(() => setBlink(false), 95);
                loop();
            }, base + Math.random() * 1800);
        };
        loop();
        return () => clearTimeout(t);
    }, [arousal]);

    // Micro-saccades : le regard n'est jamais parfaitement fixe (vivant).
    useEffect(() => {
        const id = setInterval(() => {
            setSacc({ x: (Math.random() - 0.5) * 1.6, y: (Math.random() - 0.5) * 1.2 });
        }, 1400 + Math.random() * 1200);
        return () => clearInterval(id);
    }, []);

    // Suivi du curseur : les yeux te suivent à l'écran (relatif au centre du visage).
    useEffect(() => {
        if (!followCursor) return;
        let raf = 0;
        const onMove = (e) => {
            if (raf) return;
            raf = requestAnimationFrame(() => {
                raf = 0;
                const el = svgRef.current;
                if (!el) return;
                const r = el.getBoundingClientRect();
                const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
                setCurLook({ x: clamp((e.clientX - cx) / 240, -1, 1), y: clamp((e.clientY - cy) / 240, -1, 1) });
            });
        };
        window.addEventListener('mousemove', onMove);
        return () => { window.removeEventListener('mousemove', onMove); if (raf) cancelAnimationFrame(raf); };
    }, [followCursor]);

    // Détection de parole micro (humeur « écoute »), via l'amplitude du flux micro.
    useEffect(() => {
        if (!micRef) return;
        let lastHot = 0;
        const id = setInterval(() => {
            const arr = micRef.current;
            if (!arr || !arr.length) return;
            let s = 0;
            for (let i = 0; i < arr.length; i++) s += arr[i];
            const amp = s / arr.length / 255;
            const now = Date.now();
            if (amp > 0.08) { lastHot = now; setMicHot(true); }
            else if (now - lastHot > 500) setMicHot(false);
        }, 150);
        return () => clearInterval(id);
    }, [micRef]);

    // Détection de parole d'Ada via l'amplitude audio réelle (la transcription de
    // sa voix est désactivée) → la bouche s'anime quand elle parle vraiment.
    useEffect(() => {
        if (!speakRef) return;
        let lastHot = 0;
        const id = setInterval(() => {
            const arr = speakRef.current;
            if (!arr || !arr.length) return;
            let s = 0;
            for (let i = 0; i < arr.length; i++) s += arr[i];
            const amp = s / arr.length / 255;
            const now = Date.now();
            if (amp > 0.05) { lastHot = now; setAiHot(true); }
            else if (now - lastHot > 350) setAiHot(false);
        }, 120);
        return () => clearInterval(id);
    }, [speakRef]);

    const tint = E.tint;
    const screen = 'rgba(7,17,22,0.92)'; // couleur de la plaque / des paupières

    // Décalage du regard : curseur (externe ou suivi interne) + saccade + baissé si honte.
    const effLook = followCursor ? curLook : (look || { x: 0, y: 0 });
    const gx = clamp((effLook.x || 0), -1, 1) * 4 + sacc.x;
    const gy = clamp((effLook.y || 0), -1, 1) * 3 + sacc.y + (E.lookDown ? 3 : 0);

    const lidTop = blink ? 1 : E.lidTop;
    const eyeRy = 13 * (E.eyeScale || 1);
    const eyeRx = 10.5 * (E.eyeScale || 1);

    // Sourcils : point d'ancrage = extrémité interne ; rotation = inclinaison.
    // Gauche et droite sont miroir. asym -> le sourcil droit se lève (dubitatif).
    const browLy = 28 + (E.browY || 0);
    const browRy = 28 + (E.browY || 0) - (E.asym ? 5 : 0);
    const browLrot = E.browA;        // gauche
    const browRrot = -E.browA - (E.asym ? 6 : 0); // droite (miroir)

    // Bouche : quadratique. curve>0 => ∪ sourire (milieu bas), <0 => ∩.
    const mW = 15 * (E.mouthW || 1);
    const mx1 = 50 - mW, mx2 = 50 + mW;
    const ctrlY = 72 + (E.mouthCurve || 0) * 12 + (E.smirk ? 0 : 0);
    const mouthPath = E.smirk
        ? `M ${mx1} 73 Q 50 ${72 + 6} ${mx2} 69` // sourire en coin
        : `M ${mx1} 72 Q 50 ${ctrlY} ${mx2} 72`;
    const isTalking = talking || aiHot;
    const mouthOpen = isTalking ? 0.55 : (E.mouthOpen || 0);

    const anims = useMemo(() => `
      @keyframes ${uid}-breathe { 0%,100%{transform:translateY(0) scale(1)} 50%{transform:translateY(-1px) scale(1.012)} }
      @keyframes ${uid}-shake   { 0%,100%{transform:translate(0,0)} 25%{transform:translate(0.7px,-0.4px)} 75%{transform:translate(-0.7px,0.4px)} }
      @keyframes ${uid}-talk    { 0%,100%{transform:scaleY(0.25)} 50%{transform:scaleY(1)} }
      @keyframes ${uid}-tear    { 0%{opacity:0;transform:translateY(0)} 20%{opacity:.9} 100%{opacity:0;transform:translateY(10px)} }
      @keyframes ${uid}-ring    { 0%{opacity:.5;transform:scale(1)} 70%{opacity:0;transform:scale(1.14)} 100%{opacity:0} }
    `, [uid]);

    const breatheSpeed = (3.6 - arousal * 1.8).toFixed(2);
    const headStyle = {
        transformOrigin: '50px 55px',
        animation: `${uid}-breathe ${breatheSpeed}s ease-in-out infinite${E.shake ? `, ${uid}-shake ${(0.18 / (E.shake)).toFixed(2)}s linear infinite` : ''}`,
    };

    return (
        <svg ref={svgRef} width={size} height={size} viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"
             style={{
                 display: 'block',
                 filter: `drop-shadow(0 0 ${6 + arousal * 6}px ${tint}55)`,
                 transform: isListening ? 'rotate(3deg)' : 'none',
                 transition: 'filter .4s ease, transform .4s ease',
             }}>
            <style>{anims}</style>

            {/* Anneau d'écoute : pulse quand Ada t'entend parler */}
            {isListening && (
                <rect x="6" y="12" width="88" height="76" rx="24" fill="none" stroke={tint} strokeWidth="1.4"
                      style={{ transformOrigin: '50px 50px', animation: `${uid}-ring 1.3s ease-out infinite` }} />
            )}

            <g style={headStyle}>
                {/* Plaque / écran */}
                <rect x="10" y="16" width="80" height="68" rx="20" fill={screen}
                      stroke={tint} strokeWidth="1.6" style={{ transition: 'stroke .5s ease' }} opacity="0.96" />

                {/* Antenne */}
                <line x1="50" y1="8" x2="50" y2="15" stroke={tint} strokeWidth="2.4" strokeLinecap="round" style={{ transition: 'stroke .5s ease' }} />
                <circle cx="50" cy="6.5" r="2.6" fill={tint} style={{ transition: 'fill .5s ease' }} />

                {/* Sourcils */}
                <g style={{ transition: 'transform .35s ease' }} transform={`translate(0 ${browLy - 28})`}>
                    <line x1="23" y1="28" x2="41" y2="28" stroke={tint} strokeWidth="3" strokeLinecap="round"
                          style={{ transformOrigin: '41px 28px', transform: `rotate(${browLrot}deg)`, transition: 'transform .35s ease, stroke .5s ease' }} />
                </g>
                <g style={{ transition: 'transform .35s ease' }} transform={`translate(0 ${browRy - 28})`}>
                    <line x1="59" y1="28" x2="77" y2="28" stroke={tint} strokeWidth="3" strokeLinecap="round"
                          style={{ transformOrigin: '59px 28px', transform: `rotate(${browRrot}deg)`, transition: 'transform .35s ease, stroke .5s ease' }} />
                </g>

                {/* Yeux (bougent avec le regard) */}
                <g transform={`translate(${gx} ${gy})`} style={{ transition: 'transform .18s ease-out' }}>
                    {[34, 66].map((cx) => (
                        <g key={cx}>
                            {/* globe lumineux */}
                            <ellipse cx={cx} cy="50" rx={eyeRx} ry={eyeRy} fill={tint}
                                     style={{ transition: 'rx .4s ease, ry .4s ease, fill .5s ease' }} />
                            <circle cx={cx - 3} cy="45" r="2.3" fill="#eafcff" opacity="0.92" />
                            {/* paupière haute (clignement + mi-clos) */}
                            <rect x={cx - eyeRx - 1} y={50 - eyeRy - 1} width={eyeRx * 2 + 2} height={eyeRy * 2 + 2}
                                  fill={screen}
                                  style={{ transformOrigin: `${cx}px ${50 - eyeRy}px`, transform: `scaleY(${lidTop})`, transition: 'transform .09s ease' }} />
                            {/* paupière basse (sourire des yeux) */}
                            <rect x={cx - eyeRx - 1} y="50" width={eyeRx * 2 + 2} height={eyeRy + 2}
                                  fill={screen}
                                  style={{ transformOrigin: `${cx}px ${50 + eyeRy}px`, transform: `scaleY(${E.lidBottom || 0})`, transition: 'transform .3s ease' }} />
                        </g>
                    ))}
                </g>

                {/* Larme (tristesse) */}
                {E.tear && (
                    <path d="M31 60 q-2 4 0 6 q2 -2 0 -6" fill="#8ecbff"
                          style={{ animation: `${uid}-tear 2.8s ease-in-out infinite` }} />
                )}
                {/* Goutte de sueur (peur/stress) */}
                {E.sweat && (
                    <path d="M76 36 q-2 4 0 6 q2 -2 0 -6" fill="#bfe6ff" opacity="0.8"
                          style={{ animation: `${uid}-tear 2.2s ease-in-out infinite` }} />
                )}

                {/* Bouche */}
                {mouthOpen > 0.02 ? (
                    <ellipse cx="50" cy="72" rx={mW * 0.7} ry={6 * mouthOpen + 1.5} fill={tint}
                             style={{
                                 transformOrigin: '50px 72px', transition: 'fill .5s ease',
                                 animation: isTalking ? `${uid}-talk .32s ease-in-out infinite` : 'none',
                             }} />
                ) : (
                    <path d={mouthPath} fill="none" stroke={tint} strokeWidth="3" strokeLinecap="round"
                          style={{ transition: 'd .35s ease, stroke .5s ease' }} />
                )}
            </g>
        </svg>
    );
}

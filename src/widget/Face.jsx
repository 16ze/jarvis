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

// SIGNATURES de forme par émotion (Ekman) : des DELTAS appliqués par-dessus une
// base continue, et dosés par une intensité k (jamais binaire). C'est ce qui
// distingue deux émotions de même valence (peur vs colère vs dégoût).
//  browA +  = sourcils abaissés/rapprochés (colère) ; -  = relevés (peur) / obliques (tristesse)
//  mouthBoost = sourire en plus ; mouthDown = bouche descendue ; mouthOpenAdd = bouche ouverte
const SIG = {
    joy:        { browA: -3, browY: -2, lidBottom: 0.38, mouthBoost: 0.3,  tint: '#4fc3a8' },
    love:       { browA: -5, browY: -1, lidTop: 0.12, lidBottom: 0.22, mouthBoost: 0.12, tint: '#ff86cf' },
    pride:      { browA: -6, browY: -3, mouthBoost: 0.08, tint: '#5aa6e0' },
    curious:    { browY: -5, eyeBoost: 0.12, asym: true, mouthBoost: 0.06, tint: '#6cb0e0' },
    serene:     { lidTop: 0.18, lidBottom: 0.12, mouthBoost: 0.12, tint: '#5bc0ac' },
    fear:       { browA: -9, browY: -7, eyeBoost: 0.22, mouthOpenAdd: 0.4, tint: '#b98cff', sweat: true, shake: 0.5 },
    anger:      { browA: 17, browY: 2, lidTop: 0.2, mouthDown: 0.5, tint: '#ff5a46', shake: 0.25 },
    disgust:    { browA: 7, lidTop: 0.22, asym: true, smirk: true, mouthDown: 0.3, tint: '#c3a24b' },
    sad:        { browA: -14, browY: 3, lidTop: 0.22, mouthDown: 0.55, tint: '#5aa6ff', tear: true },
    shame:      { browA: -7, lidTop: 0.3, lookDown: true, mouthDown: 0.25, tint: '#6f88c0' },
    bored:      { browY: 2, lidTop: 0.45, mouthDown: 0.1, tint: '#788690' },
    tired:      { browY: 2, lidTop: 0.55, droop: true, mouthDown: 0.15, tint: '#6b7a85' },
    sarcastic:  { browA: 4, browY: -2, lidTop: 0.3, asym: true, smirk: true, mouthBoost: 0.2, tint: '#7fd4c0' },
    overwhelmed:{ browA: -6, browY: -6, eyeBoost: 0.1, mouthOpenAdd: 0.55, mouthDown: 0.4, tint: '#ff4d6d', sweat: true, shake: 0.9 },
    focus:      { browA: 6, lidTop: 0.32, lidBottom: 0.2, tint: '#fbbf24' }, // pilotage PC
};

const clamp = (v, lo = 0, hi = 1) => Math.max(lo, Math.min(hi, v));

// Interpolation de deux couleurs hex (#rrggbb) — pour fondre vers la teinte de l'émotion.
function mixHex(a, b, t) {
    const pa = parseInt(a.slice(1), 16), pb = parseInt(b.slice(1), 16);
    const ar = pa >> 16, ag = (pa >> 8) & 255, ab = pa & 255;
    const br = pb >> 16, bg = (pb >> 8) & 255, bb = pb & 255;
    const r = Math.round(ar + (br - ar) * t);
    const g = Math.round(ag + (bg - ag) * t);
    const bl = Math.round(ab + (bb - ab) * t);
    return '#' + ((1 << 24) + (r << 16) + (g << 8) + bl).toString(16).slice(1);
}

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
    const [micro, setMicro] = useState({ brow: 0, mouth: 0 }); // micro-variations humaines
    const svgRef = useRef(null);
    const uid = useRef('f' + Math.random().toString(36).slice(2, 8)).current;

    // Écoute : le visage est attentif tant qu'une émotion forte (pilotage) ne prime pas.
    const isListening = (listening || micHot) && !acting;

    // ── MOTEUR D'EXPRESSION CONTINU ──────────────────────────────────────────
    // L'humeur n'est pas un état figé : on lit en continu les hormones du brain et
    // on en dérive des dimensions affectives (valence, éveil, fatigue) qui modèlent
    // le visage en douceur. La famille nommée n'ajoute que sa SIGNATURE de forme,
    // dosée progressivement — jamais un saut binaire. Résultat : variable, humain.
    const H = affect || {};
    const d = H.dopamine ?? 0.28, c = H.cortisol ?? 0.10, o = H.oxytocine ?? 0.30;
    const s = H.serotonine ?? 0.42, ml = H.mental_load ?? 0.16;
    const valence = clamp((d - 0.28) * 1.8 + (s - 0.42) * 1.3 + (o - 0.30) * 1.1 - (c - 0.10) * 2.3, -1, 1);
    const arousal = clamp(c * 0.7 + d * 0.5 + ml * 0.3, 0, 1);
    const fatigue = clamp(ml, 0, 1);

    // Base continue (toujours vivante, varie en douceur avec l'état).
    const E = {
        mouthCurve: valence * 0.7,
        mouthOpen: 0,
        mouthW: 1,
        eyeScale: 1 + (arousal - 0.3) * 0.22,
        lidTop: clamp(0.06 + fatigue * 0.5 - Math.max(0, arousal - 0.5) * 0.4, 0, 0.72),
        lidBottom: valence > 0 ? valence * 0.3 : 0,
        browA: -valence * 2,
        browY: -Math.max(0, arousal - 0.3) * 4 + fatigue * 2,
        tint: '#6e9fd4',
    };

    // Signature de l'émotion nommée, appliquée avec une intensité k progressive.
    const fam = familyFor(affect, acting);
    const sig = SIG[fam];
    if (sig) {
        const k = acting ? 1 : clamp(0.4 + Math.abs(valence) * 0.6 + Math.max(0, arousal - 0.3) * 0.5, 0.35, 1);
        if (sig.browA) E.browA += sig.browA * k;
        if (sig.browY) E.browY += sig.browY * k;
        if (sig.lidTop) E.lidTop = clamp(E.lidTop + sig.lidTop * k, 0, 0.8);
        if (sig.lidBottom) E.lidBottom = clamp(Math.max(E.lidBottom, sig.lidBottom * k), 0, 0.6);
        if (sig.eyeBoost) E.eyeScale += sig.eyeBoost * k;
        if (sig.mouthBoost) E.mouthCurve = clamp(E.mouthCurve + sig.mouthBoost * k, -0.85, 0.98);
        if (sig.mouthDown) E.mouthCurve = clamp(E.mouthCurve - sig.mouthDown * k, -0.85, 0.98);
        if (sig.mouthOpenAdd) E.mouthOpen = clamp(E.mouthOpen + sig.mouthOpenAdd * k, 0, 0.7);
        if (sig.asym && k > 0.5) E.asym = true;
        if (sig.smirk && k > 0.5) E.smirk = true;
        if (sig.droop) E.droop = true;
        if (sig.lookDown) E.lookDown = true;
        if (sig.sweat && k > 0.5) E.sweat = true;
        if (sig.tear && k > 0.55) E.tear = true;
        if (sig.shake) E.shake = sig.shake * k;
        if (sig.tint) E.tint = mixHex('#6e9fd4', sig.tint, clamp(k, 0, 1));
    }

    // Micro-variations humaines : le visage n'est jamais parfaitement immobile.
    E.browY += micro.brow;
    E.mouthCurve = clamp(E.mouthCurve + micro.mouth, -0.9, 0.98);

    // Écoute : visage attentif (yeux un peu plus ouverts, sourcils relevés).
    if (isListening) { E.browY -= 2.5; E.eyeScale *= 1.06; }

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

    // Micro-variations d'expression (marche aléatoire lente) : sourcils et bouche
    // bougent légèrement en permanence → l'humeur paraît vivante, jamais figée.
    useEffect(() => {
        const id = setInterval(() => {
            setMicro((m) => ({
                brow: clamp(m.brow + (Math.random() - 0.5) * 1.1, -1.6, 1.6),
                mouth: clamp(m.mouth + (Math.random() - 0.5) * 0.07, -0.12, 0.12),
            }));
        }, 650 + Math.random() * 500);
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
                 filter: `drop-shadow(0 0 ${3 + arousal * 4}px ${tint}38)`,
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

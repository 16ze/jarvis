import React, { memo, useEffect, useMemo, useRef } from 'react';

const randomGaussian = () => {
    let u = 0;
    let v = 0;
    while (u === 0) u = Math.random();
    while (v === 0) v = Math.random();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
};

const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

// Réglages perceptifs du nuage. Tweake ici sans toucher à la boucle de rendu.
const MOTION = {
    // === Conditionnement de l'intensité audio ===
    // La voix humaine utilise typiquement 5-30% de l'intensité brute. On amplifie
    // puis on compresse pour que toute la plage [0,1] de liveness soit exploitée.
    audioGain: 3.8,      // multiplie l'intensity avant clamp à 1
    audioCurve: 0.55,    // exposant < 1 = boost les petits signaux (sqrt-like)

    // === Lissage liveness ===
    // Attack rapide pour capter les attaques de voix, release lent pour un fade naturel
    // après le hold (quand Ada a vraiment fini sa phrase).
    livenessAttack: 0.30,
    livenessRelease: 0.012,

    // === Détection audio + hold gate ===
    // Seuil bas pour capter les fins de phrases (voix qui s'éteint).
    // Hold = combien de temps on considère qu'Ada parle encore après le dernier signal.
    // 700ms = la queue naturelle d'une phrase TTS + une marge de sécurité.
    audioActiveThreshold: 0.025,
    audioHoldMs: 700,

    // === Plancher de parole ===
    // Tant qu'Ada parle (audio actif OU dans la fenêtre de hold), liveness ne descend
    // jamais sous ce seuil — l'animation reste pleine TOUT LE LONG de la phrase.
    speakingFloor: 0.60,

    // === Respiration globale ===
    breathHzSpeaking: 1.4,    // ≈0.71s/cycle quand voix pleine
    breathHzIdle: 0.20,       // ≈5s/cycle en silence
    breathAmpIdle: 0.008,     // ±0.8% en silence (à peine perceptible)
    breathAmpSpeaking: 0.055, // ±5.5% en parole (clairement visible)

    // === Mouvement par particule ===
    idleMotion: 0.20,         // floor : 20% du mouvement reste actif même en silence
    driftMultiplier: 5.5,     // amplifie p.orbit (base 0.002-0.008 → 0.011-0.044)
    zMotionAmp: 0.05,         // profondeur z (base 0.018)
    jitterPx: 4.8,            // chaos local en pixels (base 1.2 — invisible)
    swirl: 0.45,              // composante secondaire haute-fréquence

    // === Wave radiale ===
    // L'onde voyage en permanence mais lentement au repos, et s'accélère + s'amplifie
    // quand Ada parle. Vitesse interpolée via un phase accumulator pour éviter les sauts.
    waveAmplitudeIdle: 0.022,      // ~9 px en silence — wave discrète mais perceptible
    waveAmplitudeSpeaking: 0.115,  // ~45 px en parole — effet majeur (inchangé)
    waveSpeedIdle: 0.4,            // très lente au repos — un cycle d'onde prend ~16s (méditatif)
    waveSpeedSpeaking: 4.2,        // vraiment vive en parole — un cycle en ~1.5s (vibrant)
    waveFrequency: 5.5,            // longueur d'onde principale (5-6 anneaux visibles)
    // Onde secondaire à fréquence ~φ (nombre d'or) pour casser la périodicité.
    waveSecondaryRatio: 1.7,       // f2 = f1 × 1.7 — non-multiple = pas de répétition visible
    waveSecondaryAmp: 0.45,        // amplitude relative à la wave principale

    // === Densité visuelle perçue ===
    alphaBoost: 1.25,        // alpha final = base * (1 + liveness * alphaBoost) → ×2.25 max
    sizeBoost: 1.10,         // size final  = base * (1 + liveness * sizeBoost)  → ×2.10 max
    idleDensityScale: 0.60,  // alpha multiplié par 0.60 en silence pur → nuage moins dense au repos
};

const Visualizer = ({ audioData, audioDataRef: externalAudioDataRef, isListening, intensity = 0, width = 600, height = 400, reduceMotion = false }) => {
    const canvasRef = useRef(null);
    const particlesRef = useRef([]);

    const audioDataRef = useRef(audioData);
    const intensityRef = useRef(intensity);
    const isListeningRef = useRef(isListening);
    // État lissé en [0,1] qui module toute l'animation. Vit entre les frames pour ne pas
    // redémarrer à 0 quand React re-render — un useState ferait un re-render à 60Hz.
    const livenessRef = useRef(0);
    // Accumulateur de phase wave : intègre dt × vitesse à chaque frame. Permet de changer
    // la vitesse de l'onde sans saut de phase visible (comme un VCO en synthèse audio).
    const wavePhaseRef = useRef(0);
    const lastTimeRef = useRef(0);
    // Timestamp du dernier moment où l'audio a dépassé le seuil. Sert au hold du noise gate :
    // tant que (now - lastAudioTime) < audioHoldMs, on considère qu'Ada parle encore.
    const lastAudioTimeRef = useRef(0);

    const particleCount = useMemo(() => {
        if (reduceMotion) return Math.max(16000, Math.min(24000, Math.round((width * height) / 34)));
        return Math.max(36000, Math.min(56000, Math.round((width * height) / 13)));
    }, [height, reduceMotion, width]);

    useEffect(() => {
        audioDataRef.current = audioData;
        intensityRef.current = intensity;
        isListeningRef.current = isListening;
    }, [audioData, intensity, isListening]);

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;

        const dpr = reduceMotion ? 1 : Math.min(window.devicePixelRatio || 1, 2);
        canvas.width = Math.floor(width * dpr);
        canvas.height = Math.floor(height * dpr);
        canvas.style.width = `${width}px`;
        canvas.style.height = `${height}px`;

        const ctx = canvas.getContext('2d');
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

        const createParticles = () => {
            const points = [];
            for (let i = 0; i < particleCount; i += 1) {
                const layer = Math.random();
                const lobeRoll = Math.random();

                let sigmaX;
                let sigmaY;
                let sigmaZ;
                let alphaBase;
                let sizeBase;

                if (layer < 0.62) {
                    sigmaX = 0.24;
                    sigmaY = 0.31;
                    sigmaZ = 0.22;
                    alphaBase = 0.31;
                    sizeBase = 0.72;
                } else if (layer < 0.90) {
                    sigmaX = 0.39;
                    sigmaY = 0.43;
                    sigmaZ = 0.30;
                    alphaBase = 0.19;
                    sizeBase = 0.56;
                } else {
                    sigmaX = 0.58;
                    sigmaY = 0.58;
                    sigmaZ = 0.42;
                    alphaBase = 0.09;
                    sizeBase = 0.38;
                }

                let lobeX = 0;
                let lobeY = 0;
                if (lobeRoll > 0.72 && lobeRoll <= 0.82) {
                    lobeX = -0.20;
                    lobeY = -0.02;
                } else if (lobeRoll > 0.82 && lobeRoll <= 0.91) {
                    lobeX = 0.22;
                    lobeY = 0.02;
                } else if (lobeRoll > 0.91 && lobeRoll <= 0.965) {
                    lobeX = 0.02;
                    lobeY = -0.18;
                } else if (lobeRoll > 0.965) {
                    lobeX = -0.06;
                    lobeY = 0.20;
                }

                const x = clamp(randomGaussian() * sigmaX + lobeX, -1.18, 1.18);
                const y = clamp(randomGaussian() * sigmaY + lobeY, -1.08, 1.08);
                const z = clamp(randomGaussian() * sigmaZ, -1.0, 1.0);
                const falloff = Math.exp(-((x * x) / 0.85 + (y * y) / 0.62 + (z * z) / 0.82));

                // Pré-calcul wave radiale : distance au centre + vecteur unitaire radial.
                // Évite Math.sqrt/atan2 à chaque frame (économise ~2M ops/sec).
                const dist = Math.sqrt(x * x + y * y) + 0.001;
                const nx = x / dist;
                const ny = y / dist;

                points.push({
                    x,
                    y,
                    z,
                    dist,
                    nx,
                    ny,
                    size: sizeBase + Math.random() * 0.72,
                    alpha: alphaBase * (0.58 + falloff * 1.9) * (0.82 + Math.random() * 0.48),
                    phase: Math.random() * Math.PI * 2,
                    speed: 0.22 + Math.random() * 0.72,
                    orbit: 0.002 + Math.random() * 0.006,
                    hue: 214 + Math.random() * 10,
                });
            }
            particlesRef.current = points;
        };

        createParticles();

        let animationId;
        let lastDraw = 0;

        const getCurrentIntensity = () => {
            if (intensityRef.current !== null && typeof intensityRef.current !== 'undefined') {
                return intensityRef.current;
            }

            const values = externalAudioDataRef?.current || audioDataRef.current || [];
            if (!values.length) return 0;
            return values.reduce((sum, value) => sum + value, 0) / values.length / 255;
        };

        const draw = (timestamp = 0) => {
            animationId = requestAnimationFrame(draw);
            if (reduceMotion && timestamp - lastDraw < 33) return;
            lastDraw = timestamp;

            const w = width;
            const h = height;
            const centerX = w / 2;
            const centerY = h / 2;

            const currentIntensity = getCurrentIntensity();
            const currentIsListening = isListeningRef.current;
            const intensitySafe = clamp(currentIntensity, 0, 1);
            const time = timestamp * 0.001;

            // Conditionnement audio : gain × courbe de compression.
            // pow(x, 0.55) : intensity 0.1 → 0.29, 0.2 → 0.43, 0.4 → 0.62, 0.7 → 0.82.
            // Sans ça, la voix réelle restait coincée à liveness ≈ 0.3 max.
            const audioShaped = Math.pow(
                clamp(intensitySafe * MOTION.audioGain, 0, 1),
                MOTION.audioCurve
            );

            // Noise gate avec hold : on enregistre le timestamp à chaque fois que l'audio
            // dépasse le seuil. audioActive reste vrai pendant audioHoldMs après le dernier
            // signal → l'animation tient jusqu'à la fin réelle de la phrase (queue TTS incluse).
            if (audioShaped > MOTION.audioActiveThreshold) {
                lastAudioTimeRef.current = timestamp;
            }
            const audioActive = (timestamp - lastAudioTimeRef.current) < MOTION.audioHoldMs;
            // `currentIsListening` reste un gate de sécurité (Ada déconnectée/mute → idle).
            const livenessTarget = (currentIsListening && audioActive)
                ? Math.max(audioShaped, MOTION.speakingFloor)
                : 0;
            const livenessK = livenessTarget > livenessRef.current
                ? MOTION.livenessAttack
                : MOTION.livenessRelease;
            livenessRef.current += (livenessTarget - livenessRef.current) * livenessK;
            const liveness = livenessRef.current;

            ctx.clearRect(0, 0, w, h);

            // Le glow central s'intensifie avec liveness — accentue la sensation de "souffle".
            const coreGlow = ctx.createRadialGradient(centerX, centerY, 0, centerX, centerY, Math.min(w, h) * 0.55);
            coreGlow.addColorStop(0, `rgba(37, 99, 235, ${0.28 + liveness * 0.14})`);
            coreGlow.addColorStop(0.34, `rgba(79, 142, 255, ${0.18 + liveness * 0.08})`);
            coreGlow.addColorStop(0.72, 'rgba(147, 197, 253, 0.085)');
            coreGlow.addColorStop(1, 'rgba(147, 197, 253, 0)');
            ctx.fillStyle = coreGlow;
            ctx.fillRect(0, 0, w, h);

            const plumeGlow = ctx.createRadialGradient(centerX - w * 0.13, centerY + h * 0.03, 0, centerX - w * 0.13, centerY + h * 0.03, Math.min(w, h) * 0.42);
            plumeGlow.addColorStop(0, `rgba(96, 165, 250, ${0.09 + liveness * 0.06})`);
            plumeGlow.addColorStop(1, 'rgba(96, 165, 250, 0)');
            ctx.fillStyle = plumeGlow;
            ctx.fillRect(0, 0, w, h);

            ctx.globalCompositeOperation = 'source-over';
            const spreadX = Math.min(w * 0.27, 390) * (1 + liveness * 0.32);
            const spreadY = Math.min(h * 0.39, 285) * (1 + liveness * 0.06);
            // Rotation lente : amplitude modulée par liveness (figée en silence).
            const rotation = reduceMotion ? 0.18 : 0.18 + Math.sin(time * 0.12) * 0.035 * liveness;
            const cos = Math.cos(rotation);
            const sin = Math.sin(rotation);

            // Respiration : lente (≈5s) en silence, rapide (≈0.71s) en parole. Lerp continu.
            // Indépendant de reduceMotion — l'effet est central au design, pas une fioriture.
            const breathHz = MOTION.breathHzIdle + (MOTION.breathHzSpeaking - MOTION.breathHzIdle) * liveness;
            const breathAmp = MOTION.breathAmpIdle + (MOTION.breathAmpSpeaking - MOTION.breathAmpIdle) * liveness;
            const breath = 1 + Math.sin(time * Math.PI * 2 * breathHz) * breathAmp;

            // Amplitude de la wave radiale : idle réduit, speaking max. Lerp via liveness.
            const waveAmp = MOTION.waveAmplitudeIdle
                + (MOTION.waveAmplitudeSpeaking - MOTION.waveAmplitudeIdle) * liveness;

            // Vitesse de wave : lente au repos, rapide en parole. On intègre dt × vitesse
            // dans un accumulateur pour éviter les sauts de phase quand liveness change.
            const waveSpeedNow = MOTION.waveSpeedIdle
                + (MOTION.waveSpeedSpeaking - MOTION.waveSpeedIdle) * liveness;
            const dt = lastTimeRef.current
                ? Math.min((timestamp - lastTimeRef.current) / 1000, 0.1)
                : 0;
            lastTimeRef.current = timestamp;
            wavePhaseRef.current += dt * waveSpeedNow;
            const waveTimePhase = wavePhaseRef.current;
            // Phase de l'onde secondaire — même accumulateur multiplié par le ratio φ.
            const waveTimePhase2 = wavePhaseRef.current * MOTION.waveSecondaryRatio;

            for (const p of particlesRef.current) {
                // Motion floor : même en silence, le mouvement résiduel reste à idleMotion (20%).
                // En parole, on monte progressivement jusqu'à 1. Indépendant de reduceMotion —
                // les particules doivent toujours bouger, c'est l'essence du nuage vivant.
                const motion = MOTION.idleMotion + (1 - MOTION.idleMotion) * liveness;

                const driftSlow = Math.sin(time * p.speed + p.phase);
                const driftFast = Math.sin(time * p.speed * 2.7 + p.phase * 1.3);
                const drift = (driftSlow + driftFast * MOTION.swirl) * p.orbit * MOTION.driftMultiplier * motion;

                // Wave radiale : déplacement le long du vecteur centre→particule.
                // Deux ondes superposées (fréquences en ratio φ) — l'interférence des deux
                // élimine toute périodicité visible et donne un mouvement organique.
                const wavePrimary = Math.sin(p.dist * MOTION.waveFrequency - waveTimePhase);
                const waveSecondary = Math.sin(p.dist * MOTION.waveFrequency * MOTION.waveSecondaryRatio - waveTimePhase2);
                const waveOffset = (wavePrimary + waveSecondary * MOTION.waveSecondaryAmp) * waveAmp;
                const waveX = p.nx * waveOffset;
                const waveY = p.ny * waveOffset;

                const x = p.x + drift + waveX;
                const yWithWave = p.y + waveY;
                const z = p.z + Math.cos(time * p.speed + p.phase) * MOTION.zMotionAmp * motion;
                const rotatedX = x * cos + z * sin;
                const rotatedZ = -x * sin + z * cos;
                const perspective = 1 / (1 + rotatedZ * 0.32);
                const jitterX = (Math.sin(time * 0.7 + p.phase) + Math.sin(time * 2.3 + p.phase * 0.8) * MOTION.swirl) * MOTION.jitterPx * motion;
                const jitterY = (Math.cos(time * 0.64 + p.phase) + Math.cos(time * 2.1 + p.phase * 0.9) * MOTION.swirl) * MOTION.jitterPx * 0.85 * motion;
                const px = centerX + rotatedX * spreadX * perspective * breath + jitterX;
                const py = centerY + yWithWave * spreadY * perspective * breath + jitterY;
                const depthLight = 0.78 + (1 - clamp((rotatedZ + 1) / 2, 0, 1)) * 0.38;
                // Densification asymétrique :
                //   - en silence : alpha multiplié par idleDensityScale (0.60) → nuage moins dense
                //   - en parole  : alpha multiplié par (1 + alphaBoost) → nuage très dense
                // densityScale interpole continûment entre les deux selon liveness.
                const densityScale = MOTION.idleDensityScale
                    + (1 + MOTION.alphaBoost - MOTION.idleDensityScale) * liveness;
                const alpha = clamp(p.alpha * depthLight * densityScale, 0.025, 0.95);
                const size = p.size * perspective * (1 + liveness * MOTION.sizeBoost);

                ctx.fillStyle = `hsla(${p.hue}, 100%, ${55 + liveness * 6}%, ${alpha})`;
                ctx.fillRect(px, py, size, size);
            }

            ctx.globalAlpha = 1;
        };

        draw();
        return () => cancelAnimationFrame(animationId);
    }, [width, height, reduceMotion, externalAudioDataRef, particleCount]);

    return (
        <div className="relative" style={{ width, height }}>
            <canvas
                ref={canvasRef}
                className="block"
                style={{ width: '100%', height: '100%' }}
            />
        </div>
    );
};

export default memo(Visualizer);

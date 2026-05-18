import React, { memo, useEffect, useMemo, useRef } from 'react';

const randomGaussian = () => {
    let u = 0;
    let v = 0;
    while (u === 0) u = Math.random();
    while (v === 0) v = Math.random();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
};

const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

const Visualizer = ({ audioData, audioDataRef: externalAudioDataRef, isListening, intensity = 0, width = 600, height = 400, reduceMotion = false }) => {
    const canvasRef = useRef(null);
    const particlesRef = useRef([]);

    const audioDataRef = useRef(audioData);
    const intensityRef = useRef(intensity);
    const isListeningRef = useRef(isListening);

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

                points.push({
                    x,
                    y,
                    z,
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
            const speakingBoost = currentIsListening ? 1 + intensitySafe * 0.32 : 1;
            const time = timestamp * 0.001;

            ctx.clearRect(0, 0, w, h);

            const coreGlow = ctx.createRadialGradient(centerX, centerY, 0, centerX, centerY, Math.min(w, h) * 0.55);
            coreGlow.addColorStop(0, `rgba(37, 99, 235, ${currentIsListening ? 0.36 : 0.30})`);
            coreGlow.addColorStop(0.34, 'rgba(79, 142, 255, 0.20)');
            coreGlow.addColorStop(0.72, 'rgba(147, 197, 253, 0.085)');
            coreGlow.addColorStop(1, 'rgba(147, 197, 253, 0)');
            ctx.fillStyle = coreGlow;
            ctx.fillRect(0, 0, w, h);

            const plumeGlow = ctx.createRadialGradient(centerX - w * 0.13, centerY + h * 0.03, 0, centerX - w * 0.13, centerY + h * 0.03, Math.min(w, h) * 0.42);
            plumeGlow.addColorStop(0, 'rgba(96, 165, 250, 0.11)');
            plumeGlow.addColorStop(1, 'rgba(96, 165, 250, 0)');
            ctx.fillStyle = plumeGlow;
            ctx.fillRect(0, 0, w, h);

            ctx.globalCompositeOperation = 'source-over';
            const spreadX = Math.min(w * 0.27, 390) * speakingBoost;
            const spreadY = Math.min(h * 0.39, 285) * (currentIsListening ? 1.06 : 1);
            const rotation = reduceMotion ? 0.18 : 0.18 + Math.sin(time * 0.12) * 0.035;
            const cos = Math.cos(rotation);
            const sin = Math.sin(rotation);
            const breath = 1 + Math.sin(time * 1.15) * (reduceMotion ? 0.006 : 0.018);

            for (const p of particlesRef.current) {
                const drift = reduceMotion ? 0 : Math.sin(time * p.speed + p.phase) * p.orbit;
                const x = p.x + drift;
                const z = p.z + Math.cos(time * p.speed + p.phase) * (reduceMotion ? 0.004 : 0.018);
                const rotatedX = x * cos + z * sin;
                const rotatedZ = -x * sin + z * cos;
                const perspective = 1 / (1 + rotatedZ * 0.32);
                const jitterX = reduceMotion ? 0 : Math.sin(time * 0.7 + p.phase) * 1.2;
                const jitterY = reduceMotion ? 0 : Math.cos(time * 0.64 + p.phase) * 1.0;
                const px = centerX + rotatedX * spreadX * perspective * breath + jitterX;
                const py = centerY + p.y * spreadY * perspective * breath + jitterY;
                const depthLight = 0.78 + (1 - clamp((rotatedZ + 1) / 2, 0, 1)) * 0.38;
                const alpha = clamp(p.alpha * depthLight * (currentIsListening ? 1.28 : 1.08), 0.035, 0.72);
                const size = p.size * perspective * (currentIsListening ? 1 + intensitySafe * 0.2 : 1);

                ctx.fillStyle = `hsla(${p.hue}, 100%, ${currentIsListening ? 58 : 55}%, ${alpha})`;
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

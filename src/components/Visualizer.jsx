import React, { memo, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';

const Visualizer = ({ audioData, audioDataRef: externalAudioDataRef, isListening, intensity = 0, width = 600, height = 400, reduceMotion = false }) => {
    const canvasRef = useRef(null);

    // Use a ref for audioData to avoid re-creating the animation loop on every frame
    const audioDataRef = useRef(audioData);
    const intensityRef = useRef(intensity);
    const isListeningRef = useRef(isListening);

    useEffect(() => {
        audioDataRef.current = audioData;
        intensityRef.current = intensity;
        isListeningRef.current = isListening;
    }, [audioData, intensity, isListening]);

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;

        // Ensure canvas internal resolution matches display size for sharpness
        canvas.width = width;
        canvas.height = height;

        const ctx = canvas.getContext('2d');
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

            const w = canvas.width;
            const h = canvas.height;
            const centerX = w / 2;
            const centerY = h / 2;

            // Use current audio data from ref if we were using it for visualization
            // Currently the effect only uses 'intensity', passed as prop. 
            // To ensure we aren't re-triggering this effect constantly, we use refs.

            const currentIntensity = getCurrentIntensity();
            const currentIsListening = isListeningRef.current;

            const baseRadius = Math.min(w, h) * 0.25;
            const radius = baseRadius + (currentIntensity * 40);

            ctx.clearRect(0, 0, w, h);

            // Base Circle (Glow)
            ctx.beginPath();
            ctx.arc(centerX, centerY, radius - 10, 0, Math.PI * 2);
            ctx.strokeStyle = 'rgba(6, 182, 212, 0.1)';
            ctx.lineWidth = 2;
            ctx.stroke();

            if (!currentIsListening) {
                // Idle State: Breathing Circle
                const time = Date.now() / 1000;
                const breath = Math.sin(time * 2) * 5;

                ctx.beginPath();
                ctx.arc(centerX, centerY, radius + breath, 0, Math.PI * 2);
                ctx.strokeStyle = 'rgba(34, 211, 238, 0.5)';
                ctx.lineWidth = 4;
                ctx.shadowBlur = reduceMotion ? 0 : 20;
                ctx.shadowColor = '#22d3ee';
                ctx.stroke();
                ctx.shadowBlur = 0;
            } else {
                // Active State: Just the Circle causing the pulse
                ctx.beginPath();
                ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
                ctx.strokeStyle = 'rgba(34, 211, 238, 0.8)';
                ctx.lineWidth = 4;
                ctx.shadowBlur = reduceMotion ? 0 : 20;
                ctx.shadowColor = '#22d3ee';
                ctx.stroke();
                ctx.shadowBlur = 0;
            }
        };

        draw();
        return () => cancelAnimationFrame(animationId);
    }, [width, height, reduceMotion, externalAudioDataRef]);

    return (
        <div className="relative" style={{ width, height }}>
            {/* Central Logo/Text */}
            <div className="absolute inset-0 flex items-center justify-center z-10 pointer-events-none">
                {reduceMotion ? (
                    <div
                        className="text-cyan-100 font-bold tracking-widest"
                        style={{ fontSize: Math.min(width, height) * 0.1 }}
                    >
                        A.D.A
                    </div>
                ) : (
                    <motion.div
                        animate={{ scale: isListening ? [1, 1.1, 1] : 1 }}
                        transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
                        className="text-cyan-100 font-bold tracking-widest drop-shadow-[0_0_15px_rgba(34,211,238,0.8)]"
                        style={{ fontSize: Math.min(width, height) * 0.1 }}
                    >
                        A.D.A
                    </motion.div>
                )}
            </div>

            <canvas
                ref={canvasRef}
                style={{ width: '100%', height: '100%' }}
            />
        </div>
    );
};

export default memo(Visualizer);

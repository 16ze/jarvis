import React, { memo, useMemo, useRef } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import * as THREE from 'three';

// Génère N positions uniformément réparties sur une sphère via Fibonacci.
const generateFibonacciSphere = (count, radius) => {
    const positions = new Float32Array(count * 3);
    const golden = Math.PI * (1 + Math.sqrt(5));
    for (let i = 0; i < count; i += 1) {
        const t = (i + 0.5) / count;
        const phi = Math.acos(1 - 2 * t);
        const theta = golden * (i + 0.5);
        positions[i * 3] = radius * Math.sin(phi) * Math.cos(theta);
        positions[i * 3 + 1] = radius * Math.cos(phi);
        positions[i * 3 + 2] = radius * Math.sin(phi) * Math.sin(theta);
    }
    return positions;
};

const COLOR_IDLE = new THREE.Color('#3b82f6');   // blue-500
const COLOR_ACTIVE = new THREE.Color('#2563eb'); // blue-600

// Animation tuning — design tokens for the visualizer's behavior.
const ROT_SPEED_IDLE = 0.0008;
const ROT_SPEED_ACTIVE = 0.003;
const REDUCE_MOTION_ROT_FACTOR = 0.3;
const SPEAK_RADIAL_AMPLITUDE = 0.15;     // max radial pulse as fraction of radius
const SPEAK_THRESHOLD = 0.05;            // intensity above which we consider Ada "speaking"
const COLOR_ACTIVE_THRESHOLD = 0.6;      // intensity above which color lerps to active
const COLOR_LERP_RATE = 0.05;
const SIZE_LERP_RATE = 0.05;
const SIZE_IDLE = 0.04;
const SIZE_ACTIVE = 0.06;
const BREATH_FREQ = 1.5;
const BREATH_AMPLITUDE = 0.02;
const WOBBLE_FREQ = 8;
const WOBBLE_PHASE_STEP = 0.1;
const WOBBLE_AMPLITUDE = 0.3;

export const POINTCLOUD_SPEAK_THRESHOLD = SPEAK_THRESHOLD;

const PointsCluster = ({ count, radius, isSpeaking, intensity, reduceMotion }) => {
    const pointsRef = useRef(null);
    const materialRef = useRef(null);

    const originalPositions = useMemo(
        () => generateFibonacciSphere(count, radius),
        [count, radius]
    );

    const livePositions = useMemo(() => originalPositions.slice(), [originalPositions]);

    const tmpColor = useMemo(() => new THREE.Color(), []);

    useFrame((state) => {
        const points = pointsRef.current;
        const material = materialRef.current;
        if (!points || !material) return;

        const t = state.clock.elapsedTime;

        const rotSpeed = isSpeaking ? ROT_SPEED_ACTIVE : ROT_SPEED_IDLE;
        points.rotation.y += reduceMotion ? rotSpeed * REDUCE_MOTION_ROT_FACTOR : rotSpeed;

        const positionsAttr = points.geometry.attributes.position;
        const arr = positionsAttr.array;
        const intensitySafe = Math.max(0, Math.min(1, intensity || 0));

        for (let i = 0; i < count; i += 1) {
            const ox = originalPositions[i * 3];
            const oy = originalPositions[i * 3 + 1];
            const oz = originalPositions[i * 3 + 2];

            let scale;
            if (isSpeaking && !reduceMotion) {
                const wobble = Math.sin(t * WOBBLE_FREQ + i * WOBBLE_PHASE_STEP) * WOBBLE_AMPLITUDE;
                scale = 1 + intensitySafe * SPEAK_RADIAL_AMPLITUDE * (1 + wobble);
            } else {
                scale = 1 + Math.sin(t * BREATH_FREQ) * BREATH_AMPLITUDE;
            }

            arr[i * 3] = ox * scale;
            arr[i * 3 + 1] = oy * scale;
            arr[i * 3 + 2] = oz * scale;
        }
        positionsAttr.needsUpdate = true;

        const targetColor = intensitySafe > COLOR_ACTIVE_THRESHOLD ? COLOR_ACTIVE : COLOR_IDLE;
        tmpColor.copy(material.color);
        tmpColor.lerp(targetColor, COLOR_LERP_RATE);
        material.color.copy(tmpColor);

        const targetSize = isSpeaking ? SIZE_ACTIVE : SIZE_IDLE;
        material.size = material.size + (targetSize - material.size) * SIZE_LERP_RATE;
    });

    return (
        <points ref={pointsRef}>
            <bufferGeometry>
                <bufferAttribute
                    attach="attributes-position"
                    count={count}
                    array={livePositions}
                    itemSize={3}
                />
            </bufferGeometry>
            <pointsMaterial
                ref={materialRef}
                color={COLOR_IDLE}
                size={0.04}
                sizeAttenuation
                transparent
                opacity={0.85}
                depthWrite={false}
            />
        </points>
    );
};

const PointCloudSphere = ({
    isSpeaking = false,
    intensity = 0,
    reduceMotion = false,
    width = 550,
    height = 350,
}) => {
    const pointCount = reduceMotion ? 1000 : 2000;
    const dpr = reduceMotion ? 1 : [1, 2];

    return (
        <div style={{ width, height }} className="relative">
            <Canvas
                dpr={dpr}
                camera={{ position: [0, 0, 3], fov: 50 }}
                gl={{ antialias: !reduceMotion, alpha: true }}
            >
                <ambientLight intensity={0.5} />
                <PointsCluster
                    key={pointCount}
                    count={pointCount}
                    radius={1.0}
                    isSpeaking={isSpeaking}
                    intensity={intensity}
                    reduceMotion={reduceMotion}
                />
            </Canvas>
        </div>
    );
};

export default memo(PointCloudSphere);

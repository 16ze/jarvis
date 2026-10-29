import React, { useMemo, useState, useEffect, useRef } from 'react';
import { Canvas, useLoader, useFrame } from '@react-three/fiber';
import { OrbitControls, Center, Stage } from '@react-three/drei';
import * as THREE from 'three';
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader';
import { Printer } from 'lucide-react';

const GeometryModel = ({ geometry }) => {
    return (
        <mesh geometry={geometry} castShadow receiveShadow>
            <meshStandardMaterial color="#b0b0b8" roughness={0.35} metalness={0.7} />
        </mesh>
    );
};

const LoadingCube = () => {
    const meshRef = React.useRef();
    useFrame((state, delta) => {
        meshRef.current.rotation.x += delta;
        meshRef.current.rotation.y += delta;
    });
    return (
        <mesh ref={meshRef}>
            <boxGeometry args={[10, 10, 10]} />
            <meshStandardMaterial wireframe color="#8e8e93" transparent opacity={0.5} />
        </mesh>
    );
};

const CadWindow = ({ data, thoughts, retryInfo = {}, onClose, socket }) => {
    // data format: { format: "stl", data: "base64..." }
    const [isIterating, setIsIterating] = useState(false);
    const [prompt, setPrompt] = useState("");
    const [isSending, setIsSending] = useState(false);
    const thoughtsEndRef = useRef(null);

    // Debug log
    useEffect(() => {
        if (data) console.log("CadWindow Data:", data.format);
    }, [data]);

    // Auto-scroll thoughts panel
    useEffect(() => {
        if (thoughtsEndRef.current) {
            thoughtsEndRef.current.scrollIntoView({ behavior: 'smooth' });
        }
    }, [thoughts]);

    const geometry = useMemo(() => {
        if (!data || data.format !== 'stl' || !data.data) return null;

        try {
            // Convert Base64 to ArrayBuffer
            const byteCharacters = atob(data.data);
            const byteNumbers = new Array(byteCharacters.length);
            for (let i = 0; i < byteCharacters.length; i++) {
                byteNumbers[i] = byteCharacters.charCodeAt(i);
            }
            const byteArray = new Uint8Array(byteNumbers);

            // Parse directly using THREE.STLLoader
            const loader = new STLLoader();
            const geom = loader.parse(byteArray.buffer);
            geom.center(); // Optional: Center the geometry
            return geom;
        } catch (e) {
            console.error("Failed to decode/parse STL:", e);
            return null;
        }
    }, [data]);

    const handleGenerate = () => {
        if (!prompt.trim()) return;
        setIsSending(true);
        if (socket) {
            socket.emit('generate_cad', { prompt });
        } else {
            console.error("Socket not available in CadWindow");
        }
        setPrompt("");
        // NOTE: We don't clear isSending immediately here if we want to show loading state until data arrives.
        // But for UI responsiveness we might want to just show global loading or similar.
        // For now, let's timeout or rely on parent updates.
        // Actually, let's just keep isSending true until we get an update? 
        // But we don't listen to socket here.
        // Let's reset it after a short delay so user knows it was sent.
        setTimeout(() => setIsSending(false), 2000);
    };

    const handleIterate = () => {
        if (!prompt.trim()) return;
        setIsSending(true);
        // Assuming socket is passed as prop or available globally. 
        // If not, we might need to emit via window event or refactor App.jsx to pass it.
        // For now, looking at App.jsx structure, socket might not be prop. 
        // If socket is missing, we can use window.socket if available or emit a custom event.

        if (socket) {
            socket.emit('iterate_cad', { prompt });
        } else {
            console.error("Socket not available in CadWindow");
        }

        setIsIterating(false);
        setPrompt("");
        setIsSending(false);
    };

    return (
        <div className="w-full h-full relative group bg-surface2 rounded-ada overflow-hidden border border-line shadow-ada">
            {/* Close Button */}
            <div className="absolute top-2 right-2 z-10 opacity-0 group-hover:opacity-100 transition-opacity">
                <button onClick={onClose} className="bg-danger/10 hover:bg-danger/20 text-danger p-1 rounded">X</button>
            </div>

            {/* Top Toolbar */}
            <div className="absolute top-2 left-2 z-10 opacity-0 group-hover:opacity-100 transition-opacity flex gap-2">
                <button
                    onClick={() => setIsIterating(true)}
                    className="bg-accent/10 hover:bg-accent/20 text-accent text-xs px-2 py-1 rounded border border-accent/30"
                >
                    ITERATE
                </button>
                <button
                    onClick={() => {
                        // Trigger print from current available data if possible, or just open printer window
                        // Since slicing requires backend file, we ideally emit an event or show UI
                        // For now we'll rely on voice or tool window, but user requested button here.
                        // Best approach: Open Printer Window + Auto-populate / Trigger
                        if (socket) socket.emit('request_print_window');
                    }}
                    className="bg-positive/10 hover:bg-positive/20 text-positive text-xs px-2 py-1 rounded border border-positive/30 flex items-center gap-1"
                >
                    <Printer size={12} /> PRINT
                </button>
            </div>

            {/* Iteration / Generation Overlay */}
            {/* Show if iterating OR if no data exists (and not loading) */}
            {(isIterating || (!data && data?.format !== 'loading')) && (
                <div className={`absolute inset-0 z-20 ${!data ? 'bg-surface2' : 'bg-black/50'} flex items-center justify-center p-4`}>
                    <div className="ada-card rounded-ada p-4 w-full max-w-sm pointer-events-auto">
                        <h4 className="text-ink text-sm mb-2 font-semibold">
                            {!data ? "New Design" : "Refine Design"}
                        </h4>
                        <textarea
                            value={prompt}
                            onChange={(e) => setPrompt(e.target.value)}
                            placeholder={!data ? "Describe what you want to create..." : "e.g., Make the wheels bigger..."}
                            className="w-full bg-surface border border-line rounded-ada p-2 text-ink text-sm mb-3 focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 h-24 resize-none"
                            autoFocus
                            onKeyDown={(e) => {
                                if (e.key === 'Enter' && !e.shiftKey) {
                                    e.preventDefault();
                                    !data ? handleGenerate() : handleIterate();
                                }
                            }}
                        />
                        <div className="flex justify-end gap-2">
                            {/* Only show cancel if we have data to go back to */}
                            {data && (
                                <button
                                    onClick={() => setIsIterating(false)}
                                    className="text-muted text-xs hover:text-ink px-2 py-1"
                                >
                                    Cancel
                                </button>
                            )}
                            <button
                                onClick={!data ? handleGenerate : handleIterate}
                                disabled={isSending}
                                className="bg-accent hover:bg-accent/90 text-white text-xs px-3 py-1 rounded-ada"
                            >
                                {isSending ? "Generating..." : (!data ? "Generate" : "Update")}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            <Canvas shadows camera={{ position: [4, 4, 4], fov: 45 }}>
                <color attach="background" args={['#1c1c1e']} />

                <Stage environment="city" intensity={0.5}>
                    {data?.format === 'loading' ? (
                        <LoadingCube />
                    ) : (
                        geometry && (
                            <Center>
                                <GeometryModel geometry={geometry} />
                            </Center>
                        )
                    )}
                </Stage>

                <OrbitControls autoRotate={!isIterating} autoRotateSpeed={1} makeDefault />
            </Canvas>

            {/* Streaming Thoughts Panel */}
            {data?.format === 'loading' && (
                <div className="absolute inset-y-0 right-0 w-2/5 p-4 bg-surface/90 backdrop-blur-sm border-l border-line overflow-hidden flex flex-col">
                    <div className="flex items-center justify-between mb-2">
                        <h4 className="text-positive text-xs font-mono tracking-widest uppercase flex items-center gap-2">
                            <span className="w-2 h-2 bg-positive rounded-full animate-pulse"></span>
                            Designer Thinking...
                        </h4>
                        {retryInfo.attempt && (
                            <span className={`text-xs font-mono px-2 py-0.5 rounded ${retryInfo.error ? 'bg-warn/15 text-warn' : 'bg-accent/15 text-accent'}`}>
                                Attempt {retryInfo.attempt}/{retryInfo.maxAttempts || 3}
                            </span>
                        )}
                    </div>
                    {retryInfo.error && (
                        <div className="mb-2 p-2 bg-danger/10 border border-danger/30 rounded text-danger text-xs font-mono">
                            <span className="text-danger font-bold">⚠ Error:</span> {retryInfo.error}
                        </div>
                    )}
                    <div className="flex-1 overflow-y-auto text-muted text-xs font-mono whitespace-pre-wrap leading-relaxed scrollbar-thin scrollbar-thumb-green-500/30">
                        {thoughts}
                        <div ref={thoughtsEndRef} />
                    </div>
                </div>
            )}

            <div className="absolute bottom-2 left-2 text-[10px] text-muted font-mono tracking-widest pointer-events-none">
                CAD_ENGINE_V2: {data?.format?.toUpperCase() || "READY"}
            </div>
        </div>
    );
};

export default CadWindow;

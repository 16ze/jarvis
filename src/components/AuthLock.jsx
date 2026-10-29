import React, { useEffect, useState } from 'react';
import { Lock, Unlock, User } from 'lucide-react';

const AuthLock = ({ socket, onAuthenticated, onAnimationComplete }) => {
    const [frameSrc, setFrameSrc] = useState(null);
    const [message, setMessage] = useState("Initializing Security...");
    const [isUnlocking, setIsUnlocking] = useState(false);

    useEffect(() => {
        if (!socket) return;

        const handleAuthStatus = (data) => {
            console.log("Auth Status:", data);
            if (data.authenticated && !isUnlocking) {
                // Start Unlock Sequence
                setIsUnlocking(true);
                setMessage("Identity Verified. Access Granted.");

                // Wait for animation then notify parent
                setTimeout(() => {
                    onAuthenticated(true);
                }, 2000); // 2 seconds animation
            } else if (!data.authenticated && !isUnlocking) {
                setMessage("Look at the camera to unlock.");
            }
        };

        const handleAuthFrame = (data) => {
            setFrameSrc(`data:image/jpeg;base64,${data.image}`);
        };

        socket.on('auth_status', handleAuthStatus);
        socket.on('auth_frame', handleAuthFrame);

        return () => {
            socket.off('auth_status', handleAuthStatus);
            socket.off('auth_frame', handleAuthFrame);
        };
    }, [socket, onAuthenticated, onAnimationComplete, isUnlocking]);

    const themeColor = isUnlocking ? 'text-positive' : 'text-accent';
    const borderColor = isUnlocking ? 'border-positive' : 'border-accent';
    const shadowColor = 'shadow-ada-lg';
    const bgGradient = isUnlocking
        ? 'from-positive/10 via-bg to-bg'
        : 'from-accent/10 via-bg to-bg';

    return (

        <div className={`fixed inset-0 z-[9999] bg-bg flex flex-col items-center justify-center select-none transition-all duration-[2000ms] ${isUnlocking ? 'opacity-0 scale-110 pointer-events-none' : 'opacity-100'}`}
            style={{ transitionDelay: '2000ms' }}> {/* Delay fade out to show success state */}

            {/* Background Grid */}
            <div className={`absolute inset-0 bg-[radial-gradient(circle_at_center,_var(--tw-gradient-stops))] ${bgGradient} pointer-events-none transition-colors duration-[1500ms]`}></div>

            <div className={`relative flex flex-col items-center gap-6 p-10 border ${borderColor}/30 rounded-ada-lg bg-surface/90 backdrop-blur-xl ${shadowColor} transition-all duration-[1500ms]`}>
                <div className={`text-3xl font-semibold tracking-[0.2em] uppercase flex items-center gap-4 ${themeColor} transition-colors duration-1000`}>
                    {isUnlocking ? <Unlock size={32} /> : <Lock size={32} />}
                    {isUnlocking ? "SYSTEM UNLOCKED" : "SYSTEM LOCKED"}
                </div>

                {/* Camera Feed Frame */}
                <div className={`relative w-64 h-64 border-2 ${borderColor}/40 rounded-ada overflow-hidden bg-surface2 shadow-inner flex items-center justify-center transition-colors duration-500`}>
                    {frameSrc ? (
                        <img
                            src={frameSrc}
                            alt="Auth Camera"
                            className={`w-full h-full object-cover transform scale-x-[-1] transition-opacity duration-500 ${isUnlocking ? 'opacity-50 grayscale' : 'opacity-100'}`}
                        />
                    ) : (
                        <div className={`animate-pulse ${isUnlocking ? 'text-positive/40' : 'text-accent/40'}`}>
                            <User size={64} />
                        </div>
                    )}

                    {/* Scanning Line Animation - remove on unlock */}
                    {!isUnlocking && (
                        <div className="absolute top-0 left-0 w-full h-1 bg-accent/80 animate-[scan_2s_ease-in-out_infinite]"></div>
                    )}

                    {/* Success Overlay */}
                    {isUnlocking && (
                        <div className="absolute inset-0 flex items-center justify-center bg-positive/15 animate-pulse">
                            <Unlock size={64} className="text-positive" />
                        </div>
                    )}
                </div>

                <div className={`text-sm tracking-widest ${isUnlocking ? 'text-positive' : 'text-accent'} animate-pulse transition-colors duration-500`}>
                    {message}
                </div>
            </div>

            {/* Keyframe for scan animation */}
            <style>{`
                @keyframes scan {
                    0%, 100% { top: 0%; opacity: 0; }
                    50% { opacity: 1; }
                    100% { top: 100%; opacity: 0; }
                }
             `}</style>
        </div>
    );
};

export default AuthLock;

import React, { useState, useEffect } from 'react';
import { X, RefreshCw, Power, Sun, Palette } from 'lucide-react';

const KasaWindow = ({
    socket,
    position,
    onClose,
    activeDragElement,
    setActiveDragElement,
    devices,
    onMouseDown,
    zIndex = 40
}) => {
    const [isThinking, setIsThinking] = useState(false);
    const [loadingDevices, setLoadingDevices] = useState({}); // { ip: true/false }

    useEffect(() => {
        // Listen for individual updates to clear loading state
        const onUpdate = (data) => {
            if (data && data.ip) {
                setLoadingDevices(prev => {
                    const next = { ...prev };
                    delete next[data.ip];
                    return next;
                });
            }
        };

        socket.on('kasa_update', onUpdate);
        return () => socket.off('kasa_update', onUpdate);
    }, [socket]);


    const handleDiscover = () => {
        setIsThinking(true);
        socket.emit('discover_kasa');
        // Reset thinking after 5s if no response (safety)
        setTimeout(() => setIsThinking(false), 5000);
    };

    useEffect(() => {
        if (devices && devices.length > 0) {
            setIsThinking(false);
        }
    }, [devices]);

    const handleToggle = (ip, currentState) => {
        setLoadingDevices(prev => ({ ...prev, [ip]: true }));
        socket.emit('control_kasa', {
            ip: ip,
            action: currentState ? 'off' : 'on'
        });
    };


    const handleBrightness = (ip, val) => {
        socket.emit('control_kasa', {
            ip: ip,
            action: 'brightness',
            value: parseInt(val)
        });
    };

    const handleColor = (ip, hue) => {
        socket.emit('control_kasa', {
            ip: ip,
            action: 'color',
            value: { h: parseInt(hue), s: 100, v: 100 }
        });
    };

    // Color logic can be added later, keeping it simple for now as requested (Off, On, Settings)

    return (
        <div
            id="kasa"
            onMouseDown={onMouseDown}
            className={`absolute flex flex-col gap-2 p-4 rounded-ada-lg ada-float transition-all duration-200 select-none
                ${activeDragElement === 'kasa' ? 'ring-2 ring-accent' : ''}
            `}
            style={{
                left: position.x,
                top: position.y,
                width: '320px',
                minHeight: '200px',
                transform: 'translate(-50%, -50%)',
                zIndex: zIndex
            }}
        >
            {/* Header */}
            <div data-drag-handle className="flex items-center justify-between pb-2 border-b border-line mb-2 cursor-grab active:cursor-grabbing">
                <div className="flex items-center gap-2">
                    <div className={`w-2 h-2 rounded-full ${devices.length > 0 ? 'bg-positive animate-pulse' : 'bg-line'}`} />
                    <h3 className="font-semibold text-ink tracking-wider text-sm">SMART CONTROL</h3>
                </div>
                <button
                    onClick={onClose}
                    className="p-1 rounded hover:bg-ink/5 transition-colors text-muted hover:text-ink"
                >
                    <X size={16} />
                </button>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto max-h-[400px] scrollbar-hide">

                {devices.length === 0 && !isThinking && (
                    <div className="flex flex-col items-center justify-center p-8 text-center text-muted">
                        <p className="text-xs mb-4">No devices found. Ensure they are on the same network.</p>
                        <button
                            onClick={handleDiscover}
                            className="flex items-center gap-2 px-4 py-2 bg-accent/10 border border-accent/30 rounded-ada hover:bg-accent/20 hover:border-accent transition-all text-xs text-accent"
                        >
                            <RefreshCw size={14} /> DISCOVER LIGHTS
                        </button>
                    </div>
                )}

                {isThinking && (
                    <div className="flex flex-col items-center justify-center p-8 gap-3">
                        <div className="w-6 h-6 border-2 border-accent border-t-transparent rounded-full animate-spin" />
                        <span className="text-xs text-accent animate-pulse">Scanning Network...</span>
                    </div>
                )}

                {devices.map((dev) => (
                    <div key={dev.ip} className="mb-3 p-3 bg-surface2 rounded-ada border border-line hover:border-accent/40 transition-all">
                        <div className="flex items-center justify-between mb-2">
                            <div className="flex flex-col">
                                <span className="font-semibold text-sm text-ink">{dev.alias}</span>
                                <span className="text-[10px] text-muted font-mono">{dev.ip}</span>
                            </div>
                            <button
                                onClick={() => handleToggle(dev.ip, dev.is_on)}
                                disabled={loadingDevices[dev.ip]}
                                className={`p-2 rounded-full transition-all ${dev.is_on
                                    ? 'bg-positive/15 text-positive'
                                    : 'bg-surface text-muted hover:text-ink'}
                                    ${loadingDevices[dev.ip] ? 'opacity-50 cursor-not-allowed' : ''}
                                `}
                            >
                                {loadingDevices[dev.ip] ? (
                                    <div className="w-[18px] h-[18px] border-2 border-current border-t-transparent rounded-full animate-spin" />
                                ) : (
                                    <Power size={18} />
                                )}
                            </button>

                        </div>

                        {/* Controls */}
                        {dev.has_brightness && dev.is_on && (
                            <div className="flex items-center gap-2 mt-2">
                                <Sun size={14} className="text-warn" />
                                <input
                                    type="range"
                                    min="0"
                                    max="100"
                                    defaultValue={dev.brightness || 100}
                                    onChange={(e) => handleBrightness(dev.ip, e.target.value)}
                                    className="w-full h-1 bg-surface2 rounded-full appearance-none cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-accent"
                                />
                            </div>
                        )}

                        {/* Color Control */}
                        {dev.has_color && dev.is_on && (
                            <div className="flex items-center gap-2 mt-2">
                                <Palette size={14} className="text-muted" />
                                <input
                                    type="range"
                                    min="0"
                                    max="360"
                                    defaultValue={(dev.hsv && dev.hsv.h) || 0}
                                    onChange={(e) => handleColor(dev.ip, e.target.value)}
                                    className="w-full h-1 rounded-full appearance-none cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-white"
                                    style={{
                                        background: 'linear-gradient(to right, red, yellow, lime, cyan, blue, magenta, red)'
                                    }}
                                />
                            </div>
                        )}
                    </div>
                ))}
            </div>
            {/* Bottom Discover (if devices exist) */}
            {devices.length > 0 && (
                <div className="pt-2 border-t border-line mt-2 flex justify-end">
                    <button
                        onClick={handleDiscover}
                        className="p-1 text-muted hover:text-accent transition-colors"
                        title="Rescan"
                    >
                        <RefreshCw size={14} />
                    </button>
                </div>
            )}
        </div>
    );
};

export default KasaWindow;

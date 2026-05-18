import React, { useState, useEffect } from 'react';
import { X, RefreshCw, Printer, Thermometer, Clock, FileText, CheckCircle, AlertTriangle, ExternalLink } from 'lucide-react';

const shell = (() => {
    try {
        return window.require('electron').shell;
    } catch {
        return { openExternal: (url) => window.open(url, '_blank') };
    }
})();

const PrinterWindow = ({
    socket,
    position,
    onClose,
    activeDragElement,
    setActiveDragElement,
    onMouseDown,
    zIndex = 40
}) => {
    const [isDiscovering, setIsDiscovering] = useState(false);
    const [printers, setPrinters] = useState([]); // [{ name, host, port, printer_type, status: {...}, camera_url: ... }]
    const [selectedPrinter, setSelectedPrinter] = useState(null);
    const [slicingProgress, setSlicingProgress] = useState({ percent: 0, message: '', active: false });

    // Initial discovery on mount
    useEffect(() => {
        if (socket) {
            handleDiscover();

            socket.on('printer_list', (list) => {
                setPrinters(list);
                setIsDiscovering(false);
            });

            socket.on('print_status_update', (data) => {
                // Update specific printer status in list
                setPrinters(prev => prev.map(p =>
                    p.name === data.printer ? { ...p, status: data } : p
                ));
            });

            socket.on('slicing_progress', (data) => {
                setSlicingProgress({
                    percent: data.percent,
                    message: data.message,
                    active: data.percent < 100
                });
            });

            socket.on('print_result', (result) => {
                // Reset slicing when print starts or fails
                if (result.success) {
                    setSlicingProgress({ percent: 100, message: 'Done', active: false });
                } else {
                    setSlicingProgress({ percent: 0, message: 'Failed', active: false });
                }
            });
        }
        return () => {
            if (socket) {
                socket.off('printer_list');
                socket.off('print_status_update');
                socket.off('slicing_progress');
                socket.off('print_result');
            }
        };
    }, [socket]);

    const handleDiscover = () => {
        setIsDiscovering(true);
        socket.emit('discover_printers');
        // Fallback timeout
        setTimeout(() => setIsDiscovering(false), 5000);
    };

    const getStatusColor = (state) => {
        if (!state) return 'text-slate-500';
        const s = state.toLowerCase();
        if (s.includes('print')) return 'text-green-500';
        if (s.includes('paus')) return 'text-yellow-500';
        if (s.includes('error') || s.includes('fail')) return 'text-red-500';
        return 'text-blue-600';
    };

    return (
        <div
            id="printer"
            onMouseDown={onMouseDown}
            style={{
                position: 'absolute',
                left: position.x,
                top: position.y,
                transform: 'translate(-50%, -50%)',
                width: '380px',
                zIndex: zIndex
            }}
            className="pointer-events-auto backdrop-blur-xl bg-white/80 border border-blue-400/40 rounded-2xl shadow-[0_0_30px_rgba(59,130,246,0.15)] overflow-hidden flex flex-col"
        >
            {/* Header */}
            <div data-drag-handle className="flex items-center justify-between p-4 border-b border-blue-200 bg-white/60 cursor-grab active:cursor-grabbing">
                <div className="flex items-center gap-2">
                    <Printer size={16} className="text-blue-600" />
                    <span className="text-xs font-bold tracking-widest text-blue-700 uppercase">3D Printers</span>
                </div>
                <div className="flex items-center gap-2">
                    <button
                        onClick={handleDiscover}
                        disabled={isDiscovering}
                        className={`p-1.5 hover:bg-blue-100 rounded-full transition-colors ${isDiscovering ? 'animate-spin text-blue-600' : 'text-slate-500 hover:text-blue-700'}`}
                    >
                        <RefreshCw size={14} />
                    </button>
                    <button
                        onClick={onClose}
                        className="p-1.5 hover:bg-blue-100 rounded-full text-slate-500 hover:text-slate-800 transition-colors"
                    >
                        <X size={14} />
                    </button>
                </div>
            </div>

            {/* Content */}
            <div className="p-4 max-h-[400px] overflow-y-auto custom-scrollbar">
                {/* Manual Add Section */}
                <div className="mb-4 p-3 bg-white/40 border border-blue-200 rounded-lg">
                    <div className="text-[10px] uppercase text-slate-500 font-bold mb-2 tracking-wider">Manual Add</div>
                    <div className="flex flex-col gap-2">
                        <input
                            id="printer-name-input"
                            type="text"
                            placeholder="Printer Name (e.g. Creality K1)"
                            className="w-full bg-white/70 border border-blue-200 rounded px-2 py-1 text-xs text-slate-800 focus:border-blue-500 outline-none placeholder:text-slate-400"
                        />
                        <div className="flex gap-2">
                            <input
                                id="printer-ip-input"
                                type="text"
                                placeholder="IP Address (e.g. 192.168.1.50)"
                                className="flex-1 bg-white/70 border border-blue-200 rounded px-2 py-1 text-xs text-slate-800 focus:border-blue-500 outline-none placeholder:text-slate-400"
                                onKeyDown={(e) => {
                                    if (e.key === 'Enter') {
                                        const ip = e.target.value.trim();
                                        const nameInput = document.getElementById('printer-name-input');
                                        const name = nameInput?.value.trim() || ip;
                                        if (ip) {
                                            socket.emit('add_printer', { host: ip, name: name, type: 'moonraker' });
                                            e.target.value = '';
                                            if (nameInput) nameInput.value = '';
                                            setIsDiscovering(true);
                                        }
                                    }
                                }}
                            />
                            <button
                                className="bg-green-500/20 hover:bg-green-500/30 text-green-600 text-xs px-3 rounded transition-colors"
                                onClick={() => {
                                    const ipInput = document.getElementById('printer-ip-input');
                                    const nameInput = document.getElementById('printer-name-input');
                                    const ip = ipInput?.value.trim();
                                    const name = nameInput?.value.trim() || ip;
                                    if (ip) {
                                        socket.emit('add_printer', { host: ip, name: name, type: 'moonraker' });
                                        if (ipInput) ipInput.value = '';
                                        if (nameInput) nameInput.value = '';
                                        setIsDiscovering(true);
                                    }
                                }}
                            >
                                Add
                            </button>
                        </div>
                    </div>
                </div>

                {printers.length === 0 ? (
                    <div className="text-center py-8 text-slate-400 text-xs">
                        {isDiscovering ? (
                            <div className="flex flex-col items-center gap-2">
                                <RefreshCw className="animate-spin" size={20} />
                                <span>Scanning Network...</span>
                            </div>
                        ) : (
                            "No printers found. Try adding IP manually."
                        )}
                    </div>
                ) : (
                    <div className="space-y-3">
                        {/* Global Pipeline Visualizer (when slicing is active) */}
                        {slicingProgress.active && (
                            <div className="mb-4 p-3 bg-blue-50 border border-blue-400/40 rounded-lg">
                                <div className="text-[10px] uppercase text-blue-700 font-bold mb-2 tracking-wider flex justify-between">
                                    <span>Preparation Pipeline</span>
                                    <span>{slicingProgress.percent}%</span>
                                </div>
                                {/* Pipeline Stages */}
                                <div className="flex items-center gap-2 mb-2 text-[10px] text-slate-500">
                                    <div className={`flex items-center gap-1 ${slicingProgress.percent < 100 ? 'text-green-500 font-bold' : ''}`}>
                                        <div className={`w-2 h-2 rounded-full ${slicingProgress.percent < 100 ? 'bg-green-500 animate-pulse' : 'bg-slate-300'}`}></div>
                                        Slicing
                                    </div>
                                    <div className="h-[1px] w-4 bg-blue-200"></div>
                                    <div className="flex items-center gap-1">
                                        <div className="w-2 h-2 rounded-full bg-slate-300"></div>
                                        Printing
                                    </div>
                                </div>
                                <div className="w-full h-1 bg-blue-100 rounded-full overflow-hidden">
                                    <div
                                        className="h-full bg-blue-500 transition-all duration-300"
                                        style={{ width: `${slicingProgress.percent}%` }}
                                    />
                                </div>
                                <div className="text-[10px] text-blue-700/70 mt-1 truncate">
                                    {slicingProgress.message}
                                </div>
                            </div>
                        )}

                        {printers.map((printer, idx) => (
                            <div key={idx} className="bg-white/40 border border-blue-200 rounded-lg p-3 hover:border-blue-400/40 transition-all">
                                <div className="flex justify-between items-start mb-2">
                                    <div>
                                        <div className="font-bold text-sm text-slate-800">{printer.name}</div>
                                        <div className="text-[10px] text-slate-500 uppercase tracking-wider">{printer.host}:{printer.port} • {printer.printer_type}</div>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        {/* Open Interface Button */}
                                        <button
                                            onClick={() => shell.openExternal(`http://${printer.host}`)}
                                            className="flex items-center gap-1 text-[10px] text-blue-600 hover:text-blue-700 bg-blue-50 hover:bg-blue-100 border border-blue-400/40 px-2 py-0.5 rounded transition-colors"
                                            title="Open printer web interface"
                                        >
                                            <ExternalLink size={10} />
                                            <span>Open</span>
                                        </button>
                                        {printer.status && (
                                            <div className={`text-[10px] font-bold px-2 py-0.5 rounded-full bg-white/60 ${getStatusColor(printer.status.state)}`}>
                                                {printer.status.state?.toUpperCase() || "IDLE"}
                                            </div>
                                        )}
                                    </div>
                                </div>

                                {/* Camera Feed (kept dark for video clarity) */}
                                {printer.camera_url && (
                                    <div className="mb-3 rounded overflow-hidden border border-blue-200 bg-black relative aspect-video">
                                        <img
                                            src={printer.camera_url}
                                            alt="Printer Camera"
                                            className="w-full h-full object-cover"
                                            onError={(e) => {
                                                e.target.style.display = 'none';
                                                e.target.nextSibling.style.display = 'flex';
                                            }}
                                        />
                                        <div className="hidden absolute inset-0 flex items-center justify-center text-white/30 text-xs">
                                            Camera Stream Unavailable
                                        </div>
                                    </div>
                                )}

                                {printer.status && (
                                    <div className="space-y-2 mt-3 pt-3 border-t border-blue-200">
                                        {/* Progress Bar */}
                                        {printer.status.progress_percent > 0 && (
                                            <div className="w-full h-1 bg-blue-100 rounded-full overflow-hidden">
                                                <div
                                                    className="h-full bg-green-500 transition-all duration-500"
                                                    style={{ width: `${printer.status.progress_percent}%` }}
                                                />
                                            </div>
                                        )}

                                        {/* Stats Grid */}
                                        <div className="grid grid-cols-2 gap-2 text-[10px] text-slate-600">
                                            {printer.status.filename && (
                                                <div className="col-span-2 flex items-center gap-1.5 truncate">
                                                    <FileText size={10} className="text-green-500" />
                                                    <span className="truncate">{printer.status.filename}</span>
                                                </div>
                                            )}
                                            {printer.status.temperatures?.hotend && (
                                                <div className="flex items-center gap-1.5">
                                                    <Thermometer size={10} className="text-red-500" />
                                                    <span>E: {Math.round(printer.status.temperatures.hotend.current)}°C</span>
                                                </div>
                                            )}
                                            {printer.status.temperatures?.bed && (
                                                <div className="flex items-center gap-1.5">
                                                    <Thermometer size={10} className="text-blue-500" />
                                                    <span>B: {Math.round(printer.status.temperatures.bed.current)}°C</span>
                                                </div>
                                            )}
                                            {printer.status.time_remaining && (
                                                <div className="flex items-center gap-1.5">
                                                    <Clock size={10} className="text-yellow-500" />
                                                    <span>{printer.status.time_remaining} left</span>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
};

export default PrinterWindow;

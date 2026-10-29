import React, { useState, useEffect } from 'react';
import { Save, X, Power } from 'lucide-react';

const MemoryPrompt = ({ onConfirm, onDeny, onCancel }) => {
    const [filename, setFilename] = useState('');

    useEffect(() => {
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
        setFilename(`memory_${timestamp}`);
    }, []);

    return (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/40 backdrop-blur-sm">
            <div className="ada-card ada-scale-in rounded-ada-lg p-8 max-w-md w-full text-center relative overflow-hidden">
                <Save className="w-12 h-12 text-accent mx-auto mb-4" />

                <h2 className="text-xl font-semibold text-ink mb-2">SAVE MEMORY?</h2>
                <p className="text-muted mb-6 text-sm">
                    Do you want to save this conversation to Long Term Memory?
                </p>

                {/* Filename Input */}
                <div className="mb-6 relative">
                    <label className="block text-xs font-semibold text-muted uppercase tracking-wider mb-2 text-left pl-1">Memory Name</label>
                    <input
                        type="text"
                        value={filename}
                        onChange={(e) => setFilename(e.target.value)}
                        className="w-full bg-surface border border-line rounded-ada p-3 text-ink focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 font-mono text-sm"
                        placeholder="Enter filename..."
                    />
                    <div className="absolute right-3 top-[38px] text-muted text-xs pointer-events-none">.txt</div>
                </div>

                <div className="flex flex-col gap-3">
                    <button
                        onClick={() => onConfirm(filename)}
                        className="w-full bg-accent hover:bg-accent/90 text-white py-3 rounded-ada transition-all font-medium flex items-center justify-center gap-2 group"
                    >
                        <Save size={18} className="group-hover:scale-110 transition-transform" />
                        YES, SAVE & EXIT
                    </button>

                    <button
                        onClick={onDeny}
                        className="w-full bg-transparent hover:bg-danger/10 text-danger border border-line hover:border-danger/40 py-3 rounded-ada transition-all font-medium flex items-center justify-center gap-2"
                    >
                        <Power size={18} />
                        NO, JUST EXIT
                    </button>

                    <button
                        onClick={onCancel}
                        className="w-full mt-2 text-muted hover:text-ink text-xs tracking-wider uppercase transition-colors"
                    >
                        Cancel
                    </button>
                </div>
            </div>
        </div>
    );
};

export default MemoryPrompt;

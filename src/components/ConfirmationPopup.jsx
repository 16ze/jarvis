import React from 'react';

const ConfirmationPopup = ({ request, onConfirm, onDeny }) => {
    if (!request) return null;

    return (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/40 backdrop-blur-sm animate-fade-in">
            <div className="ada-scale-in ada-card relative w-full max-w-lg p-8 rounded-ada-lg">

                {/* Header with Icon */}
                <div className="flex items-center gap-4 mb-6 relative z-10">
                    <div className="p-3 rounded-full bg-accent/10 text-accent">
                        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>
                    </div>
                    <div>
                        <h2 className="text-xl font-semibold text-ink">
                            AUTHORIZATION REQUIRED
                        </h2>
                        <p className="text-xs text-muted tracking-wider uppercase">
                            AI Logic Core Request
                        </p>
                    </div>
                </div>

                {/* Content */}
                <div className="mb-8 space-y-4 relative z-10">
                    <p className="text-muted leading-relaxed text-sm">
                        The system is requesting permission to execute an autonomous function. Please review the parameters below.
                    </p>

                    <div className="space-y-2">
                        <div className="bg-surface2 border border-line rounded-ada overflow-hidden">
                            <div className="bg-surface px-4 py-2 border-b border-line flex justify-between items-center">
                                <span className="text-xs text-accent font-semibold uppercase tracking-wider">Function</span>
                                <span className="text-xs text-muted font-mono">system.call</span>
                            </div>
                            <div className="p-4">
                                <div className="text-ink font-mono text-lg font-medium">{request.tool}</div>
                            </div>
                        </div>

                        <div className="bg-surface2 border border-line rounded-ada overflow-hidden">
                            <div className="bg-surface px-4 py-2 border-b border-line flex justify-between items-center">
                                <span className="text-xs text-accent font-semibold uppercase tracking-wider">Parameters</span>
                                <span className="text-xs text-muted font-mono">json.payload</span>
                            </div>
                            <div className="p-4 bg-surface2">
                                <pre className="text-xs text-ink font-mono overflow-x-auto whitespace-pre-wrap leading-relaxed">
                                    {JSON.stringify(request.args, null, 2)}
                                </pre>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Actions */}
                <div className="flex gap-4 relative z-10">
                    <button
                        onClick={onDeny}
                        className="flex-1 px-4 py-3.5 rounded-ada border border-line bg-surface text-danger hover:bg-danger/10 hover:border-danger/40 transition-all duration-200 font-medium tracking-wider uppercase text-xs"
                    >
                        Deny Request
                    </button>
                    <button
                        onClick={onConfirm}
                        className="flex-1 px-4 py-3.5 rounded-ada bg-accent text-white hover:bg-accent/90 transition-all duration-200 font-medium tracking-wider uppercase text-xs"
                    >
                        Authorize Execution
                    </button>
                </div>
            </div>
        </div>
    );
};

export default ConfirmationPopup;

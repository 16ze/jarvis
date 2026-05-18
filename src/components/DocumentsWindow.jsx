import React, { useState, useEffect, useRef } from 'react';
import { X, Upload, FileText, Trash2, Loader } from 'lucide-react';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';
const ADA_TOKEN = import.meta.env.VITE_ADA_API_TOKEN || '';

const authHeaders = () => ({ Authorization: `Bearer ${ADA_TOKEN}` });

const DocumentsWindow = ({ onClose }) => {
    const [documents, setDocuments] = useState([]);
    const [uploading, setUploading] = useState(false);
    const [uploadStatus, setUploadStatus] = useState(null); // { type: 'success'|'error', msg }
    const [dragging, setDragging] = useState(false);
    const fileInputRef = useRef(null);

    const fetchDocuments = async () => {
        try {
            const res = await fetch(`${BACKEND_URL}/documents`, { headers: authHeaders() });
            const data = await res.json();
            setDocuments(data.documents || []);
        } catch (e) {
            console.error('Failed to fetch documents', e);
        }
    };

    useEffect(() => {
        fetchDocuments();
    }, []);

    const uploadFile = async (file) => {
        setUploading(true);
        setUploadStatus(null);
        const formData = new FormData();
        formData.append('file', file);
        try {
            const res = await fetch(`${BACKEND_URL}/documents/upload`, {
                method: 'POST',
                headers: authHeaders(),
                body: formData,
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Upload failed');
            setUploadStatus({ type: 'success', msg: `✓ ${file.name} — ${data.chunks} chunks indexés` });
            fetchDocuments();
        } catch (e) {
            setUploadStatus({ type: 'error', msg: `✗ ${e.message}` });
        } finally {
            setUploading(false);
        }
    };

    const handleFiles = (files) => {
        if (files.length === 0) return;
        Array.from(files).forEach(uploadFile);
    };

    const deleteDocument = async (filename) => {
        try {
            await fetch(`${BACKEND_URL}/documents/${encodeURIComponent(filename)}`, { method: 'DELETE', headers: authHeaders() });
            setDocuments(prev => prev.filter(d => d.filename !== filename));
        } catch (e) {
            console.error('Delete failed', e);
        }
    };

    const onDragOver = (e) => { e.preventDefault(); setDragging(true); };
    const onDragLeave = () => setDragging(false);
    const onDrop = (e) => {
        e.preventDefault();
        setDragging(false);
        handleFiles(e.dataTransfer.files);
    };

    const supportedFormats = 'PDF, DOCX, TXT, MD, PY, JS, TS, JSON, CSV, HTML';

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-white/40 backdrop-blur-sm">
            <div className="w-[520px] max-h-[80vh] bg-white/80 border border-blue-400/40 rounded-xl flex flex-col shadow-2xl shadow-blue-500/20 backdrop-blur-xl">

                {/* Header */}
                <div className="flex items-center justify-between px-5 py-4 border-b border-blue-200">
                    <div className="flex items-center gap-2">
                        <FileText size={16} className="text-blue-600" />
                        <span className="text-sm font-mono text-blue-700 tracking-wider">BASE DE CONNAISSANCES</span>
                    </div>
                    <button onClick={onClose} className="text-slate-500 hover:text-blue-700 transition-colors">
                        <X size={16} />
                    </button>
                </div>

                {/* Drop zone */}
                <div
                    className={`mx-5 mt-4 border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-all ${
                        dragging
                            ? 'border-blue-500 bg-blue-50'
                            : 'border-blue-200 hover:border-blue-400/60 hover:bg-blue-50/60'
                    }`}
                    onDragOver={onDragOver}
                    onDragLeave={onDragLeave}
                    onDrop={onDrop}
                    onClick={() => fileInputRef.current?.click()}
                >
                    <input
                        ref={fileInputRef}
                        type="file"
                        multiple
                        className="hidden"
                        accept=".pdf,.docx,.txt,.md,.py,.js,.ts,.jsx,.tsx,.json,.csv,.html,.css"
                        onChange={(e) => handleFiles(e.target.files)}
                    />
                    {uploading ? (
                        <div className="flex items-center justify-center gap-2 text-blue-700">
                            <Loader size={16} className="animate-spin" />
                            <span className="text-xs font-mono">Indexation en cours...</span>
                        </div>
                    ) : (
                        <>
                            <Upload size={20} className="mx-auto mb-2 text-blue-600" />
                            <p className="text-xs text-blue-700 font-mono">Glisse un fichier ici ou clique pour uploader</p>
                            <p className="text-[10px] text-slate-500 font-mono mt-1">{supportedFormats}</p>
                        </>
                    )}
                </div>

                {/* Upload status */}
                {uploadStatus && (
                    <div className={`mx-5 mt-2 px-3 py-2 rounded text-xs font-mono ${
                        uploadStatus.type === 'success'
                            ? 'bg-green-50 border border-green-300 text-green-700'
                            : 'bg-red-50 border border-red-300 text-red-700'
                    }`}>
                        {uploadStatus.msg}
                    </div>
                )}

                {/* Document list */}
                <div className="flex-1 overflow-y-auto px-5 py-4 space-y-2 min-h-0">
                    {documents.length === 0 ? (
                        <div className="text-center py-8">
                            <p className="text-xs text-slate-500 font-mono">Aucun document indexé</p>
                            <p className="text-[10px] text-slate-400 font-mono mt-1">Ada pourra répondre à des questions sur vos fichiers</p>
                        </div>
                    ) : (
                        documents.map((doc) => (
                            <div
                                key={doc.filename}
                                className="flex items-center justify-between px-3 py-2.5 bg-white/60 border border-blue-200 rounded-lg group"
                            >
                                <div className="flex items-center gap-3 min-w-0">
                                    <FileText size={13} className="text-blue-600 shrink-0" />
                                    <div className="min-w-0">
                                        <p className="text-xs font-mono text-blue-700 truncate">{doc.filename}</p>
                                        <p className="text-[10px] text-slate-500 font-mono">
                                            {doc.chunks} chunks · {doc.added?.slice(0, 10)}
                                        </p>
                                    </div>
                                </div>
                                <button
                                    onClick={() => deleteDocument(doc.filename)}
                                    className="text-slate-400 hover:text-red-500 transition-colors opacity-0 group-hover:opacity-100 shrink-0 ml-2"
                                >
                                    <Trash2 size={13} />
                                </button>
                            </div>
                        ))
                    )}
                </div>

                {/* Footer */}
                <div className="px-5 py-3 border-t border-blue-200">
                    <p className="text-[10px] text-slate-500 font-mono text-center">
                        {documents.length} document{documents.length !== 1 ? 's' : ''} indexé{documents.length !== 1 ? 's' : ''} · Ada les consulte automatiquement
                    </p>
                </div>
            </div>
        </div>
    );
};

export default DocumentsWindow;

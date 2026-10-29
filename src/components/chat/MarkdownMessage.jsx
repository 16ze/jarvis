import React, { useCallback, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import { Check, Copy } from 'lucide-react';
import { twMerge } from 'tailwind-merge';
import clsx from 'clsx';

/**
 * Bouton « copier » pour un bloc de code.
 * Feedback visuel 1,5 s (icône Copy → Check).
 */
function CodeCopyButton({ getText }) {
    const [copied, setCopied] = useState(false);

    const handleCopy = useCallback(async () => {
        try {
            await navigator.clipboard.writeText(getText());
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
        } catch {
            /* clipboard indisponible — on ignore silencieusement */
        }
    }, [getText]);

    return (
        <button
            type="button"
            onClick={handleCopy}
            className="absolute right-2 top-2 inline-flex items-center gap-1 rounded-ada border border-line bg-surface/90 px-2 py-1 text-[11px] font-medium text-muted shadow-ada-sm backdrop-blur transition hover:text-ink"
            aria-label={copied ? 'Copié' : 'Copier le code'}
            title={copied ? 'Copié' : 'Copier le code'}
        >
            {copied ? <Check size={13} strokeWidth={2.2} /> : <Copy size={13} strokeWidth={2} />}
            <span>{copied ? 'Copié' : 'Copier'}</span>
        </button>
    );
}

/** Extrait récursivement le texte brut des enfants React (pour le presse-papiers). */
function extractText(node) {
    if (node == null || node === false) return '';
    if (typeof node === 'string' || typeof node === 'number') return String(node);
    if (Array.isArray(node)) return node.map(extractText).join('');
    if (node.props && node.props.children) return extractText(node.props.children);
    return '';
}

const components = {
    // Liens — accent, nouvel onglet sécurisé
    a: ({ node, children, ...props }) => (
        <a
            {...props}
            target="_blank"
            rel="noreferrer"
            className="text-accent underline decoration-accent/30 underline-offset-2 transition hover:decoration-accent"
        >
            {children}
        </a>
    ),

    // Bloc de code (pre) — fond surface2, bordure, rayon, scroll horizontal, bouton copier
    pre: ({ node, children, ...props }) => {
        const codeText = extractText(children);
        return (
            <div className="group relative my-3">
                <CodeCopyButton getText={() => codeText} />
                <pre
                    {...props}
                    className="overflow-x-auto rounded-ada border border-line bg-surface2 p-3 pt-9 font-mono text-[13px] leading-relaxed text-ink"
                >
                    {children}
                </pre>
            </div>
        );
    },

    // Code inline vs code en bloc (le bloc est stylé par <pre>)
    code: ({ node, inline, className, children, ...props }) => {
        if (inline) {
            return (
                <code
                    {...props}
                    className="rounded-[6px] border border-line bg-surface2 px-1.5 py-0.5 font-mono text-[0.85em] text-ink"
                >
                    {children}
                </code>
            );
        }
        return (
            <code {...props} className={clsx(className, 'font-mono')}>
                {children}
            </code>
        );
    },

    // Tables GFM — bordures fines, en-tête surface2
    table: ({ node, children, ...props }) => (
        <div className="my-3 overflow-x-auto">
            <table {...props} className="w-full border-collapse text-sm">
                {children}
            </table>
        </div>
    ),
    thead: ({ node, children, ...props }) => (
        <thead {...props} className="bg-surface2">
            {children}
        </thead>
    ),
    th: ({ node, children, ...props }) => (
        <th {...props} className="border border-line px-3 py-1.5 text-left font-semibold text-ink">
            {children}
        </th>
    ),
    td: ({ node, children, ...props }) => (
        <td {...props} className="border border-line px-3 py-1.5 align-top text-ink">
            {children}
        </td>
    ),

    // Listes
    ul: ({ node, children, ...props }) => (
        <ul {...props} className="my-2 list-disc space-y-1 pl-5 marker:text-muted">
            {children}
        </ul>
    ),
    ol: ({ node, children, ...props }) => (
        <ol {...props} className="my-2 list-decimal space-y-1 pl-5 marker:text-muted">
            {children}
        </ol>
    ),
    li: ({ node, children, ...props }) => (
        <li {...props} className="leading-relaxed">
            {children}
        </li>
    ),

    // Titres
    h1: ({ node, children, ...props }) => (
        <h1 {...props} className="mb-2 mt-3 text-lg font-semibold text-ink">
            {children}
        </h1>
    ),
    h2: ({ node, children, ...props }) => (
        <h2 {...props} className="mb-2 mt-3 text-base font-semibold text-ink">
            {children}
        </h2>
    ),
    h3: ({ node, children, ...props }) => (
        <h3 {...props} className="mb-1.5 mt-2.5 text-sm font-semibold text-ink">
            {children}
        </h3>
    ),

    // Paragraphes, citations, règles
    p: ({ node, children, ...props }) => (
        <p {...props} className="my-2 leading-relaxed first:mt-0 last:mb-0">
            {children}
        </p>
    ),
    blockquote: ({ node, children, ...props }) => (
        <blockquote
            {...props}
            className="my-3 border-l-2 border-line pl-3 text-muted"
        >
            {children}
        </blockquote>
    ),
    hr: ({ node, ...props }) => <hr {...props} className="my-4 border-line" />,
    strong: ({ node, children, ...props }) => (
        <strong {...props} className="font-semibold text-ink">
            {children}
        </strong>
    ),
};

/**
 * Rend `text` en Markdown GFM (listes, tables, liens, gras, code inline/bloc)
 * avec coloration syntaxique. Entièrement tokenisé (clair/sombre), sans
 * débordement horizontal, et robuste au streaming (texte qui s'allonge).
 */
export default function MarkdownMessage({ text, className }) {
    return (
        <div
            className={twMerge(
                'min-w-0 max-w-full break-words text-[15px] text-ink',
                className
            )}
        >
            <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                rehypePlugins={[rehypeHighlight]}
                components={components}
            >
                {text || ''}
            </ReactMarkdown>
        </div>
    );
}

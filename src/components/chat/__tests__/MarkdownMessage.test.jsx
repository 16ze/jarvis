import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import MarkdownMessage from '../MarkdownMessage.jsx';

describe('MarkdownMessage', () => {
    it('rend un titre markdown en vrai heading', () => {
        render(<MarkdownMessage text={'# Bonjour Ada'} />);
        const heading = screen.getByRole('heading', { name: 'Bonjour Ada' });
        expect(heading).toBeInTheDocument();
        expect(heading.tagName).toBe('H1');
    });

    it('rend une liste à puces avec ses items', () => {
        render(<MarkdownMessage text={'- premier\n- second\n- troisième'} />);
        const items = screen.getAllByRole('listitem');
        expect(items).toHaveLength(3);
        expect(items[0]).toHaveTextContent('premier');
        expect(items[2]).toHaveTextContent('troisième');
    });

    it('rend un bloc de code avec un bouton copier', () => {
        const { container } = render(
            <MarkdownMessage text={'```js\nconst a = 1;\n```'} />
        );
        // Le bloc <pre> est présent et contient le code (la coloration
        // syntaxique découpe le texte en plusieurs <span>, d'où le textContent).
        const pre = container.querySelector('pre');
        expect(pre).toBeInTheDocument();
        expect(pre).toHaveTextContent('const a = 1;');
        // Le bouton copier existe (aria-label "Copier le code")
        const copyBtn = screen.getByRole('button', { name: 'Copier le code' });
        expect(copyBtn).toBeInTheDocument();
    });

    it('rend sans crash avec un texte vide', () => {
        const { container } = render(<MarkdownMessage text={''} />);
        expect(container.firstChild).toBeInTheDocument();
    });

    describe('bouton copier du bloc de code', () => {
        beforeEach(() => {
            Object.assign(navigator, {
                clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
            });
        });

        it('copie le contenu du bloc de code dans le presse-papiers', async () => {
            render(<MarkdownMessage text={'```\nhello world\n```'} />);
            const copyBtn = screen.getByRole('button', { name: 'Copier le code' });
            fireEvent.click(copyBtn);
            await waitFor(() => {
                expect(navigator.clipboard.writeText).toHaveBeenCalledTimes(1);
            });
            // Le texte copié contient le code du bloc
            expect(navigator.clipboard.writeText.mock.calls[0][0]).toContain(
                'hello world'
            );
        });
    });
});

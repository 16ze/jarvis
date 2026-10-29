import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import MessageActions from '../MessageActions.jsx';

describe('MessageActions', () => {
    it("n'affiche pas Régénérer quand canRegenerate est faux", () => {
        render(<MessageActions onCopy={() => {}} onRegenerate={() => {}} />);
        expect(
            screen.queryByRole('button', { name: 'Régénérer la réponse' })
        ).not.toBeInTheDocument();
        // Le bouton copier est toujours présent
        expect(
            screen.getByRole('button', { name: 'Copier le message' })
        ).toBeInTheDocument();
    });

    it('affiche Régénérer quand canRegenerate est vrai', () => {
        render(
            <MessageActions onCopy={() => {}} onRegenerate={() => {}} canRegenerate />
        );
        expect(
            screen.getByRole('button', { name: 'Régénérer la réponse' })
        ).toBeInTheDocument();
    });

    it('le clic sur copier appelle onCopy', async () => {
        const onCopy = vi.fn().mockResolvedValue(undefined);
        render(<MessageActions onCopy={onCopy} onRegenerate={() => {}} />);
        fireEvent.click(screen.getByRole('button', { name: 'Copier le message' }));
        await waitFor(() => expect(onCopy).toHaveBeenCalledTimes(1));
    });

    it('le clic sur régénérer appelle onRegenerate', () => {
        const onRegenerate = vi.fn();
        render(
            <MessageActions
                onCopy={() => {}}
                onRegenerate={onRegenerate}
                canRegenerate
            />
        );
        fireEvent.click(
            screen.getByRole('button', { name: 'Régénérer la réponse' })
        );
        expect(onRegenerate).toHaveBeenCalledTimes(1);
    });
});

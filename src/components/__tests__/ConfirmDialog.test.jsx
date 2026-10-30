import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import ConfirmDialog from '../ConfirmDialog';

describe('ConfirmDialog', () => {
    it('annule avec Escape et place le focus sur Annuler', () => {
        const onCancel = vi.fn();
        render(
            <ConfirmDialog
                open
                title="Supprimer ?"
                description="Cette action est irréversible."
                onCancel={onCancel}
                onConfirm={() => {}}
            />
        );

        expect(screen.getByRole('button', { name: 'Annuler' })).toHaveFocus();
        fireEvent.keyDown(document, { key: 'Escape' });
        expect(onCancel).toHaveBeenCalledTimes(1);
    });

    it('confirme explicitement la suppression', () => {
        const onConfirm = vi.fn();
        render(
            <ConfirmDialog
                open
                title="Supprimer ?"
                description="Cette action est irréversible."
                confirmLabel="Supprimer"
                onCancel={() => {}}
                onConfirm={onConfirm}
            />
        );
        fireEvent.click(screen.getByRole('button', { name: 'Supprimer' }));
        expect(onConfirm).toHaveBeenCalledTimes(1);
    });
});

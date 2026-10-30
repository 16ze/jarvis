import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import MobileConversationDrawer from '../MobileConversationDrawer';

const conversations = [
    {
        id: 'one',
        title: 'Projet mémoire',
        messages: [{ sender: 'Bryan', text: 'Préparer le dossier client' }],
    },
    {
        id: 'two',
        title: 'Voyage',
        messages: [{ sender: 'Bryan', text: 'Hôtel à Lisbonne' }],
    },
];

describe('MobileConversationDrawer', () => {
    it('ne rend rien quand il est fermé', () => {
        render(<MobileConversationDrawer open={false} />);
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    it('recherche, sélectionne et ferme le tiroir', () => {
        const onSelect = vi.fn();
        const onClose = vi.fn();
        render(
            <MobileConversationDrawer
                open
                conversations={conversations}
                onSelect={onSelect}
                onClose={onClose}
            />
        );

        fireEvent.change(screen.getByLabelText('Rechercher dans les conversations'), {
            target: { value: 'Lisbonne' },
        });
        expect(screen.queryByText('Projet mémoire')).not.toBeInTheDocument();
        fireEvent.click(screen.getByText('Voyage'));
        expect(onSelect).toHaveBeenCalledWith('two');
        expect(onClose).toHaveBeenCalled();
    });

    it('crée une conversation puis ferme le tiroir', () => {
        const onNew = vi.fn();
        const onClose = vi.fn();
        render(
            <MobileConversationDrawer
                open
                conversations={conversations}
                onNew={onNew}
                onClose={onClose}
            />
        );
        fireEvent.click(screen.getByRole('button', { name: 'Nouvelle conversation' }));
        expect(onNew).toHaveBeenCalled();
        expect(onClose).toHaveBeenCalled();
    });

    it('verrouille les mutations pendant une génération', () => {
        render(<MobileConversationDrawer open conversations={conversations} disabled />);
        expect(screen.getByRole('button', { name: 'Nouvelle conversation' })).toBeDisabled();
        expect(screen.getByRole('button', { name: 'Projet mémoire' })).toBeDisabled();
        expect(screen.getByRole('button', { name: 'Supprimer Projet mémoire' })).toBeDisabled();
    });

    it('ferme le tiroir avec Escape', () => {
        const onClose = vi.fn();
        render(
            <MobileConversationDrawer
                open
                conversations={conversations}
                onClose={onClose}
            />
        );
        fireEvent.keyDown(document, { key: 'Escape' });
        expect(onClose).toHaveBeenCalledTimes(1);
    });
});

import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import ConversationSidebar from '../ConversationSidebar';

const conversations = [
    {
        id: 'one',
        title: 'Projet mémoire',
        messages: [{ sender: 'Bryan', text: 'Préparer le dossier client' }],
    },
    {
        id: 'two',
        title: 'Voyage Portugal',
        messages: [{ sender: 'Bryan', text: 'Trouver un hôtel à Lisbonne' }],
    },
];

describe('ConversationSidebar', () => {
    it('filtre par titre et sélectionne le bon résultat', () => {
        const onSelect = vi.fn();
        render(<ConversationSidebar conversations={conversations} onSelect={onSelect} />);

        fireEvent.change(screen.getByLabelText('Rechercher dans les conversations'), {
            target: { value: 'Portugal' },
        });
        expect(screen.queryByText('Projet mémoire')).not.toBeInTheDocument();
        fireEvent.click(screen.getByText('Voyage Portugal'));
        expect(onSelect).toHaveBeenCalledWith('two');
    });

    it('filtre par contenu et affiche le contexte correspondant', () => {
        render(<ConversationSidebar conversations={conversations} />);
        fireEvent.change(screen.getByLabelText('Rechercher dans les conversations'), {
            target: { value: 'dossier' },
        });
        expect(screen.getByText('Projet mémoire')).toBeInTheDocument();
        expect(screen.getByText('Préparer le dossier client')).toBeInTheDocument();
    });

    it('efface la recherche avec Escape', () => {
        render(<ConversationSidebar conversations={conversations} />);
        const search = screen.getByLabelText('Rechercher dans les conversations');
        fireEvent.change(search, { target: { value: 'absent' } });
        expect(screen.getByText('Aucune conversation trouvée.')).toBeInTheDocument();
        fireEvent.keyDown(search, { key: 'Escape' });
        expect(screen.getByText('Projet mémoire')).toBeInTheDocument();
    });

    it('distingue une liste vide d’une recherche sans résultat', () => {
        const { rerender } = render(<ConversationSidebar conversations={[]} />);
        expect(screen.getByText('Aucune conversation.')).toBeInTheDocument();

        rerender(<ConversationSidebar conversations={conversations} />);
        fireEvent.change(screen.getByLabelText('Rechercher dans les conversations'), {
            target: { value: 'introuvable' },
        });
        expect(screen.getByText('Aucune conversation trouvée.')).toBeInTheDocument();
    });

    it('marque la conversation active et masque la recherche quand la barre est repliée', () => {
        const { rerender } = render(
            <ConversationSidebar conversations={conversations} activeId="one" />
        );
        expect(screen.getByRole('button', { name: 'Projet mémoire' })).toHaveAttribute('aria-current', 'page');

        rerender(<ConversationSidebar conversations={conversations} collapsed />);
        expect(screen.queryByLabelText('Rechercher dans les conversations')).not.toBeInTheDocument();
    });

    it('annule un renommage avec Escape sans appeler onRename', () => {
        const onRename = vi.fn();
        render(<ConversationSidebar conversations={conversations} onRename={onRename} />);

        fireEvent.click(screen.getByRole('button', { name: 'Renommer Projet mémoire' }));
        const editor = screen.getByDisplayValue('Projet mémoire');
        fireEvent.change(editor, { target: { value: 'Nouveau titre' } });
        fireEvent.keyDown(editor, { key: 'Escape' });

        expect(onRename).not.toHaveBeenCalled();
        expect(screen.queryByDisplayValue('Nouveau titre')).not.toBeInTheDocument();
    });
});

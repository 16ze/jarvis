import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import EditableUserMessage from '../EditableUserMessage';

describe('EditableUserMessage', () => {
    it('ouvre un éditeur prérempli puis annule avec Escape', () => {
        const onSave = vi.fn();
        render(<EditableUserMessage text="Bonjour" onSave={onSave} />);

        fireEvent.click(screen.getByRole('button', { name: 'Modifier le message' }));
        const editor = screen.getByRole('textbox', { name: 'Modifier le message' });
        expect(editor).toHaveValue('Bonjour');

        fireEvent.change(editor, { target: { value: 'Texte modifié' } });
        fireEvent.keyDown(editor, { key: 'Escape' });
        expect(screen.queryByRole('textbox', { name: 'Modifier le message' })).not.toBeInTheDocument();
        expect(onSave).not.toHaveBeenCalled();
    });

    it('enregistre le texte nettoyé avec Enter', () => {
        const onSave = vi.fn(() => true);
        render(<EditableUserMessage text="Bonjour" onSave={onSave} />);

        fireEvent.click(screen.getByRole('button', { name: 'Modifier le message' }));
        const editor = screen.getByRole('textbox', { name: 'Modifier le message' });
        fireEvent.change(editor, { target: { value: '  Nouveau message  ' } });
        fireEvent.keyDown(editor, { key: 'Enter', shiftKey: false });

        expect(onSave).toHaveBeenCalledWith('Nouveau message');
        expect(screen.queryByRole('textbox', { name: 'Modifier le message' })).not.toBeInTheDocument();
    });

    it('garde Shift+Enter pour les messages multilignes', () => {
        const onSave = vi.fn();
        render(<EditableUserMessage text="Bonjour" onSave={onSave} />);
        fireEvent.click(screen.getByRole('button', { name: 'Modifier le message' }));
        fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Enter', shiftKey: true });
        expect(onSave).not.toHaveBeenCalled();
    });

    it('désactive la modification pendant une génération', () => {
        render(<EditableUserMessage text="Bonjour" disabled />);
        expect(screen.getByRole('button', { name: 'Modifier le message' })).toBeDisabled();
    });
});

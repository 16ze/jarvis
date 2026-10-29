import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import ChatComposer from '../ChatComposer.jsx';

describe('ChatComposer', () => {
    it('transmet une string (pas un event) à onChange', () => {
        const onChange = vi.fn();
        render(<ChatComposer value="" onChange={onChange} />);
        const textarea = screen.getByLabelText('Message pour Ada');
        fireEvent.change(textarea, { target: { value: 'coucou' } });
        expect(onChange).toHaveBeenCalledTimes(1);
        expect(onChange).toHaveBeenCalledWith('coucou');
    });

    it('Enter appelle onSend quand il y a du contenu', () => {
        const onSend = vi.fn();
        render(<ChatComposer value="salut" onChange={() => {}} onSend={onSend} />);
        const textarea = screen.getByLabelText('Message pour Ada');
        fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });
        expect(onSend).toHaveBeenCalledTimes(1);
    });

    it("Shift+Enter n'appelle pas onSend (retour à la ligne)", () => {
        const onSend = vi.fn();
        render(<ChatComposer value="salut" onChange={() => {}} onSend={onSend} />);
        const textarea = screen.getByLabelText('Message pour Ada');
        fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: true });
        expect(onSend).not.toHaveBeenCalled();
    });

    it("Enter n'appelle pas onSend quand le champ est vide", () => {
        const onSend = vi.fn();
        render(<ChatComposer value="   " onChange={() => {}} onSend={onSend} />);
        const textarea = screen.getByLabelText('Message pour Ada');
        fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });
        expect(onSend).not.toHaveBeenCalled();
    });

    it('le bouton envoyer est désactivé quand la valeur est vide', () => {
        render(<ChatComposer value="" onChange={() => {}} onSend={() => {}} />);
        const sendBtn = screen.getByRole('button', { name: 'Envoyer le message' });
        expect(sendBtn).toBeDisabled();
    });

    it('le bouton envoyer est actif quand il y a du contenu, et le clic appelle onSend', () => {
        const onSend = vi.fn();
        render(<ChatComposer value="hello" onChange={() => {}} onSend={onSend} />);
        const sendBtn = screen.getByRole('button', { name: 'Envoyer le message' });
        expect(sendBtn).toBeEnabled();
        fireEvent.click(sendBtn);
        expect(onSend).toHaveBeenCalledTimes(1);
    });

    it('affiche le bouton Stop en génération et le clic appelle onStop', () => {
        const onStop = vi.fn();
        const onSend = vi.fn();
        render(
            <ChatComposer
                value="hello"
                onChange={() => {}}
                onSend={onSend}
                onStop={onStop}
                isGenerating
            />
        );
        const stopBtn = screen.getByRole('button', {
            name: 'Arrêter la génération',
        });
        expect(stopBtn).toBeInTheDocument();
        // En génération, Enter ne déclenche pas onSend
        const textarea = screen.getByLabelText('Message pour Ada');
        fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });
        expect(onSend).not.toHaveBeenCalled();
        // Le clic sur Stop appelle onStop
        fireEvent.click(stopBtn);
        expect(onStop).toHaveBeenCalledTimes(1);
    });

    it('respecte la prop disabled', () => {
        render(
            <ChatComposer value="hello" onChange={() => {}} onSend={() => {}} disabled />
        );
        expect(screen.getByLabelText('Message pour Ada')).toBeDisabled();
        expect(
            screen.getByRole('button', { name: 'Envoyer le message' })
        ).toBeDisabled();
    });
});

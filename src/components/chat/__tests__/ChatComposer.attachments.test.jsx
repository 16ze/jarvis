import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import ChatComposer from '../ChatComposer';

function setup(props = {}) {
    const onChange = vi.fn();
    const onSend = vi.fn();
    const onStop = vi.fn();
    const onPickImage = vi.fn();
    const onClearAttachment = vi.fn();
    render(
        <ChatComposer
            value=""
            onChange={onChange}
            onSend={onSend}
            onStop={onStop}
            onPickImage={onPickImage}
            onClearAttachment={onClearAttachment}
            {...props}
        />
    );
    return { onChange, onSend, onStop, onPickImage, onClearAttachment };
}

describe('ChatComposer — pièces jointes', () => {
    it('affiche le bouton « Joindre une image »', () => {
        setup();
        expect(screen.getByLabelText('Joindre une image')).toBeInTheDocument();
    });

    it('appelle onPickImage avec le fichier choisi', () => {
        const { onPickImage } = setup();
        const file = new File(['x'], 'photo.png', { type: 'image/png' });
        const input = document.querySelector('input[type="file"]');
        fireEvent.change(input, { target: { files: [file] } });
        expect(onPickImage).toHaveBeenCalledTimes(1);
        expect(onPickImage.mock.calls[0][0].name).toBe('photo.png');
    });

    it('affiche l’aperçu et le nom quand une pièce jointe est fournie', () => {
        setup({ attachment: { name: 'capture.png', previewUrl: 'blob:preview' } });
        expect(screen.getByText('capture.png')).toBeInTheDocument();
        expect(screen.getByAltText('capture.png')).toHaveAttribute('src', 'blob:preview');
    });

    it('appelle onClearAttachment au clic sur retirer', () => {
        const { onClearAttachment } = setup({ attachment: { name: 'a.png', previewUrl: 'blob:x' } });
        fireEvent.click(screen.getByLabelText('Retirer la pièce jointe'));
        expect(onClearAttachment).toHaveBeenCalledTimes(1);
    });

    it('permet l’envoi avec une pièce jointe même sans texte', () => {
        const { onSend } = setup({ value: '', attachment: { name: 'a.png', previewUrl: 'blob:x' } });
        const sendBtn = screen.getByLabelText('Envoyer le message');
        expect(sendBtn).not.toBeDisabled();
        fireEvent.click(sendBtn);
        expect(onSend).toHaveBeenCalledTimes(1);
    });

    it('reste désactivé sans texte ni pièce jointe', () => {
        setup({ value: '' });
        expect(screen.getByLabelText('Envoyer le message')).toBeDisabled();
    });
});

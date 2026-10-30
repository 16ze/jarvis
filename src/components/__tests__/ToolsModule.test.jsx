import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import ToolsModule from '../ToolsModule.jsx';

const renderTools = (props = {}) => {
    const onToggleVideo = vi.fn();
    render(
        <ToolsModule
            isConnected
            isMuted={false}
            isVideoOn={false}
            isHandTrackingEnabled={false}
            onToggleVideo={onToggleVideo}
            {...props}
        />
    );
    return { onToggleVideo };
};

describe('ToolsModule — mode conversation', () => {
    it('ouvre le panneau sans afficher le menu radial', () => {
        renderTools();

        fireEvent.click(screen.getByRole('button', { name: 'Ouvrir les outils' }));

        expect(screen.getByRole('dialog', { name: 'Outils Ada' })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Camera' })).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Chat' })).not.toBeInTheDocument();
    });

    it('exécute une action puis referme le panneau', () => {
        const { onToggleVideo } = renderTools();
        fireEvent.click(screen.getByRole('button', { name: 'Ouvrir les outils' }));

        fireEvent.click(screen.getByRole('button', { name: 'Camera' }));

        expect(onToggleVideo).toHaveBeenCalledTimes(1);
        expect(screen.queryByRole('dialog', { name: 'Outils Ada' })).not.toBeInTheDocument();
    });

    it('se referme avec la touche Échap', () => {
        renderTools();
        fireEvent.click(screen.getByRole('button', { name: 'Ouvrir les outils' }));

        fireEvent.keyDown(document, { key: 'Escape' });

        expect(screen.queryByRole('dialog', { name: 'Outils Ada' })).not.toBeInTheDocument();
    });
});

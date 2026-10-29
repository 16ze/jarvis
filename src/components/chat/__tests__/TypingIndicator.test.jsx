import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import TypingIndicator from '../TypingIndicator.jsx';

describe('TypingIndicator', () => {
    it('rend sans crash', () => {
        const { container } = render(<TypingIndicator />);
        expect(container.firstChild).toBeInTheDocument();
    });

    it('expose un rôle status accessible', () => {
        render(<TypingIndicator />);
        const status = screen.getByRole('status', {
            name: "Ada est en train d'écrire",
        });
        expect(status).toBeInTheDocument();
    });

    it('affiche trois points', () => {
        const { container } = render(<TypingIndicator />);
        const status = container.querySelector('[role="status"]');
        expect(status.children).toHaveLength(3);
    });
});

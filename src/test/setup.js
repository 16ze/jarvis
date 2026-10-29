// Setup global pour Vitest — étend expect() avec les matchers jest-dom
// (toBeInTheDocument, toBeDisabled, etc.) et nettoie le DOM entre les tests.
import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

afterEach(() => {
    cleanup();
});

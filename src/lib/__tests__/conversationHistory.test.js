import { describe, expect, it } from 'vitest';
import {
    editMessageBranch,
    filterConversations,
    getRegenerationBranch,
} from '../conversationHistory';

const conversations = [
    {
        id: 'alpha',
        title: 'Projet mémoire',
        messages: [
            { sender: 'Bryan', text: 'Prépare le dossier client' },
            { sender: 'ADA', text: 'Voici le résumé demandé' },
        ],
    },
    {
        id: 'beta',
        title: 'Voyage',
        messages: [
            { sender: 'System', text: 'Erreur mémoire interne' },
            { sender: 'Bryan', text: 'Trouve un hôtel à Lisbonne' },
        ],
    },
];

describe('filterConversations', () => {
    it('recherche dans les titres sans tenir compte de la casse ou des accents', () => {
        expect(filterConversations(conversations, 'MEMOIRE')).toEqual([conversations[0]]);
    });

    it('recherche dans le contenu des messages', () => {
        expect(filterConversations(conversations, 'lisbonne')).toEqual([conversations[1]]);
    });

    it('ignore les messages système', () => {
        expect(filterConversations(conversations, 'interne')).toEqual([]);
    });

    it('retourne la liste d’origine pour une requête vide', () => {
        expect(filterConversations(conversations, '')).toBe(conversations);
    });
});

describe('editMessageBranch', () => {
    it('remplace le message Bryan et supprime les réponses suivantes sans muter la source', () => {
        const messages = [
            { sender: 'Bryan', text: 'Ancien texte', time: '10:00' },
            { sender: 'ADA', text: 'Ancienne réponse', time: '10:01' },
        ];

        const result = editMessageBranch(messages, 0, '  Nouveau texte  ');

        expect(result).toEqual([
            { sender: 'Bryan', text: 'Nouveau texte', time: '10:00', edited: true },
        ]);
        expect(messages).toHaveLength(2);
        expect(messages[0].text).toBe('Ancien texte');
    });

    it('refuse un index invalide, un message Ada ou un texte vide', () => {
        const messages = [{ sender: 'ADA', text: 'Réponse' }];
        expect(editMessageBranch(messages, 3, 'Texte')).toBe(messages);
        expect(editMessageBranch(messages, 0, 'Texte')).toBe(messages);
        expect(editMessageBranch(messages, 0, '   ')).toBe(messages);
    });
});

describe('getRegenerationBranch', () => {
    it('tronque le fil au dernier message Bryan', () => {
        const messages = [
            { sender: 'Bryan', text: 'Question' },
            { sender: 'ADA', text: 'Réponse' },
        ];
        expect(getRegenerationBranch(messages)).toEqual({
            messages: [messages[0]],
            prompt: 'Question',
        });
    });
});

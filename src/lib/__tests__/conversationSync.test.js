import { describe, expect, it, vi } from 'vitest';
import {
    ConversationSyncError,
    MAX_SYNC_CONVERSATIONS,
    MAX_SYNC_MESSAGES,
    conversationSnapshotSignature,
    getConversationDeviceId,
    mergeConversationSnapshots,
    syncConversationSnapshot,
} from '../conversationSync';

function conversation(id, updatedAt, text = id) {
    return {
        id,
        title: `Conversation ${id}`,
        updatedAt,
        messages: [{ sender: 'Bryan', text }],
    };
}

describe('getConversationDeviceId', () => {
    it('réutilise puis persiste un identifiant local sans exposer de secret', () => {
        const values = new Map();
        const storage = {
            getItem: (key) => values.get(key) || null,
            setItem: (key, value) => values.set(key, value),
        };
        const cryptoApi = { randomUUID: () => 'device-uuid' };

        expect(getConversationDeviceId(storage, cryptoApi)).toBe('device-uuid');
        expect(getConversationDeviceId(storage, { randomUUID: () => 'autre' })).toBe('device-uuid');
    });
});

describe('mergeConversationSnapshots', () => {
    it('fusionne deux historiques disjoints et les trie par date', () => {
        const result = mergeConversationSnapshots({
            localConversations: [conversation('local', 10)],
            remoteConversations: [conversation('remote', 20)],
        });
        expect(result.conversations.map(({ id }) => id)).toEqual(['remote', 'local']);
    });

    it('conserve la version la plus récente sans muter les entrées', () => {
        const local = conversation('shared', 10, 'ancien');
        const remote = conversation('shared', 20, 'récent');
        const result = mergeConversationSnapshots({
            localConversations: [local],
            remoteConversations: [remote],
        });

        expect(result.conversations[0].messages[0].text).toBe('récent');
        expect(local.messages[0].text).toBe('ancien');
        expect(result.conversations[0]).not.toBe(remote);
    });

    it('empêche une ancienne conversation supprimée de réapparaître', () => {
        const result = mergeConversationSnapshots({
            localConversations: [conversation('deleted', 10)],
            remoteTombstones: [{ id: 'deleted', deletedAt: 20 }],
        });
        expect(result.conversations).toEqual([]);
        expect(result.tombstones).toEqual([{ id: 'deleted', deletedAt: 20 }]);
    });

    it('autorise une recréation explicitement plus récente que le tombstone', () => {
        const result = mergeConversationSnapshots({
            localConversations: [conversation('reborn', 30)],
            remoteTombstones: [{ id: 'reborn', deletedAt: 20 }],
        });
        expect(result.conversations.map(({ id }) => id)).toEqual(['reborn']);
        expect(result.tombstones).toEqual([]);
    });

    it('résout une égalité de façon déterministe et limite le snapshot', () => {
        const left = conversation('same', 10, 'a');
        const right = conversation('same', 10, 'z');
        const many = Array.from(
            { length: MAX_SYNC_CONVERSATIONS + 5 },
            (_, index) => conversation(`id-${index}`, index)
        );
        const first = mergeConversationSnapshots({
            localConversations: [left, ...many],
            remoteConversations: [right],
        });
        const second = mergeConversationSnapshots({
            localConversations: [right],
            remoteConversations: [left, ...many],
        });

        expect(first.conversations).toHaveLength(MAX_SYNC_CONVERSATIONS);
        expect(conversationSnapshotSignature(first.conversations, first.tombstones))
            .toBe(conversationSnapshotSignature(second.conversations, second.tombstones));
    });

    it('préfère la version canonique distante en cas d’égalité', () => {
        const result = mergeConversationSnapshots({
            localConversations: [conversation('shared', 20, 'copie locale')],
            remoteConversations: [conversation('shared', 20, 'version serveur')],
            preferRemoteOnTie: true,
        });

        expect(result.conversations[0].messages[0].text).toBe('version serveur');
    });

    it('normalise un ancien cache dépassant 500 messages avant l’envoi', async () => {
        const oversized = conversation('legacy', 30);
        oversized.messages = Array.from(
            { length: MAX_SYNC_MESSAGES + 5 },
            (_, index) => ({ sender: 'Bryan', text: `message-${index}` })
        );
        const fetchImpl = vi.fn().mockResolvedValue({
            ok: true,
            json: async () => ({ revision: 1, conversations: [oversized], tombstones: [] }),
        });

        await syncConversationSnapshot({
            backendUrl: 'https://ada.example',
            token: 'secret-test',
            deviceId: 'mac',
            sourceId: 'tab-1',
            conversations: [oversized],
            fetchImpl,
        });

        const body = JSON.parse(fetchImpl.mock.calls[0][1].body);
        expect(body.conversations[0].messages).toHaveLength(MAX_SYNC_MESSAGES);
        expect(body.conversations[0].messages[0].text).toBe('message-5');
    });
});

describe('syncConversationSnapshot', () => {
    it('envoie le Bearer dans les headers et fusionne la réponse canonique', async () => {
        const fetchImpl = vi.fn().mockResolvedValue({
            ok: true,
            json: async () => ({
                revision: 7,
                conversations: [conversation('remote', 20)],
                tombstones: [],
            }),
        });

        const result = await syncConversationSnapshot({
            backendUrl: 'https://ada.example/',
            token: 'secret-test',
            deviceId: 'mac',
            sourceId: 'tab-1',
            conversations: [conversation('local', 10)],
            fetchImpl,
        });

        expect(fetchImpl).toHaveBeenCalledOnce();
        const [url, options] = fetchImpl.mock.calls[0];
        expect(url).toBe('https://ada.example/api/conversations/sync');
        expect(options.headers.Authorization).toBe('Bearer secret-test');
        expect(url).not.toContain('secret-test');
        expect(JSON.parse(options.body)).toMatchObject({
            deviceId: 'mac',
            sourceId: 'tab-1',
            knownRevision: 0,
        });
        expect(result.revision).toBe(7);
        expect(result.conversations.map(({ id }) => id)).toEqual(['remote', 'local']);
    });

    it('signale une panne réseau sans altérer le cache local', async () => {
        const local = [conversation('offline', 10)];
        const before = JSON.stringify(local);

        await expect(syncConversationSnapshot({
            backendUrl: 'https://ada.example',
            token: 'secret-test',
            deviceId: 'mac',
            conversations: local,
            fetchImpl: vi.fn().mockRejectedValue(new Error('offline')),
        })).rejects.toMatchObject({
            name: 'ConversationSyncError',
            retryable: true,
        });
        expect(JSON.stringify(local)).toBe(before);
    });

    it('classe une erreur d’authentification comme non rejouable', async () => {
        const fetchImpl = vi.fn().mockResolvedValue({
            ok: false,
            status: 401,
            json: async () => ({ detail: 'Token invalide' }),
        });

        try {
            await syncConversationSnapshot({
                backendUrl: 'https://ada.example',
                token: 'incorrect',
                deviceId: 'mac',
                fetchImpl,
            });
            throw new Error('La synchronisation aurait dû échouer');
        } catch (error) {
            expect(error).toBeInstanceOf(ConversationSyncError);
            expect(error.status).toBe(401);
            expect(error.retryable).toBe(false);
        }
    });

    it('laisse une erreur 400 rejouable après correction du cache', async () => {
        const fetchImpl = vi.fn().mockResolvedValue({
            ok: false,
            status: 400,
            json: async () => ({ detail: 'Payload invalide' }),
        });

        await expect(syncConversationSnapshot({
            backendUrl: 'https://ada.example',
            token: 'secret-test',
            deviceId: 'mac',
            fetchImpl,
        })).rejects.toMatchObject({ status: 400, retryable: true });
    });
});

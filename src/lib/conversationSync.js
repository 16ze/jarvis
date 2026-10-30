export const MAX_SYNC_CONVERSATIONS = 60;
export const MAX_SYNC_TOMBSTONES = 500;
export const MAX_SYNC_MESSAGES = 500;
export const MAX_SYNC_TEXT_CHARS = 100_000;

const DEVICE_ID_KEY = 'ada-device-id';
const SAFE_ID = /^[A-Za-z0-9._:-]{1,128}$/;

function asTimestamp(value) {
    const timestamp = Number(value);
    return Number.isFinite(timestamp) && timestamp >= 0 ? Math.floor(timestamp) : 0;
}

function cloneMessage(message) {
    const cloned = {
        sender: String(message?.sender || '').slice(0, 40),
        text: String(message?.text || '').slice(0, MAX_SYNC_TEXT_CHARS),
    };
    if (typeof message?.time === 'string') cloned.time = message.time.slice(0, 64);
    if (message?.edited === true) cloned.edited = true;
    return cloned;
}

function cloneConversation(conversation) {
    return {
        id: String(conversation?.id || ''),
        title: String(conversation?.title || 'Nouvelle conversation').slice(0, 200),
        updatedAt: asTimestamp(conversation?.updatedAt),
        messages: Array.isArray(conversation?.messages)
            ? conversation.messages
                .slice(-MAX_SYNC_MESSAGES)
                .filter((message) => message && typeof message === 'object' && message.sender)
                .map(cloneMessage)
            : [],
    };
}

function cloneTombstone(tombstone) {
    return {
        id: String(tombstone?.id || ''),
        deletedAt: asTimestamp(tombstone?.deletedAt),
    };
}

function stableValue(value) {
    if (Array.isArray(value)) return value.map(stableValue);
    if (!value || typeof value !== 'object') return value;

    return Object.keys(value)
        .sort()
        .reduce((result, key) => {
            result[key] = stableValue(value[key]);
            return result;
        }, {});
}

function stableStringify(value) {
    return JSON.stringify(stableValue(value));
}

function deterministicWinner(current, candidate, versionKey, preferCandidateOnTie = false) {
    if (!current) return candidate;
    const currentVersion = asTimestamp(current[versionKey]);
    const candidateVersion = asTimestamp(candidate[versionKey]);
    if (candidateVersion !== currentVersion) {
        return candidateVersion > currentVersion ? candidate : current;
    }
    if (preferCandidateOnTie) return candidate;
    return stableStringify(candidate) > stableStringify(current) ? candidate : current;
}

function normalizedSnapshot(
    conversations = [],
    tombstones = [],
    { preferLaterOnTie = false } = {}
) {
    const conversationMap = new Map();
    const tombstoneMap = new Map();

    for (const rawConversation of conversations || []) {
        const conversation = cloneConversation(rawConversation);
        if (!SAFE_ID.test(conversation.id)) continue;
        conversationMap.set(
            conversation.id,
            deterministicWinner(
                conversationMap.get(conversation.id),
                conversation,
                'updatedAt',
                preferLaterOnTie
            )
        );
    }

    for (const rawTombstone of tombstones || []) {
        const tombstone = cloneTombstone(rawTombstone);
        if (!SAFE_ID.test(tombstone.id)) continue;
        tombstoneMap.set(
            tombstone.id,
            deterministicWinner(
                tombstoneMap.get(tombstone.id),
                tombstone,
                'deletedAt',
                preferLaterOnTie
            )
        );
    }

    for (const [id, conversation] of conversationMap) {
        const tombstone = tombstoneMap.get(id);
        if (!tombstone) continue;
        if (tombstone.deletedAt >= conversation.updatedAt) {
            conversationMap.delete(id);
        } else {
            // Une modification strictement postérieure recrée explicitement le fil.
            tombstoneMap.delete(id);
        }
    }

    const normalizedConversations = [...conversationMap.values()]
        .sort((left, right) => right.updatedAt - left.updatedAt || left.id.localeCompare(right.id))
        .slice(0, MAX_SYNC_CONVERSATIONS);
    const normalizedTombstones = [...tombstoneMap.values()]
        .sort((left, right) => right.deletedAt - left.deletedAt || left.id.localeCompare(right.id))
        .slice(0, MAX_SYNC_TOMBSTONES);

    return {
        conversations: normalizedConversations,
        tombstones: normalizedTombstones,
    };
}

export function getConversationDeviceId(
    storage = globalThis.localStorage,
    cryptoApi = globalThis.crypto
) {
    let stored = null;
    try {
        stored = storage?.getItem?.(DEVICE_ID_KEY);
    } catch (_) {
        // Safari privé ou stockage désactivé : l'identifiant reste en mémoire.
    }
    if (stored && SAFE_ID.test(stored)) return stored;

    const generated = cryptoApi?.randomUUID?.()
        || `device-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
    try {
        storage?.setItem?.(DEVICE_ID_KEY, generated);
    } catch (_) {
        // Le ref React conserve cet identifiant pour toute la session courante.
    }
    return generated;
}

export function mergeConversationSnapshots({
    localConversations = [],
    localTombstones = [],
    remoteConversations = [],
    remoteTombstones = [],
    preferRemoteOnTie = false,
} = {}) {
    return normalizedSnapshot(
        [...localConversations, ...remoteConversations],
        [...localTombstones, ...remoteTombstones],
        { preferLaterOnTie: preferRemoteOnTie }
    );
}

export function conversationSnapshotSignature(conversations = [], tombstones = []) {
    const snapshot = normalizedSnapshot(conversations, tombstones);
    const byId = {
        conversations: [...snapshot.conversations].sort((a, b) => a.id.localeCompare(b.id)),
        tombstones: [...snapshot.tombstones].sort((a, b) => a.id.localeCompare(b.id)),
    };
    return stableStringify(byId);
}

export class ConversationSyncError extends Error {
    constructor(message, { status = 0, retryable = true, cause } = {}) {
        super(message, cause ? { cause } : undefined);
        this.name = 'ConversationSyncError';
        this.status = status;
        this.retryable = retryable;
    }
}

export async function syncConversationSnapshot({
    backendUrl,
    token,
    deviceId,
    sourceId = deviceId,
    conversations = [],
    tombstones = [],
    knownRevision = 0,
    fetchImpl = globalThis.fetch,
    signal,
}) {
    const localSnapshot = normalizedSnapshot(conversations, tombstones);
    const url = `${String(backendUrl || '').replace(/\/$/, '')}/api/conversations/sync`;
    const headers = { 'Content-Type': 'application/json' };
    if (token) headers.Authorization = `Bearer ${token}`;

    let response;
    try {
        response = await fetchImpl(url, {
            method: 'POST',
            headers,
            signal,
            body: JSON.stringify({
                deviceId,
                sourceId,
                conversations: localSnapshot.conversations,
                tombstones: localSnapshot.tombstones,
                knownRevision,
            }),
        });
    } catch (error) {
        throw new ConversationSyncError('Synchronisation des conversations indisponible.', {
            retryable: true,
            cause: error,
        });
    }

    if (!response.ok) {
        let detail = '';
        try {
            const payload = await response.json();
            detail = payload?.detail ? ` ${payload.detail}` : '';
        } catch (_) {
            // Une réponse non JSON conserve un message utilisateur stable.
        }
        throw new ConversationSyncError(`Synchronisation refusée (${response.status}).${detail}`, {
            status: response.status,
            retryable: ![401, 403].includes(response.status),
        });
    }

    const remoteSnapshot = await response.json();
    const merged = mergeConversationSnapshots({
        localConversations: localSnapshot.conversations,
        localTombstones: localSnapshot.tombstones,
        remoteConversations: remoteSnapshot?.conversations,
        remoteTombstones: remoteSnapshot?.tombstones,
        preferRemoteOnTie: true,
    });

    return {
        ...remoteSnapshot,
        ...merged,
        revision: asTimestamp(remoteSnapshot?.revision),
    };
}

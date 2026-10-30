export function normalizeConversationText(value = '') {
    return String(value)
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .replace(/\s+/g, ' ')
        .trim()
        .toLocaleLowerCase('fr');
}

export function filterConversations(conversations = [], query = '') {
    const normalizedQuery = normalizeConversationText(query);
    if (!normalizedQuery) return conversations;

    return conversations.filter((conversation) => {
        if (normalizeConversationText(conversation.title).includes(normalizedQuery)) {
            return true;
        }

        return (conversation.messages || []).some(
            (message) =>
                message.sender !== 'System'
                && normalizeConversationText(message.text).includes(normalizedQuery)
        );
    });
}

export function getConversationMatchSnippet(conversation, query = '') {
    const normalizedQuery = normalizeConversationText(query);
    if (!normalizedQuery) return '';
    if (normalizeConversationText(conversation?.title).includes(normalizedQuery)) return '';

    const match = (conversation?.messages || []).find(
        (message) =>
            message.sender !== 'System'
            && normalizeConversationText(message.text).includes(normalizedQuery)
    );
    return match?.text?.replace(/\s+/g, ' ').trim() || '';
}

export function editMessageBranch(messages = [], index, nextText = '') {
    const cleanText = String(nextText).trim();
    const target = messages[index];
    if (!target || target.sender !== 'Bryan' || !cleanText) return messages;

    return [
        ...messages.slice(0, index),
        { ...target, text: cleanText, edited: true },
    ];
}

export function getRegenerationBranch(messages = []) {
    const lastUserIndex = messages.findLastIndex((message) => message.sender === 'Bryan');
    if (lastUserIndex < 0) return null;

    return {
        messages: messages.slice(0, lastUserIndex + 1),
        prompt: messages[lastUserIndex].text,
    };
}

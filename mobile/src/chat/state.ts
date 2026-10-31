// The chat screen's state as plain data and a pure reducer, so it can be tested without a screen.

import type { Block, ChatResponse, HistoryMessage } from '@/api/types';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  blocks: Block[];
  at: string | null;
  status?: 'sending' | 'failed'; // only for the user's own messages
  error?: string;
}

export type CardStatus = 'confirming' | 'done' | 'cancelled' | 'failed';

export interface ChatState {
  conversationId: string | null;
  messages: ChatMessage[];
  busy: boolean; // a request is in flight
  cardStatus: Record<string, CardStatus>; // what happened to a confirmation card during this session
}

export const initialState: ChatState = { conversationId: null, messages: [], busy: false, cardStatus: {} };

export type ChatAction =
  | { type: 'historyLoaded'; conversationId: string | null; messages: HistoryMessage[] }
  | { type: 'userSent'; id: string; text: string; at: string }
  | { type: 'retryStarted'; id: string }
  | { type: 'replied'; userMessageId: string | null; assistantId: string; reply: ChatResponse; at: string }
  | { type: 'sendFailed'; id: string; error: string }
  | { type: 'confirmStarted'; token: string }
  | { type: 'confirmFinished'; token: string; assistantId: string; reply: ChatResponse; at: string }
  | { type: 'confirmFailed'; token: string; assistantId: string; error: string; at: string }
  | { type: 'notice'; assistantId: string; error: string; at: string }
  | { type: 'reset' };

const errorMessage = (id: string, error: string, at: string): ChatMessage => ({
  id,
  role: 'assistant',
  text: '',
  blocks: [{ type: 'banner', level: 'error', message: error, code: null }],
  at,
});

export function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case 'historyLoaded':
      return {
        ...state,
        conversationId: action.conversationId,
        messages: action.messages.map((m, i) => ({ id: `h${i}`, role: m.role, text: m.text, blocks: m.blocks, at: m.at })),
      };

    case 'userSent':
      return {
        ...state,
        busy: true,
        messages: [
          ...state.messages,
          { id: action.id, role: 'user', text: action.text, blocks: [], at: action.at, status: 'sending' },
        ],
      };

    case 'retryStarted':
      return {
        ...state,
        busy: true,
        messages: state.messages.map((m) => (m.id === action.id ? { ...m, status: 'sending', error: undefined } : m)),
      };

    case 'replied': {
      const sent = state.messages.map((m) => (m.id === action.userMessageId ? { ...m, status: undefined } : m));
      return {
        ...state,
        busy: false,
        conversationId: action.reply.conversation_id,
        messages: [
          ...sent,
          { id: action.assistantId, role: 'assistant', text: action.reply.text, blocks: action.reply.blocks, at: action.at },
        ],
      };
    }

    case 'sendFailed':
      return {
        ...state,
        busy: false,
        messages: state.messages.map((m) => (m.id === action.id ? { ...m, status: 'failed', error: action.error } : m)),
      };

    case 'confirmStarted':
      return { ...state, busy: true, cardStatus: { ...state.cardStatus, [action.token]: 'confirming' } };

    case 'confirmFinished': {
      // The answer carries a `result` card for this token when the backend really did (or cancelled) it.
      const result = action.reply.blocks.find(
        (b): b is Extract<Block, { type: 'result' }> => b.type === 'result' && b.token === action.token,
      );
      const status: CardStatus = !result ? 'failed' : result.status === 'cancelled' ? 'cancelled' : 'done';
      return {
        ...state,
        busy: false,
        conversationId: action.reply.conversation_id,
        cardStatus: { ...state.cardStatus, [action.token]: status },
        messages: [
          ...state.messages,
          { id: action.assistantId, role: 'assistant', text: action.reply.text, blocks: action.reply.blocks, at: action.at },
        ],
      };
    }

    case 'confirmFailed':
      return {
        ...state,
        busy: false,
        cardStatus: { ...state.cardStatus, [action.token]: 'failed' },
        messages: [...state.messages, errorMessage(action.assistantId, action.error, action.at)],
      };

    case 'notice':
      return { ...state, busy: false, messages: [...state.messages, errorMessage(action.assistantId, action.error, action.at)] };

    case 'reset':
      return initialState;
  }
}

/** Confirmations that already have an answer in the conversation (so a reloaded history shows them as used). */
export function resolvedTokens(messages: ChatMessage[]): Record<string, 'done' | 'cancelled'> {
  const resolved: Record<string, 'done' | 'cancelled'> = {};
  for (const message of messages) {
    for (const block of message.blocks) {
      if (block.type === 'result' && block.token) {
        resolved[block.token] = block.status === 'cancelled' ? 'cancelled' : 'done';
      }
    }
  }
  return resolved;
}

export type ConfirmationState = 'pending' | 'confirming' | 'done' | 'cancelled' | 'failed' | 'expired';

export function confirmationState(
  token: string,
  expiresAt: string,
  state: Pick<ChatState, 'cardStatus' | 'messages'>,
  now: number = Date.now(),
): ConfirmationState {
  const local = state.cardStatus[token];
  if (local === 'confirming') return 'confirming';
  const resolved = resolvedTokens(state.messages)[token];
  if (resolved) return resolved;
  if (local === 'failed') return 'failed';
  if (Date.parse(expiresAt) <= now) return 'expired';
  return 'pending';
}

import type { Block, ChatResponse } from '@/api/types';
import { chatReducer, confirmationState, initialState, resolvedTokens, type ChatState } from '@/chat/state';

const reply = (text: string, blocks: Block[] = [], conversationId = 'c_1'): ChatResponse => ({
  conversation_id: conversationId, text, blocks,
  meta: { request_type: 'show', outcome: 'resolved', llm_calls: 1, input_tokens: 0, output_tokens: 0, cached_tokens: 0, duration_ms: 1 },
});
const confirmationBlock = (token: string, expires = '2099-01-01T00:00:00Z'): Block => ({
  type: 'confirmation', token, action: 'remove_student', summary: 's', details: { action: 'remove_student' }, warnings: [], expires_at: expires,
});
const resultBlock = (token: string, status: 'done' | 'already_done' | 'cancelled'): Block => ({ type: 'result', status, token, result: {} });

const at = '2026-11-01T10:00:00Z';

describe('sending a message', () => {
  test('the message appears at once as "sending", then the reply arrives and the conversation id is kept', () => {
    let s = chatReducer(initialState, { type: 'userSent', id: 'u1', text: 'Покажи 4А', at });
    expect(s.busy).toBe(true);
    expect(s.messages[0]).toMatchObject({ role: 'user', text: 'Покажи 4А', status: 'sending' });

    s = chatReducer(s, { type: 'replied', userMessageId: 'u1', assistantId: 'a1', reply: reply('Вот список.'), at });
    expect(s.busy).toBe(false);
    expect(s.conversationId).toBe('c_1');
    expect(s.messages.map((m) => [m.role, m.status])).toEqual([['user', undefined], ['assistant', undefined]]);
  });

  test('a failed send is marked failed with its reason, and a retry makes it "sending" again', () => {
    let s = chatReducer(initialState, { type: 'userSent', id: 'u1', text: 'hi', at });
    s = chatReducer(s, { type: 'sendFailed', id: 'u1', error: 'Нет связи' });
    expect(s.busy).toBe(false);
    expect(s.messages[0]).toMatchObject({ status: 'failed', error: 'Нет связи' });

    s = chatReducer(s, { type: 'retryStarted', id: 'u1' });
    expect(s.busy).toBe(true);
    expect(s.messages[0]).toMatchObject({ status: 'sending', error: undefined });
  });
});

describe('history and reset', () => {
  test('a loaded history becomes messages with their cards', () => {
    const s = chatReducer(initialState, {
      type: 'historyLoaded', conversationId: 'c_9',
      messages: [{ role: 'user', text: 'a', blocks: [], at }, { role: 'assistant', text: 'b', blocks: [confirmationBlock('t')], at }],
    });
    expect(s.conversationId).toBe('c_9');
    expect(s.messages).toHaveLength(2);
    expect(s.messages[1].blocks[0].type).toBe('confirmation');
  });

  test('starting a new conversation clears everything', () => {
    const s = chatReducer({ ...initialState, conversationId: 'c_1', messages: [{ id: 'x', role: 'user', text: 'a', blocks: [], at }] }, { type: 'reset' });
    expect(s).toEqual(initialState);
  });
});

describe('confirmation cards', () => {
  const withProposal = (): ChatState =>
    chatReducer(initialState, { type: 'replied', userMessageId: null, assistantId: 'a1', reply: reply('Подтвердите?', [confirmationBlock('t1')]), at });

  test('a card starts pending and is "confirming" while the request runs', () => {
    let s = withProposal();
    expect(confirmationState('t1', '2099-01-01T00:00:00Z', s)).toBe('pending');
    s = chatReducer(s, { type: 'confirmStarted', token: 't1' });
    expect(confirmationState('t1', '2099-01-01T00:00:00Z', s)).toBe('confirming');
    expect(s.busy).toBe(true);
  });

  test('when the backend did it, the card is done', () => {
    let s = chatReducer(withProposal(), { type: 'confirmStarted', token: 't1' });
    s = chatReducer(s, { type: 'confirmFinished', token: 't1', assistantId: 'a2', reply: reply('Готово.', [resultBlock('t1', 'done')]), at });
    expect(s.cardStatus.t1).toBe('done');
    expect(confirmationState('t1', '2099-01-01T00:00:00Z', s)).toBe('done');
  });

  test('pressing Confirm twice gives "already done", which still counts as done', () => {
    let s = chatReducer(withProposal(), { type: 'confirmStarted', token: 't1' });
    s = chatReducer(s, { type: 'confirmFinished', token: 't1', assistantId: 'a2', reply: reply('Уже сделано.', [resultBlock('t1', 'already_done')]), at });
    expect(s.cardStatus.t1).toBe('done');
  });

  test('Cancel gives a cancelled card', () => {
    let s = chatReducer(withProposal(), { type: 'confirmStarted', token: 't1' });
    s = chatReducer(s, { type: 'confirmFinished', token: 't1', assistantId: 'a2', reply: reply('Отменил.', [resultBlock('t1', 'cancelled')]), at });
    expect(confirmationState('t1', '2099-01-01T00:00:00Z', s)).toBe('cancelled');
  });

  test('an answer WITHOUT a result card for this token means it was NOT done: the card is failed, never done', () => {
    let s = chatReducer(withProposal(), { type: 'confirmStarted', token: 't1' });
    s = chatReducer(s, { type: 'confirmFinished', token: 't1', assistantId: 'a2', reply: reply('Срок истёк.', []), at });
    expect(s.cardStatus.t1).toBe('failed');
    expect(confirmationState('t1', '2099-01-01T00:00:00Z', s)).toBe('failed');
  });

  test('a request error marks the card failed and adds an error banner to the chat', () => {
    let s = chatReducer(withProposal(), { type: 'confirmStarted', token: 't1' });
    s = chatReducer(s, { type: 'confirmFailed', token: 't1', assistantId: 'n1', error: 'Нет связи', at });
    expect(s.busy).toBe(false);
    expect(s.cardStatus.t1).toBe('failed');
    expect(s.messages[s.messages.length - 1].blocks[0]).toMatchObject({ type: 'banner', level: 'error', message: 'Нет связи' });
  });

  test('a card whose time has passed is expired', () => {
    const s = withProposal();
    expect(confirmationState('t1', '2026-01-01T00:00:00Z', s, Date.parse('2026-01-01T00:00:01Z'))).toBe('expired');
  });

  test('after a reload the card shows what already happened, from the result cards in the history', () => {
    const s = chatReducer(initialState, {
      type: 'historyLoaded', conversationId: 'c_1',
      messages: [
        { role: 'assistant', text: 'Подтвердите?', blocks: [confirmationBlock('t1'), confirmationBlock('t2')], at },
        { role: 'assistant', text: 'Готово.', blocks: [resultBlock('t1', 'done')], at },
        { role: 'assistant', text: 'Отменено.', blocks: [resultBlock('t2', 'cancelled')], at },
      ],
    });
    expect(resolvedTokens(s.messages)).toEqual({ t1: 'done', t2: 'cancelled' });
    expect(confirmationState('t1', '2099-01-01T00:00:00Z', s)).toBe('done');
    expect(confirmationState('t2', '2099-01-01T00:00:00Z', s)).toBe('cancelled');
  });
});

test('a notice adds an error banner and ends the busy state', () => {
  const s = chatReducer({ ...initialState, busy: true }, { type: 'notice', assistantId: 'n1', error: 'Не удалось загрузить историю', at });
  expect(s.busy).toBe(false);
  expect(s.messages[0].blocks[0]).toMatchObject({ type: 'banner', message: 'Не удалось загрузить историю' });
});

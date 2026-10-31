import { useCallback, useEffect, useLayoutEffect, useMemo, useReducer, useRef } from 'react';

import { api, friendlyMessage, isSessionExpired } from '@/api/client';
import { chatReducer, confirmationState, initialState, type ConfirmationState } from './state';

/** Everything the chat screen needs: the messages, and the actions that talk to the server. */
export function useChat(token: string, onSessionExpired: () => void) {
  const [state, dispatch] = useReducer(chatReducer, initialState);
  const stateRef = useRef(state);
  // the actions below read the latest state without being re-created
  useLayoutEffect(() => {
    stateRef.current = state;
  });
  const counter = useRef(0);
  const nextId = (prefix: string) => `${prefix}${++counter.current}`;
  const now = () => new Date().toISOString();

  // A failed request is shown to the person; an expired session sends them back to the login screen.
  const explain = useCallback(
    (error: unknown, where: 'chat' | 'history') => {
      if (isSessionExpired(error)) onSessionExpired();
      return friendlyMessage(error, where);
    },
    [onSessionExpired],
  );

  useEffect(() => {
    let cancelled = false;
    api
      .history(token)
      .then((history) => {
        if (!cancelled) dispatch({ type: 'historyLoaded', conversationId: history.conversation_id, messages: history.messages });
      })
      .catch((error) => {
        if (!cancelled) dispatch({ type: 'notice', assistantId: nextId('n'), error: explain(error, 'history'), at: now() });
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const deliver = useCallback(
    async (userMessageId: string, text: string) => {
      try {
        const reply = await api.chat(token, text, stateRef.current.conversationId);
        dispatch({ type: 'replied', userMessageId, assistantId: nextId('a'), reply, at: now() });
      } catch (error) {
        dispatch({ type: 'sendFailed', id: userMessageId, error: explain(error, 'chat') });
      }
    },
    [token, explain],
  );

  const send = useCallback(
    async (text: string) => {
      const clean = text.trim();
      if (!clean || stateRef.current.busy) return;
      const id = nextId('u');
      dispatch({ type: 'userSent', id, text: clean, at: now() });
      await deliver(id, clean);
    },
    [deliver],
  );

  const retry = useCallback(
    async (id: string) => {
      const message = stateRef.current.messages.find((m) => m.id === id);
      if (!message || stateRef.current.busy) return;
      dispatch({ type: 'retryStarted', id });
      await deliver(id, message.text);
    },
    [deliver],
  );

  const answer = useCallback(
    async (confirmationToken: string, approve: boolean) => {
      const conversationId = stateRef.current.conversationId;
      if (!conversationId || stateRef.current.busy) return;
      dispatch({ type: 'confirmStarted', token: confirmationToken });
      try {
        const reply = await api.confirm(token, conversationId, confirmationToken, approve);
        dispatch({ type: 'confirmFinished', token: confirmationToken, assistantId: nextId('a'), reply, at: now() });
      } catch (error) {
        dispatch({ type: 'confirmFailed', token: confirmationToken, assistantId: nextId('n'), error: explain(error, 'chat'), at: now() });
      }
    },
    [token, explain],
  );

  const newConversation = useCallback(() => dispatch({ type: 'reset' }), []);

  const confirmationOf = useCallback(
    (confirmationToken: string, expiresAt: string): ConfirmationState => confirmationState(confirmationToken, expiresAt, state),
    [state],
  );

  return useMemo(
    () => ({ state, send, retry, answer, newConversation, confirmationOf }),
    [state, send, retry, answer, newConversation, confirmationOf],
  );
}

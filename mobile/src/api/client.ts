import type { ChatResponse, HistoryResponse, LoginResponse, Profile } from './types';

// iOS simulator and web: localhost works. A real phone needs the laptop's address, e.g. http://192.168.0.101:8000
export const API_URL = (process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000').replace(/\/$/, '');

const TIMEOUT_MS = 100_000; // the server itself stops a chat request after 90 s

export class ApiError extends Error {
  constructor(
    public readonly status: number, // 0 = no answer from the server at all
    public readonly code: string,
    message: string,
    public readonly details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

type RequestOptions = { method?: 'GET' | 'POST'; body?: unknown; token?: string | null };

function toApiError(status: number, data: unknown): ApiError {
  const body = data as { error?: { code?: string; message?: string; details?: Record<string, unknown> }; detail?: unknown } | null;
  if (body?.error) {
    return new ApiError(status, body.error.code ?? 'error', body.error.message ?? 'Error', body.error.details ?? {});
  }
  if (status === 422 || Array.isArray(body?.detail)) {
    return new ApiError(status, 'invalid_request', 'Invalid input');
  }
  return new ApiError(status, status >= 500 ? 'server_error' : 'error', `HTTP ${status}`);
}

async function request<T>(path: string, { method = 'GET', body, token }: RequestOptions = {}): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      method,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
  } catch {
    throw controller.signal.aborted
      ? new ApiError(0, 'timeout', 'The server took too long to answer')
      : new ApiError(0, 'network', 'Could not reach the server');
  } finally {
    clearTimeout(timer);
  }

  const text = await response.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    // not JSON (a proxy error page, for example): handled below by the status code
  }
  if (response.ok) return data as T;
  throw toApiError(response.status, data);
}

export const api = {
  login: (email: string, password: string) =>
    request<LoginResponse>('/auth/login', { method: 'POST', body: { email, password } }),

  me: (token: string) => request<Profile>('/auth/me', { token }),

  chat: (token: string, message: string, conversationId: string | null) =>
    request<ChatResponse>('/chat', { method: 'POST', token, body: { message, conversation_id: conversationId } }),

  confirm: (token: string, conversationId: string, confirmationToken: string, approve: boolean) =>
    request<ChatResponse>('/chat/confirm', {
      method: 'POST',
      token,
      body: { conversation_id: conversationId, token: confirmationToken, approve },
    }),

  history: (token: string, conversationId?: string | null) =>
    request<HistoryResponse>(
      `/chat/history${conversationId ? `?conversation_id=${encodeURIComponent(conversationId)}` : ''}`,
      { token },
    ),
};

/** True when the server says the token is no longer valid (expired, or the account was removed). */
export function isSessionExpired(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}

/** A message a person can act on, in the app's language. `where` tells us what was being attempted. */
export function friendlyMessage(error: unknown, where: 'login' | 'chat' | 'history' = 'chat'): string {
  if (!(error instanceof ApiError)) return 'Что-то пошло не так. Попробуйте ещё раз.';
  if (error.code === 'network') return 'Нет связи с сервером. Проверьте интернет и адрес сервера.';
  if (error.code === 'timeout') return 'Сервер отвечает слишком долго. Попробуйте ещё раз.';
  if (error.status === 401) {
    return where === 'login' ? 'Неверный email или пароль.' : 'Сессия истекла. Войдите снова.';
  }
  if (error.status === 404) return 'Диалог не найден. Начните новый.';
  if (error.status === 409) return 'Это действие уже нельзя выполнить: срок подтверждения истёк или оно уже обработано.';
  if (error.status === 422) return 'Проверьте сообщение: от 1 до 2000 символов.';
  if (error.status >= 500) return 'На сервере что-то пошло не так. Попробуйте ещё раз.';
  return 'Не получилось выполнить запрос. Попробуйте ещё раз.';
}

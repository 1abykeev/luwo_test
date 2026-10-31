import { ApiError, api, friendlyMessage, isSessionExpired } from '@/api/client';

const jsonResponse = (status: number, body: unknown) =>
  ({ ok: status >= 200 && status < 300, status, text: async () => (body === undefined ? '' : JSON.stringify(body)) }) as Response;

let fetchMock: jest.Mock;
beforeEach(() => {
  fetchMock = jest.fn();
  globalThis.fetch = fetchMock as unknown as typeof fetch;
});
afterEach(() => jest.useRealTimers());

describe('requests', () => {
  test('login sends the credentials as JSON and no token', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { access_token: 'abc', token_type: 'bearer', user: { user_id: 6 } }));
    const result = await api.login('aigul@luwo.test', 'demo1234');

    expect(result.access_token).toBe('abc');
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('http://localhost:8000/auth/login');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ email: 'aigul@luwo.test', password: 'demo1234' });
    expect(init.headers.Authorization).toBeUndefined();
  });

  test('other calls send the token as a Bearer header', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { conversation_id: 'c_1', text: 'ok', blocks: [], meta: {} }));
    await api.chat('my-token', 'Покажи 4А', null);
    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers.Authorization).toBe('Bearer my-token');
    expect(JSON.parse(init.body)).toEqual({ message: 'Покажи 4А', conversation_id: null });
  });

  test('confirm sends the conversation, the token and the choice', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, {}));
    await api.confirm('t', 'c_1', 'tok', false);
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ conversation_id: 'c_1', token: 'tok', approve: false });
  });

  test('history asks for a given conversation, encoded, or for the latest one', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { conversation_id: null, messages: [] }));
    await api.history('t');
    await api.history('t', 'c_a b');
    expect(fetchMock.mock.calls[0][0]).toBe('http://localhost:8000/chat/history');
    expect(fetchMock.mock.calls[1][0]).toBe('http://localhost:8000/chat/history?conversation_id=c_a%20b');
  });
});

describe('errors', () => {
  test('the backend error format becomes an ApiError with code, message and details', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(409, { error: { code: 'conflict', message: 'Expired', details: { x: 1 } } }),
    );
    await expect(api.confirm('t', 'c', 'tok', true)).rejects.toMatchObject({
      status: 409, code: 'conflict', message: 'Expired', details: { x: 1 },
    });
  });

  test('a validation error from the framework becomes invalid_request', async () => {
    fetchMock.mockResolvedValue(jsonResponse(422, { detail: [{ loc: ['body', 'message'], msg: 'too short' }] }));
    await expect(api.chat('t', '', null)).rejects.toMatchObject({ status: 422, code: 'invalid_request' });
  });

  test('a non-JSON server error page is still an error, not a crash', async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 502, text: async () => '<html>Bad gateway</html>' } as Response);
    await expect(api.me('t')).rejects.toMatchObject({ status: 502, code: 'server_error' });
  });

  test('no answer from the server is a network error', async () => {
    fetchMock.mockRejectedValue(new TypeError('Network request failed'));
    await expect(api.me('t')).rejects.toMatchObject({ status: 0, code: 'network' });
  });

  test('a request that takes too long is cut off and reported as a timeout', async () => {
    jest.useFakeTimers();
    fetchMock.mockImplementation(
      (_url: string, init: RequestInit) =>
        new Promise((_resolve, reject) => init.signal!.addEventListener('abort', () => reject(new Error('aborted')))),
    );
    const pending = api.chat('t', 'hi', null);
    const assertion = expect(pending).rejects.toMatchObject({ status: 0, code: 'timeout' });
    await jest.advanceTimersByTimeAsync(100_001);
    await assertion;
  });
});

describe('messages for people', () => {
  test.each([
    [new ApiError(0, 'network', ''), 'chat', 'Нет связи'],
    [new ApiError(0, 'timeout', ''), 'chat', 'слишком долго'],
    [new ApiError(401, 'authentication_failed', ''), 'login', 'Неверный email или пароль'],
    [new ApiError(401, 'authentication_failed', ''), 'chat', 'Сессия истекла'],
    [new ApiError(404, 'not_found', ''), 'chat', 'Диалог не найден'],
    [new ApiError(409, 'conflict', ''), 'chat', 'срок подтверждения истёк'],
    [new ApiError(422, 'invalid_request', ''), 'chat', 'от 1 до 2000'],
    [new ApiError(500, 'server_error', ''), 'chat', 'На сервере'],
  ] as const)('%#: %s', (error, where, expected) => {
    expect(friendlyMessage(error, where)).toContain(expected);
  });

  test('an unknown error never leaks its text to the screen', () => {
    expect(friendlyMessage(new Error('secret internals'))).not.toContain('secret');
  });

  test('only a 401 means the session is over', () => {
    expect(isSessionExpired(new ApiError(401, 'authentication_failed', ''))).toBe(true);
    expect(isSessionExpired(new ApiError(404, 'not_found', ''))).toBe(false);
    expect(isSessionExpired(new Error('x'))).toBe(false);
  });
});

/** Demo accounts and their shared password must not ship in a real build. Demo mode is ON only when
 * the flag is exactly "true", or when the flag is unset in a development build (Expo Go). */

declare const global: { __DEV__: boolean };
const realDev = global.__DEV__;

function loadDemo(flag: string | undefined, dev: boolean) {
  jest.resetModules();
  global.__DEV__ = dev;
  if (flag === undefined) delete process.env.EXPO_PUBLIC_DEMO_MODE;
  else process.env.EXPO_PUBLIC_DEMO_MODE = flag;
  // A fresh require is the point: the flag is read when the module loads.
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  return require('@/demo') as typeof import('@/demo');
}

afterEach(() => {
  delete process.env.EXPO_PUBLIC_DEMO_MODE;
  global.__DEV__ = realDev;
});

function expectOn(demo: typeof import('@/demo')) {
  expect(demo.DEMO_MODE).toBe(true);
  expect(demo.DEMO_USERS.length).toBeGreaterThan(0);
  expect(demo.DEMO_PASSWORD).not.toBe('');
}

function expectOff(demo: typeof import('@/demo')) {
  expect(demo.DEMO_MODE).toBe(false);
  expect(demo.DEMO_USERS).toEqual([]);
  expect(demo.DEMO_PASSWORD).toBe('');
}

test('in a development build (Expo Go) demo mode is on without any setup', () => {
  expectOn(loadDemo(undefined, true));
});

test('the flag "true" turns it on, even in a release build', () => {
  expectOn(loadDemo('true', false));
});

test('a release build with no flag is OFF (fails closed)', () => {
  expectOff(loadDemo(undefined, false));
});

test.each(['false', 'False', 'FALSE', '0', '', ' false', 'no', 'flase'])('the value %p turns it off, in dev and in release', (value) => {
  expectOff(loadDemo(value, true));
  expectOff(loadDemo(value, false));
});

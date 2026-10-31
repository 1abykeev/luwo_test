// Demo accounts for reviewers (the same ones as in the README). Demo data only: a real app has no such list.
// Demo mode is ON only when EXPO_PUBLIC_DEMO_MODE is exactly "true", or when it is not set at all in a
// development build (Expo Go). Anything else, including a release build with no flag, a typo or "False",
// is OFF: the accounts and the password are replaced by empty values at build time and stay out of the bundle.

const flag = process.env.EXPO_PUBLIC_DEMO_MODE;
export const DEMO_MODE = flag === 'true' || (flag === undefined && __DEV__);

export const DEMO_PASSWORD = DEMO_MODE ? 'demo1234' : '';

export interface DemoUser {
  label: string;
  hint: string;
  email: string;
}

export const DEMO_USERS: DemoUser[] = !DEMO_MODE ? [] : [
  { label: 'Учитель', hint: 'Лицей №1 · класс 4А', email: 'aigul@luwo.test' },
  { label: 'Учитель, два класса', hint: 'Лицей №1 · 3А и 3Б', email: 'bakyt@luwo.test' },
  { label: 'Админ школы', hint: 'Лицей №1', email: 'admin1@luwo.test' },
  { label: 'Админ другой школы', hint: 'Гимназия №5', email: 'admin2@luwo.test' },
  { label: 'Суперадмин', hint: 'все школы', email: 'root@luwo.test' },
];

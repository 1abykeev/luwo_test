// Demo accounts for reviewers (the same ones as in the README). Demo data only: a real app has no such list.

export const DEMO_PASSWORD = 'demo1234';

export interface DemoUser {
  label: string;
  hint: string;
  email: string;
}

export const DEMO_USERS: DemoUser[] = [
  { label: 'Учитель', hint: 'Лицей №1 · класс 4А', email: 'aigul@luwo.test' },
  { label: 'Учитель, два класса', hint: 'Лицей №1 · 3А и 3Б', email: 'bakyt@luwo.test' },
  { label: 'Админ школы', hint: 'Лицей №1', email: 'admin1@luwo.test' },
  { label: 'Админ другой школы', hint: 'Гимназия №5', email: 'admin2@luwo.test' },
  { label: 'Суперадмин', hint: 'все школы', email: 'root@luwo.test' },
];

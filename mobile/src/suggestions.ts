import type { Role } from '@/api/types';

export interface Suggestion {
  label: string;
  /** Send this text right away... */
  send?: string;
  /** ...or put this in the input so the person can finish the sentence. */
  fill?: string;
}

const COMMON: Suggestion[] = [
  { label: 'Найти ученика', fill: 'Найди ученика ' },
  { label: 'Куда пропал ученик?', fill: 'У меня в списке нет ' },
  { label: 'Проверить тёзок', send: 'Проверьте, есть ли у нас ученики с одинаковыми именами' },
];

export function suggestionsFor(role: Role): Suggestion[] {
  switch (role) {
    case 'teacher':
      return [
        { label: 'Показать мой класс', send: 'Покажите список учеников моего класса' },
        { label: 'Добавить ученика', fill: 'Добавьте ученика ' },
        ...COMMON,
      ];
    case 'school_admin':
      return [
        { label: 'Классы школы', send: 'Покажите классы школы и кто их ведёт' },
        { label: 'Учителя школы', send: 'Покажите учителей школы и их классы' },
        { label: 'Добавить учителя', fill: 'Добавьте учителя ' },
        ...COMMON,
      ];
    case 'superadmin':
      return [
        { label: 'Все школы', send: 'Покажите все школы' },
        { label: 'Классы школы', fill: 'Покажите классы школы ' },
        { label: 'Добавить учителя', fill: 'Добавьте учителя ' },
        ...COMMON,
      ];
  }
}

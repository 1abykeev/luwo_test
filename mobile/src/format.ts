import type { ConfirmationDetails, HistoryItem, Profile, Role, Warning } from '@/api/types';

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return parts.slice(0, 2).map((part) => part[0].toUpperCase()).join('') || '?';
}

/** Russian plural: 1 ученик, 2 ученика, 5 учеников. */
export function plural(n: number, one: string, few: string, many: string): string {
  const mod100 = n % 100;
  const mod10 = n % 10;
  if (mod100 >= 11 && mod100 <= 14) return many;
  if (mod10 === 1) return one;
  if (mod10 >= 2 && mod10 <= 4) return few;
  return many;
}

export const studentsCount = (n: number) => `${n} ${plural(n, 'ученик', 'ученика', 'учеников')}`;

export function roleLabel(role: Role): string {
  return { teacher: 'Учитель', school_admin: 'Админ школы', superadmin: 'Суперадмин' }[role];
}

export function profileSubtitle(profile: Profile): string {
  const parts = [roleLabel(profile.role), profile.school_name ?? 'все школы'];
  if (profile.role === 'teacher' && profile.class_names.length > 0) parts.push(profile.class_names.join(', '));
  return parts.join(' · ');
}

export function formatTime(iso: string | null): string {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
}

const MONTHS = ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];

/** '2026-10-27' -> '27 окт' */
export function formatDate(date: string | null): string {
  const match = date?.match(/^\d{4}-(\d{2})-(\d{2})/);
  if (!match) return '';
  return `${Number(match[2])} ${MONTHS[Number(match[1]) - 1]}`;
}

/** One line of a student's history. `hidden` = a class name is missing because this user may not see it. */
export function eventLine(item: HistoryItem): { text: string; hidden: boolean } {
  const { from_class: from, to_class: to } = item;
  switch (item.action) {
    case 'student_added':
      return { text: `Добавлен(а) в ${to ?? 'класс'}`, hidden: to === null };
    case 'student_deactivated':
      return { text: `Удалён(а) из ${from ?? to ?? 'класса'}`, hidden: from === null && to === null };
    case 'student_restored':
      return { text: `Возвращён(а) в ${to ?? from ?? 'класс'}`, hidden: from === null && to === null };
    case 'student_transferred':
      return {
        text: `Переведён(а) ${from ? `из ${from}` : 'из закрытого класса'} ${to ? `в ${to}` : 'в закрытый класс'}`,
        hidden: from === null || to === null,
      };
    default:
      return { text: item.action, hidden: false };
  }
}

const TITLES: Record<string, string> = {
  add_student: 'Добавить ученика',
  remove_student: 'Удалить из класса',
  restore_student: 'Вернуть в класс',
  add_teacher: 'Добавить учителя',
  remove_teacher: 'Удалить учителя',
  assign_teacher: 'Назначить учителя',
  unassign_teacher: 'Снять учителя с класса',
};

export function confirmationTitle(details: ConfirmationDetails): string {
  if (details.action === 'transfer_students') return `Перевод в ${details.to_class ?? 'класс'}`;
  return TITLES[details.action] ?? 'Подтвердите действие';
}

export function warningText(warning: Warning): string {
  switch (warning.code) {
    case 'same_name_elsewhere': {
      const students = (warning as Extract<Warning, { code: 'same_name_elsewhere' }>).students;
      return `Есть тёзка в другом классе: ${students.map((s) => `${s.full_name} (${s.class ?? '?'})`).join(', ')}`;
    }
    case 'classes_left_without_teacher':
      return `Без учителя останутся: ${(warning as { classes: string[] }).classes.join(', ')}`;
    case 'class_left_without_teacher':
      return `Класс ${(warning as { class: string }).class} останется без учителя`;
    default:
      return 'Обратите внимание на это изменение';
  }
}

/** A short line for the "done" card, built from what the backend returned. */
export function describeResult(result: Record<string, unknown>): string {
  const moved = result.moved as { full_name: string }[] | undefined;
  const student = result.student as { full_name: string; class: string | null; status: string } | undefined;
  const teacher = result.teacher as { full_name: string } | undefined;
  if (moved) return `${studentsCount(moved.length)} → ${String(result.to_class ?? '')}`.trim();
  if (student) {
    const where = student.class ? ` · ${student.class}` : '';
    return `${student.full_name}${where} · ${student.status === 'inactive' ? 'удалён(а) из класса' : 'в списке класса'}`;
  }
  if (teacher) {
    const assigned = result.assigned_classes as string[] | undefined;
    const unassigned = result.unassigned_classes as string[] | undefined;
    if (assigned) return `${teacher.full_name}: добавлен(а)${assigned.length ? `, классы ${assigned.join(', ')}` : ''}`;
    if (unassigned) return `${teacher.full_name}: удалён(а) из школы`;
    if (result.class) return `${teacher.full_name} · ${String(result.class)}`;
  }
  return '';
}

// The server's error messages are in English (they are for logs and for the model). People see these instead.
const BANNER_TEXTS: Record<string, string> = {
  permission_denied: 'Нет доступа: это действие недоступно для вашей роли или школы.',
  internal_error: 'Сбой на сервере. Действие не выполнено.',
  llm_unavailable: 'ИИ-модель сейчас недоступна. Попробуйте ещё раз через минуту.',
  llm_timeout: 'Запрос занял слишком много времени. Попробуйте ещё раз.',
  llm_rate_limited: 'Слишком много запросов. Подождите немного и повторите.',
  llm_auth: 'Сервис ИИ настроен неверно. Сообщите администратору.',
  llm_error: 'Не удалось получить ответ от ИИ-модели.',
  too_many_steps: 'Не удалось довести запрос до конца. Попробуйте сформулировать его иначе.',
};

/** Text for an error card. Messages made by this app (code null) are already in Russian. */
export function bannerText(code: string | null, message: string): string {
  if (code && BANNER_TEXTS[code]) return BANNER_TEXTS[code];
  if (code?.startsWith('llm_')) return BANNER_TEXTS.llm_error;
  return message;
}

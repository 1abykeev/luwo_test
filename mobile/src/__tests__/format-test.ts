import {
  bannerText, confirmationTitle, describeResult, eventLine, formatDate, formatTime, initials, plural,
  profileSubtitle, studentsCount, warningText,
} from '@/format';

test('initials come from the first two words', () => {
  expect(initials('Айгуль Садыкова')).toBe('АС');
  expect(initials('  бакыт  ')).toBe('Б');
  expect(initials('')).toBe('?');
});

test.each([
  [1, 'ученик'], [2, 'ученика'], [4, 'ученика'], [5, 'учеников'], [11, 'учеников'],
  [12, 'учеников'], [21, 'ученик'], [22, 'ученика'], [25, 'учеников'], [101, 'ученик'], [0, 'учеников'],
])('plural of %i is %s', (n, word) => {
  expect(plural(n, 'ученик', 'ученика', 'учеников')).toBe(word);
  expect(studentsCount(n)).toBe(`${n} ${word}`);
});

test('the header subtitle says role, school and (for teachers) classes', () => {
  const base = { user_id: 1, full_name: 'X', school_name: 'Лицей №1', class_names: ['3А', '3Б'] };
  expect(profileSubtitle({ ...base, role: 'teacher' })).toBe('Учитель · Лицей №1 · 3А, 3Б');
  expect(profileSubtitle({ ...base, role: 'school_admin', class_names: [] })).toBe('Админ школы · Лицей №1');
  expect(profileSubtitle({ ...base, role: 'superadmin', school_name: null, class_names: [] })).toBe('Суперадмин · все школы');
});

test('dates and times are formatted for people, bad input gives an empty string', () => {
  expect(formatDate('2026-10-27')).toBe('27 окт');
  expect(formatDate('2026-01-05')).toBe('5 янв');
  expect(formatDate(null)).toBe('');
  expect(formatDate('garbage')).toBe('');
  expect(formatTime(null)).toBe('');
  expect(formatTime('not a date')).toBe('');
  expect(formatTime(new Date(2026, 9, 27, 9, 5).toISOString())).toBe('09:05');
});

describe('history lines', () => {
  test('a transfer between visible classes', () => {
    expect(eventLine({ action: 'student_transferred', date: null, from_class: '3А', to_class: '3Б' }))
      .toEqual({ text: 'Переведён(а) из 3А в 3Б', hidden: false });
  });
  test('a transfer into a class the user may not see is marked hidden and never invents a name', () => {
    const line = eventLine({ action: 'student_transferred', date: null, from_class: '4А', to_class: null });
    expect(line).toEqual({ text: 'Переведён(а) из 4А в класс вне вашего доступа', hidden: true });
  });
  test('a transfer out of a class the user may not see reads the same way', () => {
    const line = eventLine({ action: 'student_transferred', date: null, from_class: null, to_class: '4А' });
    expect(line).toEqual({ text: 'Переведён(а) из класса вне вашего доступа в 4А', hidden: true });
  });
  test('added, removed and restored', () => {
    expect(eventLine({ action: 'student_added', date: null, from_class: null, to_class: '4А' }).text).toBe('Добавлен(а) в 4А');
    expect(eventLine({ action: 'student_deactivated', date: null, from_class: '4А', to_class: '4А' }).text).toBe('Удалён(а) из 4А');
    expect(eventLine({ action: 'student_restored', date: null, from_class: '4А', to_class: '4А' }).text).toBe('Возвращён(а) в 4А');
  });
  test('an unknown action is shown as it is, not hidden', () => {
    expect(eventLine({ action: 'something_new', date: null, from_class: null, to_class: null }))
      .toEqual({ text: 'something_new', hidden: false });
  });
});

test('confirmation titles', () => {
  expect(confirmationTitle({ action: 'transfer_students', to_class: '4Б' })).toBe('Перевод в 4Б');
  expect(confirmationTitle({ action: 'remove_student' })).toBe('Удалить из класса');
  expect(confirmationTitle({ action: 'something_new' })).toBe('Подтвердите действие');
});

test('warnings are readable', () => {
  expect(warningText({ code: 'classes_left_without_teacher', classes: ['4Б'] } as never)).toBe('Без учителя останутся: 4Б');
  expect(warningText({ code: 'class_left_without_teacher', class: '3Б' } as never)).toBe('Класс 3Б останется без учителя');
  expect(warningText({ code: 'same_name_elsewhere', students: [{ id: 1, full_name: 'Алина', class: '3Б', status: 'active' }] } as never))
    .toContain('Алина (3Б)');
  expect(warningText({ code: 'brand_new_warning' })).toBe('Обратите внимание на это изменение');
});

describe('the line on a "done" card', () => {
  test('a transfer', () => {
    expect(describeResult({ moved: [{ full_name: 'a' }, { full_name: 'b' }], to_class: '4Б' })).toBe('2 ученика → 4Б');
  });
  test('a student that was added or removed', () => {
    expect(describeResult({ student: { full_name: 'Амир', class: '4А', status: 'active' } })).toContain('в списке класса');
    expect(describeResult({ student: { full_name: 'Амир', class: '4А', status: 'inactive' } })).toContain('удалён(а)');
  });
  test('teacher changes', () => {
    expect(describeResult({ teacher: { full_name: 'Асель' }, assigned_classes: ['3Б'] })).toBe('Асель: добавлен(а), классы 3Б');
    expect(describeResult({ teacher: { full_name: 'Асель' }, unassigned_classes: [] })).toBe('Асель: удалён(а) из школы');
    expect(describeResult({ teacher: { full_name: 'Асель' }, class: '3Б' })).toBe('Асель · 3Б');
  });
  test('an unknown result gives an empty line, not a crash', () => {
    expect(describeResult({})).toBe('');
  });
});

describe('error cards', () => {
  test('a known server code is shown in Russian, never the English server message', () => {
    expect(bannerText('permission_denied', 'You only have access to your own school')).toBe(
      'Нет доступа: это действие недоступно для вашей роли или школы.',
    );
    expect(bannerText('llm_timeout', 'The request took too long')).toContain('слишком много времени');
    expect(bannerText('internal_error', 'The backend failed. The requested action was NOT performed.')).toContain('не выполнено');
  });
  test('any other model problem gets the general model message', () => {
    expect(bannerText('llm_brand_new_problem', 'whatever')).toBe('Не удалось получить ответ от ИИ-модели.');
  });
  test('a message made by the app itself (no code) is shown as it is', () => {
    expect(bannerText(null, 'Нет связи с сервером.')).toBe('Нет связи с сервером.');
  });
});

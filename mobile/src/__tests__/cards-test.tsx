import { render, screen, userEvent } from '@testing-library/react-native';

import type { Block, Student } from '@/api/types';
import { CardRenderer, type CardHandlers } from '@/components/cards';
import { ConfirmationCard } from '@/components/cards/confirmation';
import { ClassRosterCard, StudentListCard } from '@/components/cards/lists';

type Of<T extends Block['type']> = Extract<Block, { type: T }>;

const student = (id: number, name: string, status: Student['status'] = 'active'): Student => ({
  id, full_name: name, class: '4А', status, school: 'Лицей №1',
});

const handlers = (over: Partial<CardHandlers> = {}): CardHandlers => ({
  onShowStudent: jest.fn(),
  onPickStudent: jest.fn(),
  onAnswer: jest.fn(),
  confirmationOf: () => 'pending',
  disabled: false,
  ...over,
});

const confirmation = (over: Partial<Of<'confirmation'>> = {}): Of<'confirmation'> => ({
  type: 'confirmation',
  token: 'tok-1',
  action: 'remove_student',
  summary: 'Remove',
  details: { action: 'remove_student', student: student(12, 'Амир Касымов') },
  warnings: [],
  expires_at: '2099-01-01T10:15:00Z',
  ...over,
});

describe('confirmation card', () => {
  test('pending: Confirm and Cancel call back with the token and the choice', async () => {
    const onAnswer = jest.fn();
    await render(<ConfirmationCard block={confirmation()} state="pending" onAnswer={onAnswer} disabled={false} />);
    const user = userEvent.setup();

    expect(screen.getByText('Амир Касымов')).toBeTruthy();
    await user.press(screen.getByRole('button', { name: 'Подтвердить' }));
    expect(onAnswer).toHaveBeenLastCalledWith('tok-1', true);
    await user.press(screen.getByRole('button', { name: 'Отмена' }));
    expect(onAnswer).toHaveBeenLastCalledWith('tok-1', false);
  });

  test.each(['done', 'cancelled', 'expired'] as const)('%s: there are no buttons, so it cannot be answered again', async (state) => {
    await render(<ConfirmationCard block={confirmation()} state={state} onAnswer={jest.fn()} disabled={false} />);
    expect(screen.queryByRole('button', { name: 'Подтвердить' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Отмена' })).toBeNull();
  });

  test('done says confirmed, cancelled says cancelled, expired says to ask again', async () => {
    const { rerender } = await render(<ConfirmationCard block={confirmation()} state="done" onAnswer={jest.fn()} disabled={false} />);
    expect(screen.getByText('✓ Подтверждено')).toBeTruthy();
    await rerender(<ConfirmationCard block={confirmation()} state="cancelled" onAnswer={jest.fn()} disabled={false} />);
    expect(screen.getByText('Отменено')).toBeTruthy();
    await rerender(<ConfirmationCard block={confirmation()} state="expired" onAnswer={jest.fn()} disabled={false} />);
    expect(screen.getByText('Срок подтверждения истёк. Повторите запрос.')).toBeTruthy();
  });

  test('while confirming, a second press does nothing', async () => {
    const onAnswer = jest.fn();
    await render(<ConfirmationCard block={confirmation()} state="confirming" onAnswer={onAnswer} disabled />);
    const user = userEvent.setup();
    await user.press(screen.getByRole('button', { name: 'Отмена' }));
    expect(onAnswer).not.toHaveBeenCalled();
  });

  test('a failed attempt says so and offers the buttons again', async () => {
    await render(<ConfirmationCard block={confirmation()} state="failed" onAnswer={jest.fn()} disabled={false} />);
    expect(screen.getByText('Не получилось. Можно попробовать ещё раз.')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Подтвердить' })).toBeTruthy();
  });

  test('a transfer lists the students with where they go, and warnings are shown', async () => {
    const block = confirmation({
      action: 'transfer_students',
      details: { action: 'transfer_students', to_class: '4Б', students: [student(1, 'Алина'), student(2, 'Амир')] },
      warnings: [{ code: 'classes_left_without_teacher', classes: ['4Б'] }],
    });
    await render(<ConfirmationCard block={block} state="pending" onAnswer={jest.fn()} disabled={false} />);
    expect(screen.getByText('Перевод в 4Б')).toBeTruthy();
    expect(screen.getAllByText('4А → 4Б')).toHaveLength(2);
    expect(screen.getByText('Без учителя останутся: 4Б')).toBeTruthy();
  });

  test('a long transfer shows the first few and counts the rest', async () => {
    const many = Array.from({ length: 7 }, (_, i) => student(i, `Ученик ${i}`));
    const block = confirmation({ action: 'transfer_students', details: { action: 'transfer_students', to_class: '4Б', students: many } });
    await render(<ConfirmationCard block={block} state="pending" onAnswer={jest.fn()} disabled={false} />);
    expect(screen.getByText('и ещё 3')).toBeTruthy();
  });
});

describe('choosing a student', () => {
  const two: Of<'student_list'> = { type: 'student_list', students: [student(1, 'Амир Жумаев'), student(2, 'Амир Касымов')] };

  test('with several results, tapping one says "this is the one I meant"', async () => {
    const h = handlers();
    await render(<StudentListCard block={two} handlers={h} />);
    await userEvent.setup().press(screen.getByRole('button', { name: 'Амир Касымов' }));
    expect(h.onPickStudent).toHaveBeenCalledWith(two.students[1]);
    expect(h.onShowStudent).not.toHaveBeenCalled();
  });

  test('with a single result, tapping it opens the student card instead', async () => {
    const h = handlers();
    await render(<StudentListCard block={{ type: 'student_list', students: [student(1, 'Алина')] }} handlers={h} />);
    await userEvent.setup().press(screen.getByRole('button', { name: 'Алина' }));
    expect(h.onShowStudent).toHaveBeenCalled();
    expect(h.onPickStudent).not.toHaveBeenCalled();
  });

  test('while a request runs the rows cannot be tapped', async () => {
    const h = handlers({ disabled: true });
    await render(<StudentListCard block={two} handlers={h} />);
    expect(screen.queryByRole('button', { name: 'Амир Касымов' })).toBeNull();
  });
});

describe('class roster', () => {
  const roster = (n: number, teachers: Of<'class_roster'>['teachers']): Of<'class_roster'> => ({
    type: 'class_roster', class: '4А', school: 'Лицей №1', teachers, count: n,
    students: Array.from({ length: n }, (_, i) => student(i + 1, `Ученик ${i + 1}`)),
  });

  test('a long class is cut and can be expanded', async () => {
    await render(<ClassRosterCard block={roster(12, null)} handlers={handlers()} />);
    expect(screen.queryByText('Ученик 12')).toBeNull();
    await userEvent.setup().press(screen.getByRole('button', { name: 'Показать всех (12)' }));
    expect(screen.getByText('Ученик 12')).toBeTruthy();
  });

  test('a teacher (who may not see assignments) gets no teacher line; an admin does', async () => {
    const { rerender } = await render(<ClassRosterCard block={roster(2, null)} handlers={handlers()} />);
    expect(screen.queryByText(/Классный руководитель|Учитель не назначен/)).toBeNull();
    await rerender(<ClassRosterCard block={roster(2, [{ id: 1, full_name: 'Айгуль Садыкова' }])} handlers={handlers()} />);
    expect(screen.getByText('Классный руководитель: Айгуль Садыкова')).toBeTruthy();
    await rerender(<ClassRosterCard block={roster(2, [])} handlers={handlers()} />);
    expect(screen.getByText('Учитель не назначен')).toBeTruthy();
  });

  test('removed students are dimmed and marked', async () => {
    const block = { ...roster(1, null), students: [student(1, 'Эрмек', 'inactive')] };
    await render(<ClassRosterCard block={block} handlers={handlers()} />);
    expect(screen.getByText('удалён')).toBeTruthy();
  });
});

describe('the card renderer', () => {
  test('a block type this app does not know is skipped, not a crash', async () => {
    const unknown = { type: 'hologram', x: 1 } as unknown as Block;
    await render(<CardRenderer block={unknown} handlers={handlers()} />);
    expect(screen.toJSON()).toBeNull();
  });

  test('an error banner is shown in Russian even though the server message is English', async () => {
    const banner: Block = { type: 'banner', level: 'error', message: 'You only have access to your own school', code: 'permission_denied' };
    await render(<CardRenderer block={banner} handlers={handlers()} />);
    expect(screen.getByText('Нет доступа: это действие недоступно для вашей роли или школы.')).toBeTruthy();
    expect(screen.queryByText(/You only have access/)).toBeNull();
  });

  test('the result card says done, already done or cancelled', async () => {
    const { rerender } = await render(<CardRenderer block={{ type: 'result', status: 'done', result: { moved: [{ full_name: 'a' }], to_class: '4Б' } }} handlers={handlers()} />);
    expect(screen.getByText('1 ученик → 4Б')).toBeTruthy();
    await rerender(<CardRenderer block={{ type: 'result', status: 'already_done', result: {} }} handlers={handlers()} />);
    expect(screen.getByText('Уже выполнено ранее')).toBeTruthy();
    await rerender(<CardRenderer block={{ type: 'result', status: 'cancelled', result: {} }} handlers={handlers()} />);
    expect(screen.getByText('Данные не менялись')).toBeTruthy();
  });
});

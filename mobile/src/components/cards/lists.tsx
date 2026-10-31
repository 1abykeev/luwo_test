import { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import type { Block, Student } from '@/api/types';
import { studentsCount } from '@/format';
import { colors, fonts, radius } from '@/theme';
import { Button, Card, Chip, Row } from '../ui';

type Of<T extends Block['type']> = Extract<Block, { type: T }>;

export interface ListHandlers {
  onShowStudent: (student: Student) => void; // "tell me about this student"
  onPickStudent: (student: Student) => void; // "this is the one I meant"
  disabled: boolean; // a request is running
}

const INITIAL_ROWS = 8;

function teacherLine(teachers: Of<'class_roster'>['teachers']): string | null {
  if (teachers === null) return null; // this user may not see assignments: say nothing
  if (teachers.length === 0) return 'Учитель не назначен';
  const names = teachers.map((t) => t.full_name).join(', ');
  return teachers.length === 1 ? `Классный руководитель: ${names}` : `Учителя: ${names}`;
}

export function ClassRosterCard({ block, handlers }: { block: Of<'class_roster'>; handlers: ListHandlers }) {
  const [expanded, setExpanded] = useState(false);
  const teacher = teacherLine(block.teachers);
  const shown = expanded ? block.students : block.students.slice(0, INITIAL_ROWS);
  return (
    <Card eyebrow={`// Класс ${block.class} · ${block.school}`} title={studentsCount(block.count)}>
      {teacher ? (
        <View style={styles.note}>
          <Text style={styles.noteText}>{teacher}</Text>
        </View>
      ) : null}
      {block.students.length === 0 ? <Text style={styles.empty}>В классе пока никого нет</Text> : null}
      {shown.map((student, index) => (
        <Row
          key={student.id}
          first={index === 0 && !teacher}
          name={student.full_name}
          title={student.full_name}
          dim={student.status === 'inactive'}
          right={student.status === 'inactive' ? <Chip label="удалён" /> : undefined}
          onPress={handlers.disabled ? undefined : () => handlers.onShowStudent(student)}
        />
      ))}
      {block.students.length > INITIAL_ROWS ? (
        <View style={styles.more}>
          <Button
            variant="ghost"
            label={expanded ? 'Свернуть' : `Показать всех (${block.students.length})`}
            onPress={() => setExpanded((value) => !value)}
          />
        </View>
      ) : null}
    </Card>
  );
}

export function ClassOverviewCard({ block }: { block: Of<'class_overview'> }) {
  const showSchool = new Set(block.classes.map((c) => c.school)).size > 1;
  return (
    <Card eyebrow="// Классы" title={`${block.classes.length} ${block.classes.length === 1 ? 'класс' : 'классов'}`}>
      {block.classes.length === 0 ? <Text style={styles.empty}>Классов нет</Text> : null}
      {block.classes.map((c, index) => (
        <Row
          key={`${c.school}-${c.name}`}
          first={index === 0}
          title={c.teachers === null ? c.name : c.teachers.length ? c.teachers.map((t) => t.full_name).join(', ') : 'Учитель не назначен'}
          subtitle={`${c.name}${showSchool ? ` · ${c.school}` : ''} · ${studentsCount(c.active_students)}`}
          right={<Chip label={c.name} tone="info" />}
          dim={c.teachers !== null && c.teachers.length === 0}
        />
      ))}
    </Card>
  );
}

export function TeacherListCard({ block }: { block: Of<'teacher_list'> }) {
  const showSchool = new Set(block.teachers.map((t) => t.school)).size > 1;
  return (
    <Card eyebrow="// Учителя" title={`${block.teachers.length} ${block.teachers.length === 1 ? 'учитель' : 'учителей'}`}>
      {block.teachers.map((t, index) => (
        <Row
          key={t.id}
          first={index === 0}
          name={t.full_name}
          title={t.full_name}
          subtitle={`${t.classes.length ? `Классы: ${t.classes.join(', ')}` : 'Без классов'}${showSchool ? ` · ${t.school}` : ''}`}
        />
      ))}
    </Card>
  );
}

export function SchoolListCard({ block }: { block: Of<'school_list'> }) {
  return (
    <Card eyebrow="// Школы" title={`${block.schools.length} ${block.schools.length === 1 ? 'школа' : 'школы'}`}>
      {block.schools.map((s, index) => (
        <Row key={s.id} first={index === 0} title={s.name} />
      ))}
    </Card>
  );
}

/** Search results. With several students it becomes a "which one?" picker. */
export function StudentListCard({ block, handlers }: { block: Of<'student_list'>; handlers: ListHandlers }) {
  const [picked, setPicked] = useState<number | null>(null);
  const choosing = block.students.length > 1;
  return (
    <Card eyebrow={choosing ? '// Выберите ученика' : '// Найдено'}>
      {block.students.length === 0 ? <Text style={styles.empty}>Никого не нашла</Text> : null}
      {block.students.map((student, index) => (
        <Row
          key={student.id}
          first={index === 0 && !choosing}
          radio={choosing}
          selected={picked === student.id}
          name={choosing ? undefined : student.full_name}
          title={student.full_name}
          subtitle={[student.class, student.school].filter(Boolean).join(' · ')}
          dim={student.status === 'inactive'}
          right={student.status === 'inactive' ? <Chip label="удалён" /> : undefined}
          onPress={
            handlers.disabled
              ? undefined
              : () => {
                  setPicked(student.id);
                  (choosing ? handlers.onPickStudent : handlers.onShowStudent)(student);
                }
          }
        />
      ))}
    </Card>
  );
}

export function DuplicatesCard({ block, handlers }: { block: Of<'duplicates'>; handlers: ListHandlers }) {
  return (
    <Card eyebrow="// Тёзки" title={block.count === 0 ? 'Дубликатов нет' : `${block.count} ${block.count === 1 ? 'имя' : 'имени'} повторяется`}>
      {block.groups.map((group) => (
        <View key={group.name} style={styles.group}>
          <Text style={styles.groupName}>{group.name}</Text>
          {group.students.map((student, index) => (
            <Row
              key={student.id}
              first={index === 0}
              name={student.full_name}
              title={student.class ?? '—'}
              subtitle={student.school ?? undefined}
              onPress={handlers.disabled ? undefined : () => handlers.onShowStudent(student)}
            />
          ))}
        </View>
      ))}
    </Card>
  );
}

const styles = StyleSheet.create({
  note: { backgroundColor: colors.fog, borderRadius: radius.small, paddingHorizontal: 10, paddingVertical: 8, marginBottom: 4 },
  noteText: { fontFamily: fonts.body, fontSize: 12.5, color: colors.steel },
  empty: { fontFamily: fonts.body, fontSize: 13, color: colors.muted, paddingVertical: 6 },
  more: { marginTop: 8, flexDirection: 'row' },
  group: { marginTop: 8 },
  groupName: { fontFamily: fonts.bodySemibold, fontSize: 13.5, color: colors.ink, marginBottom: 2 },
});

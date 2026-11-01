import { StyleSheet, Text, View } from 'react-native';

import type { Block, Finding } from '@/api/types';
import { eventLine, formatDate } from '@/format';
import { colors, fonts } from '@/theme';
import { Avatar, Card, Chip, Timeline, type TimelineItem } from '../ui';

type Of<T extends Block['type']> = Extract<Block, { type: T }>;

function toTimeline(history: Finding['history']): TimelineItem[] {
  return history.map((item) => {
    const line = eventLine(item);
    return { text: line.text, sub: formatDate(item.date) || undefined, lock: line.hidden };
  });
}

export function StudentCardView({ block }: { block: Of<'student_card'> }) {
  const { student } = block;
  return (
    <Card eyebrow="// Ученик">
      <View style={styles.head}>
        <Avatar name={student.full_name} size={44} />
        <View style={styles.headText}>
          <Text style={styles.name}>{student.full_name}</Text>
          <View style={styles.chips}>
            {student.class ? <Chip label={`Класс ${student.class}`} tone="info" /> : null}
            <Chip label={student.status === 'active' ? 'В списке' : 'Удалён'} tone={student.status === 'active' ? 'ok' : 'gray'} />
            {student.school ? <Chip label={student.school} /> : null}
          </View>
        </View>
      </View>
      {block.history.length > 0 ? (
        <>
          <Text style={styles.section}>{'// История'}</Text>
          <Timeline items={toTimeline(block.history)} />
        </>
      ) : null}
    </Card>
  );
}

const STATES: Record<Finding['state'], { label: string; tone: 'ok' | 'gray' | 'lock' }> = {
  active: { label: 'В списке', tone: 'ok' },
  deactivated: { label: 'Удалён из класса', tone: 'gray' },
  moved_out_of_your_access: { label: 'Переведён в класс вне вашего доступа', tone: 'lock' },
};

export function InvestigationCard({ block }: { block: Of<'investigation'> }) {
  return (
    <Card eyebrow="// Что показывают записи" title={block.findings.length === 0 ? 'Ничего не найдено' : undefined}>
      {block.findings.length === 0 ? <Text style={styles.empty}>Ученика с таким именем нет в доступных вам записях</Text> : null}
      {block.findings.map((finding, index) => (
        <View key={finding.student_id} style={[styles.finding, index > 0 && styles.findingBorder]}>
          <Text style={styles.name}>{finding.full_name}</Text>
          <View style={styles.chips}>
            <Chip label={STATES[finding.state].label} tone={STATES[finding.state].tone} />
            {finding.current_class ? <Chip label={`Класс ${finding.current_class}`} tone="info" /> : null}
          </View>
          <Timeline items={toTimeline(finding.history)} />
        </View>
      ))}
    </Card>
  );
}

const styles = StyleSheet.create({
  head: { flexDirection: 'row', gap: 12, alignItems: 'center', marginTop: 6 },
  headText: { flex: 1, gap: 6 },
  name: { fontFamily: fonts.bodySemibold, fontSize: 16, color: colors.ink },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 4 },
  section: { fontFamily: fonts.displayMedium, fontSize: 11.5, letterSpacing: 1.2, color: colors.teal, marginTop: 12, textTransform: 'uppercase' },
  empty: { fontFamily: fonts.body, fontSize: 13, color: colors.muted, paddingVertical: 6 },
  finding: { paddingVertical: 8 },
  findingBorder: { borderTopWidth: 1, borderTopColor: colors.line, marginTop: 6 },
});

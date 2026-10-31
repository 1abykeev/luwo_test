import { StyleSheet, Text, View } from 'react-native';

import type { Block, ConfirmationDetails } from '@/api/types';
import type { ConfirmationState } from '@/chat/state';
import { bannerText, confirmationTitle, describeResult, formatTime, warningText } from '@/format';
import { colors, fonts, radius } from '@/theme';
import { Button, Card, Chip, Row } from '../ui';

type Of<T extends Block['type']> = Extract<Block, { type: T }>;

const MAX_ROWS = 4;

/** What the pending change will do, in the same words for every kind of change. */
function Details({ details }: { details: ConfirmationDetails }) {
  const classLine = [details.class && `Класс ${details.class}`, details.school].filter(Boolean).join(' · ');
  switch (details.action) {
    case 'add_student':
      return <Row first name={details.student_name} title={details.student_name ?? ''} subtitle={classLine} />;
    case 'remove_student':
    case 'restore_student':
      return details.student ? (
        <Row
          first
          name={details.student.full_name}
          title={details.student.full_name}
          subtitle={details.action === 'remove_student' ? `${details.student.class ?? ''} · запись сохранится в истории` : details.student.class ?? undefined}
        />
      ) : null;
    case 'transfer_students': {
      const students = details.students ?? [];
      return (
        <>
          {students.slice(0, MAX_ROWS).map((student, index) => (
            <Row
              key={student.id}
              first={index === 0}
              name={student.full_name}
              title={student.full_name}
              right={<Text style={styles.arrow}>{`${student.class ?? '?'} → ${details.to_class ?? '?'}`}</Text>}
            />
          ))}
          {students.length > MAX_ROWS ? (
            <Row title={`и ещё ${students.length - MAX_ROWS}`} right={<Text style={styles.arrow}>{`→ ${details.to_class ?? '?'}`}</Text>} />
          ) : null}
        </>
      );
    }
    case 'add_teacher':
      return (
        <Row
          first
          name={details.teacher_name}
          title={details.teacher_name ?? ''}
          subtitle={[details.school, details.classes?.length ? `классы ${details.classes.join(', ')}` : null].filter(Boolean).join(' · ')}
        />
      );
    case 'remove_teacher':
      return details.teacher ? (
        <Row
          first
          name={details.teacher.full_name}
          title={details.teacher.full_name}
          subtitle={details.classes?.length ? `Классы: ${details.classes.join(', ')}` : 'Без классов'}
        />
      ) : null;
    case 'assign_teacher':
    case 'unassign_teacher':
      return details.teacher ? (
        <Row first name={details.teacher.full_name} title={details.teacher.full_name} subtitle={`Класс ${details.class ?? ''}`} />
      ) : null;
    default:
      return null;
  }
}

export function ConfirmationCard({
  block,
  state,
  onAnswer,
  disabled,
}: {
  block: Of<'confirmation'>;
  state: ConfirmationState;
  onAnswer: (token: string, approve: boolean) => void;
  disabled: boolean;
}) {
  const canAnswer = state === 'pending' || state === 'failed';
  return (
    <Card eyebrow="// Подтвердите действие" title={confirmationTitle(block.details)} outlined={state === 'pending'}>
      <Details details={block.details} />
      {block.warnings.map((warning, index) => (
        <View key={index} style={styles.warning}>
          <Text style={styles.warningText}>{warningText(warning)}</Text>
        </View>
      ))}

      {canAnswer || state === 'confirming' ? (
        <>
          {state === 'failed' ? <Text style={styles.failed}>Не получилось. Можно попробовать ещё раз.</Text> : null}
          <View style={styles.actions}>
            <Button label="Подтвердить" onPress={() => onAnswer(block.token, true)} loading={state === 'confirming'} disabled={disabled && state !== 'confirming'} />
            <Button label="Отмена" variant="ghost" flex={0.7} onPress={() => onAnswer(block.token, false)} disabled={disabled || state === 'confirming'} />
          </View>
          <Text style={styles.expiry}>{`Действует до ${formatTime(block.expires_at)}`}</Text>
        </>
      ) : null}

      {state === 'done' ? <Chip label="✓ Подтверждено" tone="ok" /> : null}
      {state === 'cancelled' ? <Chip label="Отменено" tone="gray" /> : null}
      {state === 'expired' ? <Text style={styles.expired}>Срок подтверждения истёк. Повторите запрос.</Text> : null}
    </Card>
  );
}

function Notice({ tone, title, text }: { tone: 'ok' | 'err' | 'info'; title: string; text?: string }) {
  const palette = {
    ok: { bg: colors.okBg, border: colors.okBorder, fg: colors.okText, icon: '✓', dot: colors.ok },
    err: { bg: colors.errBg, border: colors.errBorder, fg: colors.err, icon: '!', dot: colors.err },
    info: { bg: colors.fog, border: colors.line, fg: colors.steel, icon: 'i', dot: colors.muted },
  }[tone];
  return (
    <View style={[styles.notice, { backgroundColor: palette.bg, borderColor: palette.border }]} accessibilityRole="alert">
      <View style={[styles.noticeIcon, { backgroundColor: palette.dot }]}>
        <Text style={styles.noticeIconText}>{palette.icon}</Text>
      </View>
      <View style={styles.noticeBody}>
        <Text style={[styles.noticeTitle, { color: palette.fg }]}>{title}</Text>
        {text ? <Text style={[styles.noticeText, { color: palette.fg }]}>{text}</Text> : null}
      </View>
    </View>
  );
}

export function ResultCard({ block }: { block: Of<'result'> }) {
  if (block.status === 'cancelled') return <Notice tone="info" title="Отменено" text="Данные не менялись" />;
  return (
    <Notice
      tone="ok"
      title={block.status === 'already_done' ? 'Уже выполнено ранее' : 'Готово'}
      text={describeResult(block.result) || undefined}
    />
  );
}

export function BannerCard({ block }: { block: Of<'banner'> }) {
  return <Notice tone={block.level === 'error' ? 'err' : 'info'} title={block.level === 'error' ? 'Ошибка' : 'Сообщение'} text={bannerText(block.code, block.message)} />;
}

const styles = StyleSheet.create({
  arrow: { fontFamily: fonts.bodySemibold, fontSize: 12, color: colors.teal },
  warning: { backgroundColor: colors.warnBg, borderRadius: radius.small, paddingHorizontal: 10, paddingVertical: 8, marginTop: 8 },
  warningText: { fontFamily: fonts.body, fontSize: 12.5, color: colors.warn },
  actions: { flexDirection: 'row', gap: 8, marginTop: 12 },
  expiry: { fontFamily: fonts.body, fontSize: 11, color: colors.muted, textAlign: 'center', marginTop: 8 },
  failed: { fontFamily: fonts.body, fontSize: 12.5, color: colors.err, marginTop: 8 },
  expired: { fontFamily: fonts.body, fontSize: 12.5, color: colors.muted, marginTop: 8 },
  notice: { flexDirection: 'row', gap: 10, alignItems: 'flex-start', borderRadius: 18, borderWidth: 1, padding: 12, alignSelf: 'stretch' },
  noticeIcon: { width: 22, height: 22, borderRadius: 11, alignItems: 'center', justifyContent: 'center' },
  noticeIconText: { color: colors.white, fontFamily: fonts.bodySemibold, fontSize: 12 },
  noticeBody: { flex: 1 },
  noticeTitle: { fontFamily: fonts.display, fontSize: 12.5, letterSpacing: 0.8, textTransform: 'uppercase' },
  noticeText: { fontFamily: fonts.body, fontSize: 13, lineHeight: 18, marginTop: 1 },
});

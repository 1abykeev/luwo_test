import type { ReactNode } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View, type StyleProp, type ViewStyle } from 'react-native';

import { initials } from '@/format';
import { colors, fonts, radius } from '@/theme';

/** "// CAPTION" in Oswald, like the captions on luwo.ai */
export function Eyebrow({ children, color = colors.teal }: { children: ReactNode; color?: string }) {
  return <Text style={[styles.eyebrow, { color }]}>{children}</Text>;
}

export function Card({
  eyebrow,
  title,
  children,
  outlined,
  style,
}: {
  eyebrow?: string;
  title?: string;
  children?: ReactNode;
  outlined?: boolean;
  style?: StyleProp<ViewStyle>;
}) {
  return (
    <View style={[styles.card, outlined && styles.cardOutlined, style]}>
      {eyebrow ? <Eyebrow>{eyebrow}</Eyebrow> : null}
      {title ? <Text style={styles.cardTitle}>{title}</Text> : null}
      {children}
    </View>
  );
}

export type ChipTone = 'gray' | 'warn' | 'ok' | 'lock' | 'info' | 'err';

const chipColors: Record<ChipTone, { bg: string; fg: string }> = {
  gray: { bg: colors.fog, fg: colors.muted },
  warn: { bg: colors.warnBg, fg: colors.warn },
  ok: { bg: colors.okBg, fg: colors.okText },
  lock: { bg: colors.fog, fg: colors.steel },
  info: { bg: '#01c3ff22', fg: colors.steel },
  err: { bg: colors.errBg, fg: colors.err },
};

export function Chip({ label, tone = 'gray' }: { label: string; tone?: ChipTone }) {
  return (
    <View style={[styles.chip, { backgroundColor: chipColors[tone].bg }]}>
      <Text style={[styles.chipText, { color: chipColors[tone].fg }]}>{label}</Text>
    </View>
  );
}

export function Avatar({ name, size = 28, dark }: { name: string; size?: number; dark?: boolean }) {
  return (
    <View
      style={{
        width: size,
        height: size,
        borderRadius: size / 2,
        backgroundColor: dark ? colors.cyan : colors.sky,
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <Text style={{ fontFamily: fonts.displayMedium, fontSize: size * 0.4, color: dark ? colors.ink : colors.steel }}>
        {initials(name)}
      </Text>
    </View>
  );
}

/** A list row: avatar, title, small line under it, something on the right. Tappable when `onPress` is given. */
export function Row({
  name,
  title,
  subtitle,
  right,
  dim,
  selected,
  radio,
  onPress,
  first,
}: {
  name?: string;
  title: string;
  subtitle?: string;
  right?: ReactNode;
  dim?: boolean;
  selected?: boolean;
  radio?: boolean;
  onPress?: () => void;
  first?: boolean;
}) {
  const content = (
    <>
      {radio ? <View style={[styles.radio, selected && styles.radioSelected]} /> : null}
      {name ? <Avatar name={name} /> : null}
      <View style={styles.rowText}>
        <Text style={styles.rowTitle}>{title}</Text>
        {subtitle ? <Text style={styles.rowSubtitle}>{subtitle}</Text> : null}
      </View>
      {right}
    </>
  );
  const style = [styles.row, first && styles.rowFirst, dim && styles.dim, radio && styles.pick, selected && styles.pickSelected];
  if (!onPress) return <View style={style}>{content}</View>;
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [...style, pressed && styles.pressed]}
      accessibilityRole="button"
      accessibilityState={{ selected }}
      accessibilityLabel={title}
    >
      {content}
    </Pressable>
  );
}

export function Button({
  label,
  onPress,
  variant = 'primary',
  disabled,
  loading,
  flex = 1,
}: {
  label: string;
  onPress: () => void;
  variant?: 'primary' | 'ghost';
  disabled?: boolean;
  loading?: boolean;
  flex?: number;
}) {
  const primary = variant === 'primary';
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled || loading}
      accessibilityRole="button"
      accessibilityState={{ disabled: disabled || loading, busy: loading }}
      style={({ pressed }) => [
        styles.button,
        primary ? styles.buttonPrimary : styles.buttonGhost,
        { flex },
        (disabled || loading) && styles.dim,
        pressed && styles.pressed,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={colors.ink} />
      ) : (
        <Text style={[styles.buttonText, { color: primary ? colors.ink : colors.steel }]}>{label}</Text>
      )}
    </Pressable>
  );
}

export interface TimelineItem {
  text: string;
  sub?: string;
  lock?: boolean;
}

export function Timeline({ items }: { items: TimelineItem[] }) {
  return (
    <View style={styles.timeline}>
      {items.map((item, index) => (
        <View key={index} style={styles.step}>
          <View style={styles.dotColumn}>
            <View style={styles.dot} />
            {index < items.length - 1 ? <View style={styles.dotLine} /> : null}
          </View>
          <View style={styles.stepText}>
            <Text style={styles.stepTitle}>
              {item.text}
              {item.lock ? '  ' : ''}
            </Text>
            {item.lock ? <Chip label="🔒 класс скрыт" tone="lock" /> : null}
            {item.sub ? <Text style={styles.rowSubtitle}>{item.sub}</Text> : null}
          </View>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  eyebrow: { fontFamily: fonts.displayMedium, fontSize: 11.5, letterSpacing: 1.2, textTransform: 'uppercase' },
  card: {
    backgroundColor: colors.white,
    borderRadius: radius.card,
    padding: 14,
    alignSelf: 'stretch',
    shadowColor: colors.ink,
    shadowOpacity: 0.08,
    shadowRadius: 4,
    shadowOffset: { width: 0, height: 1 },
    elevation: 1,
  },
  cardOutlined: { borderWidth: 1.5, borderColor: colors.cyan },
  cardTitle: {
    fontFamily: fonts.display,
    fontSize: 21,
    letterSpacing: 0.6,
    textTransform: 'uppercase',
    color: colors.ink,
    marginTop: 2,
    marginBottom: 6,
  },
  chip: { alignSelf: 'flex-start', borderRadius: radius.pill, paddingHorizontal: 9, paddingVertical: 2 },
  chipText: { fontFamily: fonts.bodySemibold, fontSize: 10.5, letterSpacing: 0.4, textTransform: 'uppercase' },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingVertical: 8,
    borderTopWidth: 1,
    borderTopColor: colors.line,
  },
  rowFirst: { borderTopWidth: 0 },
  rowText: { flex: 1, minWidth: 0 },
  rowTitle: { fontFamily: fonts.body, fontSize: 14, color: colors.ink },
  rowSubtitle: { fontFamily: fonts.body, fontSize: 11.5, color: colors.muted, marginTop: 1 },
  dim: { opacity: 0.5 },
  pressed: { opacity: 0.75 },
  pick: {
    borderWidth: 1.5,
    borderColor: colors.line,
    borderTopWidth: 1.5,
    borderTopColor: colors.line,
    borderRadius: 16,
    paddingHorizontal: 12,
    marginTop: 8,
  },
  pickSelected: { borderColor: colors.cyan, backgroundColor: '#01c3ff14', borderTopColor: colors.cyan },
  radio: { width: 18, height: 18, borderRadius: 9, borderWidth: 2, borderColor: colors.line },
  radioSelected: { borderColor: colors.cyan, backgroundColor: colors.cyan },
  button: { borderRadius: radius.pill, paddingVertical: 12, paddingHorizontal: 16, alignItems: 'center', justifyContent: 'center', minHeight: 44 },
  buttonPrimary: { backgroundColor: colors.cyan },
  buttonGhost: { borderWidth: 1.5, borderColor: colors.line },
  buttonText: { fontFamily: fonts.display, fontSize: 13, letterSpacing: 1, textTransform: 'uppercase' },
  timeline: { marginTop: 6, paddingLeft: 2 },
  step: { flexDirection: 'row', gap: 10, paddingVertical: 4 },
  dotColumn: { width: 10, alignItems: 'center' },
  dot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.cyan, marginTop: 5 },
  dotLine: { width: 2, flex: 1, backgroundColor: colors.line, marginTop: 2, minHeight: 18 },
  stepText: { flex: 1, gap: 3 },
  stepTitle: { fontFamily: fonts.body, fontSize: 13, color: colors.ink },
});

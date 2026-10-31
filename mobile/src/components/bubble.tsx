import { useEffect, useState } from 'react';
import { Animated, Easing, Platform, Pressable, StyleSheet, Text, View } from 'react-native';

import { formatTime } from '@/format';
import type { ChatMessage } from '@/chat/state';
import { colors, fonts, radius } from '@/theme';
import { CardRenderer, type CardHandlers } from './cards';

export function MessageBubble({
  message,
  handlers,
  onRetry,
}: {
  message: ChatMessage;
  handlers: CardHandlers;
  onRetry: (id: string) => void;
}) {
  const mine = message.role === 'user';
  const time = formatTime(message.at);
  return (
    <View style={[styles.row, mine && styles.rowMine]}>
      {message.text ? (
        <View style={[styles.bubble, mine ? styles.bubbleMine : styles.bubbleAgent, message.status === 'sending' && styles.sending]}>
          <Text selectable style={[styles.text, mine && styles.textMine]}>
            {message.text}
          </Text>
        </View>
      ) : null}

      {message.blocks.map((block, index) => (
        <CardRenderer key={index} block={block} handlers={handlers} />
      ))}

      {message.status === 'failed' ? (
        <Pressable onPress={() => onRetry(message.id)} accessibilityRole="button" accessibilityLabel="Повторить отправку">
          <Text style={styles.failed}>{`${message.error ?? 'Не отправлено'} · Повторить`}</Text>
        </Pressable>
      ) : time ? (
        <Text style={[styles.time, mine && styles.timeMine]}>{message.status === 'sending' ? 'отправляется…' : time}</Text>
      ) : null}
    </View>
  );
}

/** Three dots that pulse while the agent works. */
export function TypingIndicator() {
  const [dots] = useState(() => [0, 1, 2].map(() => new Animated.Value(0.3)));
  useEffect(() => {
    const loops = dots.map((dot, index) =>
      Animated.loop(
        Animated.sequence([
          Animated.delay(index * 160),
          Animated.timing(dot, { toValue: 1, duration: 360, easing: Easing.inOut(Easing.ease), useNativeDriver: Platform.OS !== 'web' }),
          Animated.timing(dot, { toValue: 0.3, duration: 360, easing: Easing.inOut(Easing.ease), useNativeDriver: Platform.OS !== 'web' }),
        ]),
      ),
    );
    loops.forEach((loop) => loop.start());
    return () => loops.forEach((loop) => loop.stop());
  }, [dots]);

  return (
    <View style={[styles.bubble, styles.bubbleAgent, styles.typing]} accessibilityLabel="Ассистент печатает" accessibilityRole="progressbar">
      {dots.map((opacity, index) => (
        <Animated.View key={index} style={[styles.dot, { opacity }]} />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { alignSelf: 'stretch', alignItems: 'flex-start', gap: 8 },
  rowMine: { alignItems: 'flex-end' },
  bubble: { maxWidth: '86%', paddingHorizontal: 14, paddingVertical: 10, borderRadius: radius.bubble },
  bubbleAgent: {
    backgroundColor: colors.white,
    borderBottomLeftRadius: 6,
    shadowColor: colors.ink,
    shadowOpacity: 0.07,
    shadowRadius: 2,
    shadowOffset: { width: 0, height: 1 },
    elevation: 1,
  },
  bubbleMine: { backgroundColor: colors.indigo, borderBottomRightRadius: 6 },
  sending: { opacity: 0.6 },
  text: { fontFamily: fonts.body, fontSize: 14.5, lineHeight: 21, color: colors.ink },
  textMine: { color: colors.white },
  time: { fontFamily: fonts.body, fontSize: 10.5, color: colors.muted, marginLeft: 6 },
  timeMine: { marginRight: 6 },
  failed: { fontFamily: fonts.bodyMedium, fontSize: 12, color: colors.err, marginRight: 6 },
  typing: { flexDirection: 'row', gap: 5, alignItems: 'center', paddingVertical: 14 },
  dot: { width: 7, height: 7, borderRadius: 4, backgroundColor: colors.steel },
});

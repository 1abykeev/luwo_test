import { useState } from 'react';
import { Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { Suggestion } from '@/suggestions';
import { colors, fonts, radius } from '@/theme';

const MAX_LENGTH = 2000; // the same limit as the server

export function Composer({
  busy,
  suggestions,
  onSend,
}: {
  busy: boolean;
  suggestions: Suggestion[];
  onSend: (text: string) => void;
}) {
  const [text, setText] = useState('');
  const insets = useSafeAreaInsets();
  const canSend = text.trim().length > 0 && !busy;

  const submit = () => {
    if (!canSend) return;
    onSend(text);
    setText('');
  };

  const applySuggestion = (suggestion: Suggestion) => {
    if (suggestion.send) onSend(suggestion.send);
    else setText(suggestion.fill ?? '');
  };

  return (
    <View style={styles.wrap}>
      {!busy && text.length === 0 ? (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.suggestions} keyboardShouldPersistTaps="handled">
          {suggestions.map((suggestion) => (
            <Pressable
              key={suggestion.label}
              onPress={() => applySuggestion(suggestion)}
              style={({ pressed }) => [styles.suggestion, pressed && styles.pressed]}
              accessibilityRole="button"
            >
              <Text style={styles.suggestionText}>{suggestion.label}</Text>
            </Pressable>
          ))}
        </ScrollView>
      ) : null}

      <View style={[styles.bar, { paddingBottom: Math.max(insets.bottom, 12) }]}>
        <TextInput
          value={text}
          onChangeText={setText}
          placeholder="Напишите сообщение…"
          placeholderTextColor={colors.muted}
          style={styles.input}
          multiline
          maxLength={MAX_LENGTH}
          editable={!busy}
          accessibilityLabel="Сообщение"
          onKeyPress={(event) => {
            // In the browser, Enter sends and Shift+Enter makes a new line.
            const native = event.nativeEvent as unknown as { key: string; shiftKey?: boolean };
            if (Platform.OS === 'web' && native.key === 'Enter' && !native.shiftKey) {
              event.preventDefault();
              submit();
            }
          }}
        />
        <Pressable
          onPress={submit}
          disabled={!canSend}
          style={({ pressed }) => [styles.send, !canSend && styles.sendOff, pressed && styles.pressed]}
          accessibilityRole="button"
          accessibilityLabel="Отправить"
        >
          <Text style={styles.sendText}>↑</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { backgroundColor: colors.white, borderTopWidth: 1, borderTopColor: colors.line },
  suggestions: { gap: 6, paddingHorizontal: 12, paddingTop: 10 },
  suggestion: { borderWidth: 1.5, borderColor: colors.line, backgroundColor: colors.white, borderRadius: radius.pill, paddingHorizontal: 12, paddingVertical: 6 },
  suggestionText: { fontFamily: fonts.bodyMedium, fontSize: 12.5, color: colors.steel },
  bar: { flexDirection: 'row', alignItems: 'flex-end', gap: 8, paddingHorizontal: 12, paddingTop: 10 },
  input: {
    flex: 1,
    maxHeight: 120,
    minHeight: 42,
    backgroundColor: colors.fog,
    borderRadius: 21,
    paddingHorizontal: 16,
    paddingTop: 11,
    paddingBottom: 11,
    fontFamily: fonts.body,
    fontSize: 15,
    color: colors.ink,
  },
  send: { width: 42, height: 42, borderRadius: 21, backgroundColor: colors.cyan, alignItems: 'center', justifyContent: 'center' },
  sendOff: { opacity: 0.4 },
  sendText: { fontFamily: fonts.displayBold, fontSize: 20, color: colors.ink, marginTop: -2 },
  pressed: { opacity: 0.75 },
});

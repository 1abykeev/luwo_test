import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { Suggestion } from '@/suggestions';
import { colors, fonts, radius } from '@/theme';
import { Eyebrow } from './ui';

/** Shown before the first message. */
export function EmptyState({ suggestions, onPick }: { suggestions: Suggestion[]; onPick: (suggestion: Suggestion) => void }) {
  return (
    <View style={styles.wrap}>
      <Eyebrow>{'// Чем помочь?'}</Eyebrow>
      <Text style={styles.title}>Списки учеников, учителей и классов</Text>
      <Text style={styles.body}>
        Я ИИ-ассистент Luwo. Покажу списки, добавлю или переведу учеников, найду тёзок и разберусь, куда пропал ученик. Любое изменение
        сначала покажу на карточке и выполню только после вашего подтверждения.
      </Text>
      <View style={styles.chips}>
        {suggestions.map((suggestion) => (
          <Pressable
            key={suggestion.label}
            onPress={() => onPick(suggestion)}
            style={({ pressed }) => [styles.chip, pressed && { opacity: 0.7 }]}
            accessibilityRole="button"
          >
            <Text style={styles.chipText}>{suggestion.label}</Text>
          </Pressable>
        ))}
      </View>
      <Text style={styles.kawaii}>(˶˃ᆺ˂˶)</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { alignSelf: 'stretch', padding: 8, gap: 10, alignItems: 'flex-start' },
  title: { fontFamily: fonts.display, fontSize: 26, lineHeight: 32, letterSpacing: 0.5, textTransform: 'uppercase', color: colors.ink },
  body: { fontFamily: fonts.body, fontSize: 14, lineHeight: 21, color: colors.steel },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 6 },
  chip: { backgroundColor: colors.white, borderRadius: radius.pill, paddingHorizontal: 14, paddingVertical: 8, borderWidth: 1.5, borderColor: colors.line },
  chipText: { fontFamily: fonts.bodyMedium, fontSize: 13, color: colors.steel },
  kawaii: { fontFamily: fonts.body, fontSize: 14, color: colors.muted, marginTop: 8 },
});

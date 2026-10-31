import { useState } from 'react';
import { ActivityIndicator, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { friendlyMessage } from '@/api/client';
import { Button, Eyebrow } from '@/components/ui';
import { DEMO_PASSWORD, DEMO_USERS } from '@/demo';
import { useSession } from '@/session';
import { colors, fonts, radius } from '@/theme';

export default function LoginScreen() {
  const { signIn } = useSession();
  const insets = useSafeAreaInsets();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState<string | null>(null); // which sign-in is running
  const [error, setError] = useState<string | null>(null);

  const submit = async (address: string, secret: string) => {
    if (busy) return;
    setBusy(address);
    setError(null);
    try {
      await signIn(address, secret); // the navigator moves to the chat by itself
    } catch (failure) {
      setError(friendlyMessage(failure, 'login'));
      setBusy(null);
    }
  };

  const canSubmit = email.trim().length > 0 && password.length > 0;

  return (
    <KeyboardAvoidingView style={styles.screen} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView
        contentContainerStyle={[styles.content, { paddingTop: insets.top + 48, paddingBottom: insets.bottom + 24 }]}
        keyboardShouldPersistTaps="handled"
      >
        <Text style={styles.logo}>
          LUW<Text style={styles.logoAccent}>O</Text>
        </Text>
        <Text style={styles.tag}>{'// Поддержка списков'}</Text>

        <View style={styles.form}>
          <Eyebrow color={colors.periwinkle}>{'// Вход'}</Eyebrow>
          <TextInput
            value={email}
            onChangeText={setEmail}
            placeholder="Email"
            placeholderTextColor="#ffffff80"
            style={styles.field}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="email-address"
            textContentType="username"
            accessibilityLabel="Email"
          />
          <TextInput
            value={password}
            onChangeText={setPassword}
            placeholder="Пароль"
            placeholderTextColor="#ffffff80"
            style={styles.field}
            secureTextEntry
            textContentType="password"
            onSubmitEditing={() => canSubmit && submit(email, password)}
            accessibilityLabel="Пароль"
          />
          {error ? (
            <Text style={styles.error} accessibilityRole="alert">
              {error}
            </Text>
          ) : null}
          <Button label="Войти" onPress={() => submit(email, password)} disabled={!canSubmit} loading={busy === email && busy !== null} flex={0} />
        </View>

        <View style={styles.demo}>
          <Eyebrow color={colors.periwinkle}>{'// Демо-пользователи'}</Eyebrow>
          <View style={styles.chips}>
            {DEMO_USERS.map((user) => (
              <Pressable
                key={user.email}
                onPress={() => submit(user.email, DEMO_PASSWORD)}
                disabled={busy !== null}
                style={({ pressed }) => [styles.chip, pressed && { opacity: 0.7 }, busy !== null && busy !== user.email && { opacity: 0.4 }]}
                accessibilityRole="button"
                accessibilityLabel={`Войти как: ${user.label}, ${user.hint}`}
              >
                {busy === user.email ? <ActivityIndicator color={colors.sky} size="small" /> : <Text style={styles.chipText}>{user.label}</Text>}
              </Pressable>
            ))}
          </View>
          <Text style={styles.hint}>Нажмите, чтобы войти. Пароль демо-аккаунтов: {DEMO_PASSWORD}</Text>
        </View>

        <Text style={styles.kawaii}>(˶˃ᆺ˂˶) я ИИ-ассистент</Text>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.navy },
  content: { paddingHorizontal: 26, gap: 4, flexGrow: 1 },
  logo: { fontFamily: fonts.displayBold, fontSize: 56, letterSpacing: 6, color: colors.white, lineHeight: 62 },
  logoAccent: { color: colors.cyan },
  tag: { fontFamily: fonts.display, fontSize: 13, letterSpacing: 1.6, color: colors.sky, textTransform: 'uppercase', marginTop: 4 },
  form: { marginTop: 40, gap: 12 },
  field: {
    backgroundColor: colors.indigo,
    borderWidth: 1.5,
    borderColor: '#ffffff22',
    borderRadius: radius.pill,
    paddingHorizontal: 20,
    paddingVertical: 14,
    fontFamily: fonts.body,
    fontSize: 15,
    color: colors.white,
  },
  error: { fontFamily: fonts.bodyMedium, fontSize: 13, color: '#ff8a93' },
  demo: { marginTop: 36, gap: 10 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { borderRadius: radius.pill, paddingHorizontal: 14, paddingVertical: 9, backgroundColor: '#ffffff14', minHeight: 36, justifyContent: 'center' },
  chipText: { fontFamily: fonts.bodyMedium, fontSize: 13, color: colors.sky },
  hint: { fontFamily: fonts.body, fontSize: 12, color: '#ffffff80' },
  kawaii: { marginTop: 'auto', paddingTop: 28, textAlign: 'center', fontFamily: fonts.body, fontSize: 13, color: '#ffffff66' },
});

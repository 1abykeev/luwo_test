import { useState } from 'react';
import { ActivityIndicator, Modal, Pressable, StyleSheet, Text, View } from 'react-native';

import { friendlyMessage } from '@/api/client';
import { DEMO_MODE, DEMO_PASSWORD, DEMO_USERS } from '@/demo';
import { useSession } from '@/session';
import { colors, fonts } from '@/theme';
import { Button, Eyebrow } from './ui';

/** A bottom sheet for reviewers: jump to another demo account, or sign out. */
export function UserSwitcher({ visible, currentEmail, onClose }: { visible: boolean; currentEmail: string | null; onClose: () => void }) {
  const { signIn, signOut } = useSession();
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const switchTo = async (email: string) => {
    setLoading(email);
    setError(null);
    try {
      await signIn(email, DEMO_PASSWORD);
      onClose();
    } catch (failure) {
      setError(friendlyMessage(failure, 'login'));
    } finally {
      setLoading(null);
    }
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={styles.backdrop} onPress={onClose} accessibilityLabel="Закрыть" />
      <View style={styles.sheet}>
        <Eyebrow>{DEMO_MODE ? '// Демо-пользователи' : '// Аккаунт'}</Eyebrow>
        <Text style={styles.title}>{DEMO_MODE ? 'Сменить пользователя' : 'Аккаунт'}</Text>
        {DEMO_USERS.map((user) => {
          const current = user.email === currentEmail;
          return (
            <Pressable
              key={user.email}
              onPress={() => (current ? onClose() : switchTo(user.email))}
              disabled={loading !== null}
              style={({ pressed }) => [styles.user, current && styles.userCurrent, pressed && { opacity: 0.7 }]}
              accessibilityRole="button"
              accessibilityState={{ selected: current }}
            >
              <View style={styles.userText}>
                <Text style={styles.userName}>{user.label}</Text>
                <Text style={styles.userHint}>{user.hint}</Text>
              </View>
              {loading === user.email ? <ActivityIndicator color={colors.steel} /> : current ? <Text style={styles.here}>сейчас</Text> : null}
            </Pressable>
          );
        })}
        {error ? <Text style={styles.error}>{error}</Text> : null}
        <View style={styles.footer}>
          <Button label="Выйти" variant="ghost" onPress={() => { onClose(); void signOut(); }} />
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: '#111a3c99' },
  sheet: { backgroundColor: colors.white, borderTopLeftRadius: 28, borderTopRightRadius: 28, padding: 20, paddingBottom: 32, gap: 8 },
  title: { fontFamily: fonts.display, fontSize: 22, letterSpacing: 0.6, textTransform: 'uppercase', color: colors.ink, marginBottom: 6 },
  user: { flexDirection: 'row', alignItems: 'center', borderWidth: 1.5, borderColor: colors.line, borderRadius: 18, paddingHorizontal: 14, paddingVertical: 12 },
  userCurrent: { borderColor: colors.cyan, backgroundColor: '#01c3ff14' },
  userText: { flex: 1 },
  userName: { fontFamily: fonts.bodySemibold, fontSize: 14.5, color: colors.ink },
  userHint: { fontFamily: fonts.body, fontSize: 12, color: colors.muted, marginTop: 1 },
  here: { fontFamily: fonts.bodySemibold, fontSize: 11, color: colors.teal, textTransform: 'uppercase', letterSpacing: 0.6 },
  error: { fontFamily: fonts.body, fontSize: 13, color: colors.err },
  footer: { flexDirection: 'row', marginTop: 8 },
});

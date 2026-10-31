import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { Profile } from '@/api/types';
import { profileSubtitle } from '@/format';
import { colors, fonts, radius } from '@/theme';
import { Avatar } from './ui';

export function Header({ profile, onNew, onSwitch }: { profile: Profile; onNew: () => void; onSwitch: () => void }) {
  return (
    <View style={styles.bar}>
      <Avatar name={profile.full_name} size={40} dark />
      <View style={styles.who}>
        <Text style={styles.name} numberOfLines={1}>
          {profile.full_name}
        </Text>
        <View style={styles.role}>
          <Text style={styles.roleText} numberOfLines={1}>
            {profileSubtitle(profile)}
          </Text>
        </View>
      </View>
      <IconButton glyph="+" label="Новый диалог" onPress={onNew} />
      <IconButton glyph="⇄" label="Сменить пользователя" onPress={onSwitch} />
    </View>
  );
}

function IconButton({ glyph, label, onPress }: { glyph: string; label: string; onPress: () => void }) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={label}
      style={({ pressed }) => [styles.icon, pressed && { opacity: 0.6 }]}
    >
      <Text style={styles.iconText}>{glyph}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  bar: { backgroundColor: colors.navy, flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 16, paddingTop: 8, paddingBottom: 14 },
  who: { flex: 1, minWidth: 0, gap: 3 },
  name: { fontFamily: fonts.bodySemibold, fontSize: 15, color: colors.white },
  role: { alignSelf: 'flex-start', maxWidth: '100%', backgroundColor: '#ffffff1f', borderRadius: radius.pill, paddingHorizontal: 9, paddingVertical: 2 },
  roleText: { fontFamily: fonts.bodySemibold, fontSize: 10.5, letterSpacing: 0.4, color: colors.sky, textTransform: 'uppercase' },
  icon: { width: 36, height: 36, borderRadius: 18, borderWidth: 1, borderColor: '#ffffff40', alignItems: 'center', justifyContent: 'center' },
  iconText: { color: colors.white, fontSize: 16, fontFamily: fonts.bodyMedium },
});

import { useMemo, useState } from 'react';
import { FlatList, KeyboardAvoidingView, Platform, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import type { Profile } from '@/api/types';
import { MessageBubble, TypingIndicator } from '@/components/bubble';
import type { CardHandlers } from '@/components/cards';
import { Composer } from '@/components/composer';
import { EmptyState } from '@/components/empty';
import { Header } from '@/components/header';
import { UserSwitcher } from '@/components/switcher';
import { useChat } from '@/chat/useChat';
import { useSession } from '@/session';
import { suggestionsFor, type Suggestion } from '@/suggestions';
import { colors } from '@/theme';

export default function ChatRoute() {
  const { state, signOut } = useSession();
  if (state.status !== 'signedIn') return null; // the navigator shows the login screen instead
  // key: a different user starts with a clean chat
  return <ChatView key={state.profile.user_id} token={state.token} profile={state.profile} email={state.email} onSessionExpired={signOut} />;
}

function ChatView({ token, profile, email, onSessionExpired }: { token: string; profile: Profile; email: string | null; onSessionExpired: () => void }) {
  const chat = useChat(token, onSessionExpired);
  const [switching, setSwitching] = useState(false);
  const suggestions = useMemo(() => suggestionsFor(profile.role), [profile.role]);
  const { state } = chat;

  const handlers: CardHandlers = {
    onShowStudent: (student) => chat.send(`Покажите карточку ученика ${student.full_name}${student.class ? `, класс ${student.class}` : ''}`),
    onPickStudent: (student) => chat.send(`Я имею в виду: ${student.full_name}${student.class ? `, класс ${student.class}` : ''}`),
    onAnswer: chat.answer,
    confirmationOf: chat.confirmationOf,
    disabled: state.busy,
  };

  const pickSuggestion = (suggestion: Suggestion) => {
    if (suggestion.send) chat.send(suggestion.send);
  };

  // The list is inverted (newest at the bottom without any scrolling code), so the data is reversed.
  const data = useMemo(() => [...state.messages].reverse(), [state.messages]);

  return (
    <SafeAreaView edges={['top']} style={styles.screen}>
      <Header profile={profile} onNew={chat.newConversation} onSwitch={() => setSwitching(true)} />
      <KeyboardAvoidingView style={styles.body} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        {state.messages.length === 0 && !state.busy ? (
          <View style={styles.empty}>
            <EmptyState suggestions={suggestions.filter((s) => s.send)} onPick={pickSuggestion} />
          </View>
        ) : (
          <FlatList
            style={styles.list}
            contentContainerStyle={styles.listContent}
            inverted
            data={data}
            extraData={state}
            keyExtractor={(message) => message.id}
            renderItem={({ item }) => <MessageBubble message={item} handlers={handlers} onRetry={chat.retry} />}
            ListHeaderComponent={state.busy ? <TypingIndicator /> : undefined}
            keyboardShouldPersistTaps="handled"
            keyboardDismissMode="on-drag"
          />
        )}
        <Composer busy={state.busy} suggestions={suggestions} onSend={chat.send} />
      </KeyboardAvoidingView>
      <UserSwitcher visible={switching} currentEmail={email} onClose={() => setSwitching(false)} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.navy },
  body: { flex: 1, backgroundColor: colors.fog },
  list: { flex: 1 },
  listContent: { padding: 12, gap: 12 },
  empty: { flex: 1, justifyContent: 'center', padding: 12 },
});

import { Inter_400Regular, Inter_500Medium, Inter_600SemiBold } from '@expo-google-fonts/inter';
import { Oswald_500Medium, Oswald_600SemiBold, Oswald_700Bold, useFonts } from '@expo-google-fonts/oswald';
import { Stack } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { SessionProvider, useSession } from '@/session';
import { colors } from '@/theme';

SplashScreen.preventAutoHideAsync();

export default function RootLayout() {
  const [fontsLoaded, fontError] = useFonts({
    Inter_400Regular,
    Inter_500Medium,
    Inter_600SemiBold,
    Oswald_500Medium,
    Oswald_600SemiBold,
    Oswald_700Bold,
  });

  if (!fontsLoaded && !fontError) return null; // the splash screen stays visible meanwhile

  return (
    <SafeAreaProvider>
      <SessionProvider>
        <StatusBar style="light" />
        <Navigator />
      </SessionProvider>
    </SafeAreaProvider>
  );
}

function Navigator() {
  const { state } = useSession();
  const ready = state.status !== 'loading';

  // Hide the splash screen only when we know whether someone is signed in: no flash of the wrong screen.
  useEffect(() => {
    if (ready) SplashScreen.hideAsync();
  }, [ready]);

  if (!ready) return null;

  const signedIn = state.status === 'signedIn';
  return (
    <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.navy } }}>
      <Stack.Protected guard={!signedIn}>
        <Stack.Screen name="login" />
      </Stack.Protected>
      <Stack.Protected guard={signedIn} redirectTo="/login">
        <Stack.Screen name="index" />
      </Stack.Protected>
    </Stack>
  );
}

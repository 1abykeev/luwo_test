import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

import type { Session } from '@/api/types';

const KEY = 'luwo.session';

// expo-secure-store has no web support, so the browser preview falls back to localStorage.
const useBrowserStorage = Platform.OS === 'web';

export async function loadSession(): Promise<Session | null> {
  try {
    const raw = useBrowserStorage ? localStorage.getItem(KEY) : await SecureStore.getItemAsync(KEY);
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null; // storage unavailable or corrupted: behave as signed out
  }
}

export async function saveSession(session: Session): Promise<void> {
  const raw = JSON.stringify(session);
  try {
    if (useBrowserStorage) localStorage.setItem(KEY, raw);
    else await SecureStore.setItemAsync(KEY, raw);
  } catch {
    // the session still works until the app closes
  }
}

export async function clearSession(): Promise<void> {
  try {
    if (useBrowserStorage) localStorage.removeItem(KEY);
    else await SecureStore.deleteItemAsync(KEY);
  } catch {
    // nothing to clear
  }
}

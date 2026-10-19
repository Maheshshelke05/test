// Tokens go to the OS keychain (SecureStore) on devices; web falls back to AsyncStorage.
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

const native = Platform.OS !== 'web';

export const getSecure = (k) => (native ? SecureStore.getItemAsync(k) : AsyncStorage.getItem(k));
export const setSecure = (k, v) => (native ? SecureStore.setItemAsync(k, v) : AsyncStorage.setItem(k, v));
export const removeSecure = (k) => (native ? SecureStore.deleteItemAsync(k) : AsyncStorage.removeItem(k));

export async function getJSON(k, fallback = null) {
  try {
    const v = await AsyncStorage.getItem(k);
    return v ? JSON.parse(v) : fallback;
  } catch {
    return fallback;
  }
}

export const setJSON = (k, v) => AsyncStorage.setItem(k, JSON.stringify(v)).catch(() => {});

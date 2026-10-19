import Constants from 'expo-constants';
import { Platform } from 'react-native';
import * as storage from './storage';

function guessBaseUrl() {
  if (process.env.EXPO_PUBLIC_API_URL) return process.env.EXPO_PUBLIC_API_URL;
  if (Platform.OS === 'web' && typeof window !== 'undefined') {
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }
  // On a phone, "localhost" is the phone itself: reuse the dev machine's LAN IP from Metro.
  const host = Constants.expoConfig?.hostUri?.split(':')[0];
  if (host) return `http://${host}:8000`;
  return Platform.OS === 'android' ? 'http://10.0.2.2:8000' : 'http://localhost:8000';
}

export const API_URL = guessBaseUrl();
const TOKEN_KEY = 'cb_kitchen_tokens';

let tokens = null;
let onSessionExpired = () => {};

export class ApiError extends Error {
  constructor(status, body) {
    const err = body?.error || {};
    super(err.message || 'Something went wrong');
    this.status = status;
    this.code = err.code || 'UNKNOWN';
    this.fields = err.fields || {};
  }
}

export async function loadTokens() {
  const raw = await storage.getSecure(TOKEN_KEY);
  tokens = raw ? JSON.parse(raw) : null;
  return tokens;
}

export async function saveTokens(t) {
  tokens = t;
  if (t) await storage.setSecure(TOKEN_KEY, JSON.stringify(t));
  else await storage.removeSecure(TOKEN_KEY);
}

export const getAccessToken = () => tokens?.access_token;
export const setSessionExpiredHandler = (fn) => { onSessionExpired = fn; };

async function doRefresh() {
  const res = await fetch(`${API_URL}/v1/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: tokens.refresh_token }),
  });
  if (!res.ok) return false;
  await saveTokens(await res.json());
  return true;
}

// Parallel requests that all hit 401 share one refresh: refresh tokens are
// single-use, so a second concurrent refresh would fail and log the user out.
let refreshing = null;
function refresh() {
  if (!refreshing) refreshing = doRefresh().finally(() => { refreshing = null; });
  return refreshing;
}

// Login and refresh calls must not trigger another refresh; everything else
// (including /v1/auth/me at app start) silently renews an expired token.
const isAuthCall = (path) => path.startsWith('/v1/auth/otp/') || path.startsWith('/v1/auth/refresh');

export async function api(path, { method = 'GET', body, headers = {}, retry = true } = {}) {
  let res;
  try {
    res = await fetch(API_URL + path, {
      method,
      headers: {
        'Content-Type': 'application/json',
        ...(tokens?.access_token ? { Authorization: `Bearer ${tokens.access_token}` } : {}),
        ...headers,
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    throw new ApiError(0, { error: { code: 'NETWORK', message: "Can't reach CampusBite. Check your connection." } });
  }
  if (res.status === 401 && retry && tokens?.refresh_token && !isAuthCall(path)) {
    let renewed;
    try {
      renewed = await refresh();
    } catch {
      // Offline while renewing: keep the session and report the network error.
      throw new ApiError(0, { error: { code: 'NETWORK', message: "Can't reach CampusBite. Check your connection." } });
    }
    if (renewed) return api(path, { method, body, headers, retry: false });
    await saveTokens(null);
    onSessionExpired();
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, data);
  return data;
}

export const newIdempotencyKey = () =>
  `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}-${Math.random().toString(36).slice(2, 10)}`;

export const API_URL = import.meta.env.VITE_API_URL || `${location.protocol}//${location.hostname}:8000`;
const KEY = 'cb_admin_tokens';

let tokens = JSON.parse(localStorage.getItem(KEY) || 'null');
let onExpired = () => {};

export class ApiError extends Error {
  constructor(status, body) {
    super(body?.error?.message || 'Request failed');
    this.status = status;
    this.code = body?.error?.code;
    this.fields = body?.error?.fields || {};
  }
}

export const hasSession = () => !!tokens;
export const accessToken = () => tokens?.access_token;
export const setExpiredHandler = (fn) => (onExpired = fn);
export function saveTokens(t) {
  tokens = t;
  if (t) localStorage.setItem(KEY, JSON.stringify(t));
  else localStorage.removeItem(KEY);
}

async function doRefresh() {
  const r = await fetch(`${API_URL}/v1/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: tokens.refresh_token }),
  });
  if (!r.ok) return false;
  saveTokens(await r.json());
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

export async function api(path, { method = 'GET', body, raw = false, retry = true } = {}) {
  let res;
  try {
    res = await fetch(API_URL + path, {
      method,
      headers: { 'Content-Type': 'application/json', ...(tokens ? { Authorization: `Bearer ${tokens.access_token}` } : {}) },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, { error: { code: 'NETWORK', message: `Cannot reach API at ${API_URL}` } });
  }
  if (res.status === 401 && retry && tokens?.refresh_token && !isAuthCall(path)) {
    let renewed;
    try {
      renewed = await refresh();
    } catch {
      // Offline while renewing: keep the session and report the network error.
      throw new ApiError(0, { error: { code: 'NETWORK', message: `Cannot reach API at ${API_URL}` } });
    }
    if (renewed) return api(path, { method, body, raw, retry: false });
    saveTokens(null);
    onExpired();
  }
  if (raw && res.ok) return res;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, data);
  return data;
}

export const inr = (p) => '₹' + ((p || 0) / 100).toLocaleString('en-IN', { maximumFractionDigits: 2 });
export const when = (iso) => (iso ? new Date(iso).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' }) : '—');

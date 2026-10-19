import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { Platform, Vibration } from 'react-native';
import { api, getAccessToken, loadTokens, saveTokens, setSessionExpiredHandler } from './api';
import { connectRealtime } from './realtime';
import { getJSON, setJSON } from './storage';

const Ctx = createContext(null);
export const useKitchen = () => useContext(Ctx);

// Short two-tone chime for new orders (web); devices vibrate.
function chime() {
  Vibration.vibrate([0, 300, 150, 300]);
  if (Platform.OS !== 'web' || typeof window === 'undefined') return;
  try {
    const ac = new (window.AudioContext || window.webkitAudioContext)();
    [880, 1175].forEach((f, i) => {
      const o = ac.createOscillator();
      const g = ac.createGain();
      o.frequency.value = f;
      o.connect(g);
      g.connect(ac.destination);
      g.gain.setValueAtTime(0.2, ac.currentTime + i * 0.18);
      g.gain.exponentialRampToValueAtTime(0.001, ac.currentTime + i * 0.18 + 0.3);
      o.start(ac.currentTime + i * 0.18);
      o.stop(ac.currentTime + i * 0.18 + 0.32);
    });
  } catch {}
}

export function KitchenProvider({ children }) {
  const [booting, setBooting] = useState(true);
  const [user, setUser] = useState(null);
  const [kitchens, setKitchens] = useState(null);
  const [kitchenId, setKitchenIdState] = useState(null);
  const [toastMsg, setToastMsg] = useState(null);
  const [dialog, setDialog] = useState(null);
  const [live, setLive] = useState(false);
  const [newCount, setNewCount] = useState(0);
  const [offline, setOffline] = useState(false);
  const listeners = useRef(new Set());
  const toastTimer = useRef();

  const toast = useCallback((text, kind = 'info') => {
    clearTimeout(toastTimer.current);
    setToastMsg({ text, kind, id: Date.now() });
    toastTimer.current = setTimeout(() => setToastMsg(null), 3200);
  }, []);
  const confirm = useCallback((opts) => new Promise((resolve) => setDialog({ ...opts, resolve })), []);
  const closeDialog = (v) => {
    dialog?.resolve(v);
    setDialog(null);
  };

  const loadKitchens = useCallback(async () => {
    const r = await api('/v1/kitchen/me');
    setKitchens(r.items);
    return r.items;
  }, []);

  // Load the user and their kitchens together, so a half-loaded state can't leave the
  // app on a spinner. No network -> offline screen, not a silent logout.
  const restoreSession = useCallback(async () => {
    setOffline(false);
    if (!(await loadTokens())) return;
    try {
      const me = await api('/v1/auth/me');
      const ks = await loadKitchens();
      const saved = await getJSON('cb_kitchen_id');
      setKitchenIdState(ks.find((k) => k.id === saved)?.id ?? (ks.length === 1 ? ks[0].id : null));
      setUser(me);
    } catch (e) {
      if (e.code === 'NETWORK') setOffline(true);
      else if (e.status === 401) await saveTokens(null);
    }
  }, [loadKitchens]);

  useEffect(() => {
    (async () => {
      await restoreSession();
      setBooting(false);
    })();
    setSessionExpiredHandler(() => setUser(null));
  }, []);

  const retryBoot = async () => {
    setBooting(true);
    await restoreSession();
    setBooting(false);
  };

  const setKitchenId = (id) => {
    setKitchenIdState(id);
    setJSON('cb_kitchen_id', id);
  };

  const signIn = async (data) => {
    await saveTokens({ access_token: data.access_token, refresh_token: data.refresh_token });
    const ks = await loadKitchens();
    if (ks.length === 1) setKitchenId(ks[0].id);
    setUser(data.user);
  };
  const signOut = async () => {
    try {
      await api('/v1/auth/logout', { method: 'POST' });
    } catch {}
    await saveTokens(null);
    setUser(null);
    setKitchens(null);
    setKitchenIdState(null);
  };

  const subscribe = useCallback((fn) => {
    listeners.current.add(fn);
    return () => listeners.current.delete(fn);
  }, []);

  // Socket rooms are fixed at connect time, so reconnect when kitchen memberships change.
  const kitchenKey = (kitchens || []).map((k) => k.id).join(',');
  useEffect(() => {
    if (!user) return;
    const stop = connectRealtime(getAccessToken, (evt) => {
      if (evt.type === 'connected') setLive(true);
      if (evt.type === 'disconnected') setLive(false);
      if (evt.type === 'new_order') {
        chime();
        setNewCount((n) => n + 1);
        toast(`🔔 New order ${evt.order_number}`, 'success');
      }
      if (evt.type === 'ack_overdue') toast(`⚠️ ${evt.order_number} is waiting for acceptance`, 'error');
      listeners.current.forEach((fn) => fn(evt));
    });
    return stop;
  }, [user?.id, kitchenKey]);

  const kitchen = (kitchens || []).find((k) => k.id === kitchenId) || null;
  const role = kitchen?.my_role;
  const can = {
    manage: ['kitchen_owner', 'kitchen_manager'].includes(role),
    frontDesk: ['kitchen_owner', 'kitchen_manager', 'kitchen_cashier'].includes(role),
    cook: ['kitchen_owner', 'kitchen_manager', 'kitchen_cook'].includes(role),
    owner: role === 'kitchen_owner',
  };

  const value = {
    booting, offline, retryBoot, user, setUser, signIn, signOut,
    kitchens, kitchen, kitchenId, setKitchenId, loadKitchens, can, role,
    toast, toastMsg, confirm, dialog, closeDialog,
    subscribe, live, newCount, clearNew: () => setNewCount(0),
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useLive(load, match = () => true, pollMs = 15000) {
  const { subscribe } = useKitchen();
  useEffect(() => {
    const unsub = subscribe((evt) => {
      if (evt.type === 'connected' || match(evt)) load();
    });
    const t = setInterval(load, pollMs);
    return () => {
      unsub();
      clearInterval(t);
    };
  }, [load]);
}

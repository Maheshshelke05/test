import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { BackHandler } from 'react-native';
import { api, getAccessToken, loadTokens, saveTokens, setSessionExpiredHandler } from './api';
import { connectRealtime } from './realtime';
import { getJSON, setJSON } from './storage';

const AppCtx = createContext(null);
export const useApp = () => useContext(AppCtx);

const EMPTY_CART = { kitchen: null, lines: [], instructions: '' };
const lineKey = (itemId, choiceIds = []) => `${itemId}:${[...choiceIds].sort((a, b) => a - b).join(',')}`;

export function AppProvider({ children }) {
  const [booting, setBooting] = useState(true);
  const [onboarded, setOnboarded] = useState(false);
  const [user, setUser] = useState(null);
  const [stack, setStack] = useState([]);
  const [tab, setTab] = useState('home');
  const [cart, setCartState] = useState(EMPTY_CART);
  const [toastMsg, setToastMsg] = useState(null);
  const [dialog, setDialog] = useState(null);
  const [live, setLive] = useState(false);
  const [favIds, setFavIds] = useState(new Set());
  const [offline, setOffline] = useState(false);
  const listeners = useRef(new Set());
  const toastTimer = useRef();

  // ---------------------------------------------------------------- boot
  // A saved session is only dropped when the server rejects it; with no network we
  // show an offline screen instead of pretending the user is logged out.
  const restoreSession = useCallback(async () => {
    setOffline(false);
    if (await loadTokens()) {
      try {
        setUser(await api('/v1/auth/me'));
      } catch (e) {
        if (e.code === 'NETWORK') setOffline(true);
        else if (e.status === 401) await saveTokens(null);
      }
    }
  }, []);

  useEffect(() => {
    (async () => {
      setOnboarded(!!(await getJSON('cb_onboarded', false)));
      setCartState(await getJSON('cb_cart', EMPTY_CART));
      await restoreSession();
      setBooting(false);
    })();
    setSessionExpiredHandler(() => {
      setUser(null);
      setStack([]);
    });
  }, []);

  const retryBoot = async () => {
    setBooting(true);
    await restoreSession();
    setBooting(false);
  };

  // ---------------------------------------------------------------- feedback
  const toast = useCallback((text, kind = 'info') => {
    clearTimeout(toastTimer.current);
    setToastMsg({ text, kind, id: Date.now() });
    toastTimer.current = setTimeout(() => setToastMsg(null), 3200);
  }, []);

  const confirm = useCallback(
    (opts) => new Promise((resolve) => setDialog({ ...opts, resolve })),
    []
  );
  const closeDialog = (result) => {
    dialog?.resolve(result);
    setDialog(null);
  };

  // ---------------------------------------------------------------- realtime
  const subscribe = useCallback((fn) => {
    listeners.current.add(fn);
    return () => listeners.current.delete(fn);
  }, []);

  useEffect(() => {
    if (!user) return;
    const stop = connectRealtime(getAccessToken, (evt) => {
      if (evt.type === 'connected') setLive(true);
      if (evt.type === 'disconnected') setLive(false);
      if (evt.type === 'notification') toast(`${evt.title} — ${evt.body}`, 'success');
      listeners.current.forEach((fn) => fn(evt));
    });
    return stop;
  }, [user?.id]);

  useEffect(() => {
    if (!user) return;
    api('/v1/me/favorites').then((r) => setFavIds(new Set(r.items.map((i) => i.id)))).catch(() => {});
  }, [user?.id]);

  const toggleFavorite = async (itemId) => {
    const on = favIds.has(itemId);
    const next = new Set(favIds);
    on ? next.delete(itemId) : next.add(itemId);
    setFavIds(next);
    try {
      await api(`/v1/me/favorites/${itemId}`, { method: on ? 'DELETE' : 'POST' });
      return true;
    } catch (e) {
      setFavIds(favIds);
      toast(e.message, 'error');
      return false;
    }
  };

  // ---------------------------------------------------------------- navigation
  const nav = useMemo(
    () => ({
      push: (name, params = {}) => setStack((st) => [...st, { name, params, key: `${name}-${Date.now()}` }]),
      pop: () => setStack((st) => st.slice(0, -1)),
      replace: (name, params = {}) => setStack((st) => [...st.slice(0, -1), { name, params, key: `${name}-${Date.now()}` }]),
      reset: () => setStack([]),
      tab: (t) => {
        setStack([]);
        setTab(t);
      },
    }),
    []
  );

  useEffect(() => {
    const sub = BackHandler.addEventListener('hardwareBackPress', () => {
      if (dialog) {
        closeDialog(false);
        return true;
      }
      if (stack.length) {
        nav.pop();
        return true;
      }
      if (tab !== 'home') {
        setTab('home');
        return true;
      }
      return false;
    });
    return () => sub.remove();
  }, [stack.length, tab, dialog]);

  // ---------------------------------------------------------------- auth
  const signIn = async (data) => {
    await saveTokens({ access_token: data.access_token, refresh_token: data.refresh_token });
    setUser(data.user);
  };
  const signOut = async () => {
    try {
      await api('/v1/auth/logout', { method: 'POST' });
    } catch {}
    await saveTokens(null);
    setUser(null);
    setStack([]);
    setTab('home');
  };
  const finishOnboarding = () => {
    setJSON('cb_onboarded', true);
    setOnboarded(true);
  };

  // ---------------------------------------------------------------- cart (one kitchen per cart)
  const setCart = (next) => {
    setCartState(next);
    setJSON('cb_cart', next);
  };

  const addToCart = async (kitchen, item, { quantity = 1, choiceIds = [], optionsLabel = '', unitPrice } = {}) => {
    let base = cart;
    if (cart.kitchen && cart.kitchen.id !== kitchen.id) {
      const ok = await confirm({
        title: 'Replace cart?',
        message: `Your cart has items from ${cart.kitchen.name}. Start a new cart from ${kitchen.name}?`,
        confirmText: 'Replace',
      });
      if (!ok) return false;
      base = EMPTY_CART;
    }
    const key = lineKey(item.id, choiceIds);
    const existing = base.lines.find((l) => l.key === key);
    const lines = existing
      ? base.lines.map((l) => (l.key === key ? { ...l, quantity: Math.min(l.quantity + quantity, item.max_per_order || 50) } : l))
      : [
          ...base.lines,
          {
            key,
            menu_item_id: item.id,
            name: item.name,
            emoji: item.emoji,
            is_veg: item.is_veg,
            quantity,
            choice_ids: choiceIds,
            options_label: optionsLabel,
            unit_price_paise: unitPrice ?? item.price_paise,
            max_per_order: item.max_per_order,
          },
        ];
    setCart({ ...base, kitchen: { id: kitchen.id, name: kitchen.name, emoji: kitchen.emoji, college_id: kitchen.college_id }, lines });
    return true;
  };

  const setLineQty = (key, qty) => {
    const lines = qty <= 0 ? cart.lines.filter((l) => l.key !== key) : cart.lines.map((l) => (l.key === key ? { ...l, quantity: qty } : l));
    setCart(lines.length ? { ...cart, lines } : EMPTY_CART);
  };

  const qtyOf = (itemId) => cart.lines.filter((l) => l.menu_item_id === itemId).reduce((n, l) => n + l.quantity, 0);

  const decItem = (itemId) => {
    const line = [...cart.lines].reverse().find((l) => l.menu_item_id === itemId);
    if (line) setLineQty(line.key, line.quantity - 1);
  };

  const clearCart = () => setCart(EMPTY_CART);
  const setInstructions = (instructions) => setCart({ ...cart, instructions });

  const cartCount = cart.lines.reduce((n, l) => n + l.quantity, 0);
  const cartTotal = cart.lines.reduce((n, l) => n + l.quantity * l.unit_price_paise, 0);

  const value = {
    booting, offline, retryBoot, onboarded, finishOnboarding, user, setUser, signIn, signOut,
    stack, nav, tab,
    cart, cartCount, cartTotal, addToCart, setLineQty, qtyOf, decItem, clearCart, setCart, setInstructions,
    toast, toastMsg, confirm, dialog, closeDialog,
    subscribe, live, favIds, toggleFavorite,
  };
  return <AppCtx.Provider value={value}>{children}</AppCtx.Provider>;
}

// Re-run `load` whenever a realtime event matches, plus a slow polling fallback.
export function useLiveRefresh(load, match = () => true, pollMs = 20000) {
  const { subscribe } = useApp();
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

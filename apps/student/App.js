import { StatusBar } from 'expo-status-bar';
import { useEffect, useRef } from 'react';
import { ActivityIndicator, Animated, Modal, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { CollegePicker, Login, Onboarding, ProfileForm } from './src/screens/auth';
import { CartScreen, PaymentScreen } from './src/screens/cart';
import { HomeScreen, KitchensScreen, SearchScreen } from './src/screens/home';
import { KitchenScreen } from './src/screens/kitchen';
import { OrderScreen, OrdersScreen } from './src/screens/orders';
import { FavoritesScreen, NotificationsScreen, PrivacyScreen, ProfileScreen, SupportScreen } from './src/screens/profile';
import { AppProvider, useApp } from './src/store';
import { colors, radius, rupees, shadow, space, type } from './src/theme';
import { Btn, motionOK, nativeDriver } from './src/ui';

const TABS = [
  { id: 'home', label: 'Home', icon: '🏠' },
  { id: 'kitchens', label: 'Kitchens', icon: '🍳' },
  { id: 'orders', label: 'Orders', icon: '🧾' },
  { id: 'profile', label: 'Profile', icon: '👤' },
];

const SCREENS = {
  kitchen: KitchenScreen,
  search: SearchScreen,
  cart: CartScreen,
  pay: PaymentScreen,
  order: OrderScreen,
  favorites: FavoritesScreen,
  notifications: NotificationsScreen,
  support: SupportScreen,
  privacy: PrivacyScreen,
};

const CART_VISIBLE_ON = new Set(['tabs:home', 'tabs:kitchens', 'kitchen', 'search', 'favorites']);

function StickyCart({ visible, bottom }) {
  const { cartCount, cartTotal, cart, nav } = useApp();
  const y = useRef(new Animated.Value(300)).current;
  const show = visible && cartCount > 0;
  useEffect(() => {
    const to = show ? 0 : 300;
    if (!motionOK()) return y.setValue(to);
    Animated.spring(y, { toValue: to, useNativeDriver: nativeDriver, speed: 16, bounciness: 6 }).start();
  }, [show]);
  return (
    <Animated.View pointerEvents={show ? 'auto' : 'none'} aria-hidden={!show} style={[styles.cartBar, { bottom, opacity: y.interpolate({ inputRange: [0, 120, 300], outputRange: [1, 0, 0] }), transform: [{ translateY: y }] }]}>
      <Pressable onPress={() => nav.push('cart')} accessibilityRole="button" accessibilityLabel={`View cart, ${cartCount} items, ${rupees(cartTotal)}`}
        style={({ pressed }) => [styles.cartInner, pressed && { transform: [{ scale: 0.98 }] }]}>
        <View style={styles.cartIcon}><Text style={{ fontSize: 20 }}>🛒</Text></View>
        <View style={{ flex: 1 }}>
          <Text style={{ color: '#fff', fontWeight: '800', fontSize: 15 }}>{cartCount} item{cartCount > 1 ? 's' : ''} · {rupees(cartTotal)}</Text>
          <Text style={{ color: '#CDE9D6', fontSize: 12 }} numberOfLines={1}>from {cart.kitchen?.name}</Text>
        </View>
        <Text style={{ color: '#fff', fontWeight: '800', fontSize: 15 }}>View cart ›</Text>
      </Pressable>
    </Animated.View>
  );
}

function TabBar() {
  const { tab, nav } = useApp();
  return (
    <View style={styles.tabbar} accessibilityRole="tablist">
      {TABS.map((t) => {
        const on = tab === t.id;
        return (
          <Pressable key={t.id} onPress={() => nav.tab(t.id)} style={styles.tab} accessibilityRole="tab" accessibilityState={{ selected: on }} accessibilityLabel={t.label}>
            <Text style={{ fontSize: 20, opacity: on ? 1 : 0.55 }}>{t.icon}</Text>
            <Text style={{ fontSize: 11, fontWeight: on ? '800' : '600', color: on ? colors.green : colors.muted, marginTop: 2 }}>{t.label}</Text>
            {on ? <View style={styles.tabDot} /> : null}
          </Pressable>
        );
      })}
    </View>
  );
}

function Toast() {
  const { toastMsg } = useApp();
  const y = useRef(new Animated.Value(-100)).current;
  useEffect(() => {
    if (!toastMsg) return;
    y.setValue(-100);
    Animated.spring(y, { toValue: 0, useNativeDriver: nativeDriver, speed: 18 }).start();
  }, [toastMsg?.id]);
  if (!toastMsg) return null;
  const bg = toastMsg.kind === 'error' ? colors.red : toastMsg.kind === 'success' ? colors.green : colors.text;
  return (
    <Animated.View pointerEvents="none" accessibilityLiveRegion="polite" style={[styles.toast, { backgroundColor: bg, transform: [{ translateY: y }] }]}>
      <Text style={{ color: '#fff', fontWeight: '600' }}>{toastMsg.text}</Text>
    </Animated.View>
  );
}

function Dialog() {
  const { dialog, closeDialog } = useApp();
  if (!dialog) return null;
  return (
    <Modal transparent visible animationType="fade" onRequestClose={() => closeDialog(false)}>
      <View style={styles.dialogWrap}>
        <View style={styles.dialog} accessibilityRole="alert">
          <Text style={type.h2}>{dialog.title}</Text>
          {dialog.message ? <Text style={[type.body, { marginTop: 8, color: colors.muted }]}>{dialog.message}</Text> : null}
          <View style={{ flexDirection: 'row', gap: 10, marginTop: 20 }}>
            {!dialog.hideCancel ? <Btn title={dialog.cancelText || 'Cancel'} variant="secondary" onPress={() => closeDialog(false)} style={{ flex: 1 }} /> : null}
            <Btn title={dialog.confirmText || 'OK'} variant={dialog.destructive ? 'danger' : 'primary'} onPress={() => closeDialog(true)} style={{ flex: 1 }} />
          </View>
        </View>
      </View>
    </Modal>
  );
}

function Root() {
  const { booting, offline, retryBoot, onboarded, user, stack, tab, nav } = useApp();
  if (booting) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.yellow }}>
        <Text style={{ fontSize: 34, fontWeight: '900', color: colors.green }}>campusbite</Text>
        <ActivityIndicator color={colors.green} style={{ marginTop: 16 }} />
      </View>
    );
  }
  if (offline) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.surface, padding: space(3) }}>
        <Text style={{ fontSize: 52 }}>📡</Text>
        <Text style={[type.h2, { marginTop: 12 }]}>You’re offline</Text>
        <Text style={[type.body, { color: colors.muted, textAlign: 'center', marginTop: 6 }]}>
          CampusBite can’t reach the server. Check your internet connection and try again.
        </Text>
        <Btn title="Try again" onPress={retryBoot} style={{ marginTop: 20, alignSelf: 'stretch' }} />
      </View>
    );
  }
  if (!onboarded) return <Onboarding />;
  if (!user) return <Login />;
  if (!user.name) return <ProfileForm />;
  if (!user.college_id) return <CollegePicker />;

  const top = stack[stack.length - 1];
  let screen;
  let where;
  if (!top) {
    where = `tabs:${tab}`;
    const Tab = { home: HomeScreen, kitchens: KitchensScreen, orders: OrdersScreen, profile: ProfileScreen }[tab];
    screen = (
      <View style={{ flex: 1 }}>
        <View style={{ flex: 1 }}><Tab /></View>
        <TabBar />
      </View>
    );
  } else {
    where = top.name;
    if (top.name === 'college') screen = <CollegePicker onBack={nav.pop} />;
    else if (top.name === 'editProfile') screen = <ProfileForm title="Edit profile" onBack={nav.pop} onDone={nav.pop} />;
    else {
      const S = SCREENS[top.name];
      screen = <S key={top.key} {...top.params} />;
    }
  }
  return (
    <View style={{ flex: 1 }}>
      {screen}
      <StickyCart visible={CART_VISIBLE_ON.has(where)} bottom={top ? space(2) : 76} />
    </View>
  );
}

export default function App() {
  return (
    <AppProvider>
      <View style={styles.app}>
        <View style={styles.frame}>
          <StatusBar style="dark" />
          <Root />
          <Toast />
          <Dialog />
        </View>
      </View>
    </AppProvider>
  );
}

const styles = StyleSheet.create({
  // On web, center a phone-width column so the app reads like the mobile build.
  app: { flex: 1, backgroundColor: Platform.OS === 'web' ? '#E9ECE6' : colors.bg, alignItems: 'center' },
  frame: { flex: 1, width: '100%', maxWidth: Platform.OS === 'web' ? 480 : undefined, backgroundColor: colors.bg, overflow: 'hidden' },
  tabbar: {
    flexDirection: 'row',
    backgroundColor: colors.surface,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    paddingBottom: Platform.OS === 'ios' ? 20 : 6,
    paddingTop: 6,
  },
  tab: { flex: 1, alignItems: 'center', justifyContent: 'center', minHeight: 48 },
  tabDot: { width: 4, height: 4, borderRadius: 2, backgroundColor: colors.green, marginTop: 2 },
  cartBar: { position: 'absolute', left: space(1.5), right: space(1.5) },
  cartInner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    backgroundColor: colors.green,
    borderRadius: radius.lg,
    paddingVertical: 12,
    paddingHorizontal: 14,
    ...shadow,
    shadowOpacity: 0.25,
  },
  cartIcon: { width: 40, height: 40, borderRadius: 10, backgroundColor: 'rgba(255,255,255,0.15)', alignItems: 'center', justifyContent: 'center' },
  toast: { position: 'absolute', top: 44, left: 16, right: 16, padding: 14, borderRadius: radius.md, ...shadow },
  dialogWrap: { flex: 1, backgroundColor: colors.overlay, alignItems: 'center', justifyContent: 'center', padding: space(3) },
  dialog: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: space(3), width: '100%', maxWidth: 420 },
});

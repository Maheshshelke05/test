import { StatusBar } from 'expo-status-bar';
import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Animated, Modal, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { KitchenPicker, Login, StatusGate } from './src/screens/auth';
import { MenuScreen } from './src/screens/menu';
import { MoreScreen } from './src/screens/more';
import { OrdersScreen, VerifyScreen } from './src/screens/orders';
import { KitchenProvider, useKitchen } from './src/store';
import { colors, radius, shadow, space, type } from './src/theme';
import { Btn, nativeDriver } from './src/ui';

function Toast() {
  const { toastMsg } = useKitchen();
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
      <Text style={{ color: '#fff', fontWeight: '700' }}>{toastMsg.text}</Text>
    </Animated.View>
  );
}

function Dialog() {
  const { dialog, closeDialog } = useKitchen();
  if (!dialog) return null;
  return (
    <Modal transparent visible animationType="fade" onRequestClose={() => closeDialog(false)}>
      <View style={styles.dialogWrap}>
        <View style={styles.dialog} accessibilityRole="alert">
          <Text style={type.h2}>{dialog.title}</Text>
          {dialog.message ? <Text style={[type.body, { marginTop: 8, color: colors.muted }]}>{dialog.message}</Text> : null}
          <View style={{ flexDirection: 'row', gap: 10, marginTop: 20 }}>
            <Btn title={dialog.cancelText || 'Cancel'} variant="secondary" onPress={() => closeDialog(false)} style={{ flex: 1 }} />
            <Btn title={dialog.confirmText || 'OK'} variant={dialog.destructive ? 'danger' : 'primary'} onPress={() => closeDialog(true)} style={{ flex: 1 }} />
          </View>
        </View>
      </View>
    </Modal>
  );
}

const TABS = [
  { id: 'orders', label: 'Orders', icon: '🧾' },
  { id: 'verify', label: 'Pickup', icon: '✅', need: 'frontDesk' },
  { id: 'menu', label: 'Menu', icon: '📋' },
  { id: 'more', label: 'More', icon: '☰' },
];

function Main() {
  const { can, newCount } = useKitchen();
  const [tab, setTab] = useState('orders');
  const tabs = TABS.filter((t) => !t.need || can[t.need]);
  const Screen = { orders: OrdersScreen, verify: VerifyScreen, menu: MenuScreen, more: MoreScreen }[tab];
  return (
    <View style={{ flex: 1 }}>
      <View style={{ flex: 1 }}><Screen /></View>
      <View style={styles.tabbar} accessibilityRole="tablist">
        {tabs.map((t) => {
          const on = tab === t.id;
          return (
            <Pressable key={t.id} onPress={() => setTab(t.id)} style={styles.tab} accessibilityRole="tab" accessibilityState={{ selected: on }} accessibilityLabel={t.label}>
              <View>
                <Text style={{ fontSize: 20, opacity: on ? 1 : 0.55, textAlign: 'center' }}>{t.icon}</Text>
                {t.id === 'orders' && newCount > 0 && tab !== 'orders' ? (
                  <View style={styles.badge}><Text style={{ color: '#fff', fontSize: 10, fontWeight: '900' }}>{newCount}</Text></View>
                ) : null}
              </View>
              <Text style={{ fontSize: 12, fontWeight: on ? '800' : '600', color: on ? colors.green : colors.muted }}>{t.label}</Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

function Root() {
  const { booting, offline, retryBoot, user, kitchens, kitchen } = useKitchen();
  if (booting || (user && !kitchens)) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.green }}>
        <Text style={{ fontSize: 30, fontWeight: '900', color: colors.yellow }}>campusbite</Text>
        <Text style={{ color: '#fff', fontWeight: '700' }}>Kitchen Partner</Text>
        <ActivityIndicator color={colors.yellow} style={{ marginTop: 16 }} />
      </View>
    );
  }
  if (offline) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.surface, padding: space(3) }}>
        <Text style={{ fontSize: 52 }}>📡</Text>
        <Text style={[type.h2, { marginTop: 12 }]}>You’re offline</Text>
        <Text style={[type.body, { color: colors.muted, textAlign: 'center', marginTop: 6 }]}>
          Can’t reach CampusBite. Check the internet connection — orders will load again once you’re back.
        </Text>
        <Btn title="Try again" onPress={retryBoot} style={{ marginTop: 20, alignSelf: 'stretch' }} />
      </View>
    );
  }
  if (!user) return <Login />;
  if (!kitchen) return <KitchenPicker />;
  if (kitchen.status === 'REJECTED' || kitchen.status === 'SUSPENDED') return <StatusGate />;
  return <Main />;
}

export default function App() {
  return (
    <KitchenProvider>
      <View style={styles.app}>
        <View style={styles.frame}>
          <StatusBar style="light" />
          <Root />
          <Toast />
          <Dialog />
        </View>
      </View>
    </KitchenProvider>
  );
}

const styles = StyleSheet.create({
  app: { flex: 1, backgroundColor: Platform.OS === 'web' ? '#DDE5DF' : colors.bg, alignItems: 'center' },
  frame: { flex: 1, width: '100%', maxWidth: Platform.OS === 'web' ? 760 : undefined, backgroundColor: colors.bg, overflow: 'hidden' },
  tabbar: { flexDirection: 'row', backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 6, paddingBottom: Platform.OS === 'ios' ? 20 : 6 },
  tab: { flex: 1, alignItems: 'center', justifyContent: 'center', minHeight: 50 },
  badge: { position: 'absolute', top: -4, right: -10, backgroundColor: colors.red, borderRadius: 9, minWidth: 18, height: 18, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 4 },
  toast: { position: 'absolute', top: 44, left: 16, right: 16, padding: 14, borderRadius: radius.md, ...shadow },
  dialogWrap: { flex: 1, backgroundColor: colors.overlay, alignItems: 'center', justifyContent: 'center', padding: space(3) },
  dialog: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: space(3), width: '100%', maxWidth: 420 },
});

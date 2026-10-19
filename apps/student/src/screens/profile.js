import { useCallback, useEffect, useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import { api, API_URL } from '../api';
import { useApp } from '../store';
import { colors, radius, rupees, space, type } from '../theme';
import { Btn, Card, Chip, Divider, Empty, ErrorState, Field, ListSkeleton, Row, Scroll, TopBar, VegMark } from '../ui';

function MenuRow({ icon, label, sub, onPress, danger }) {
  return (
    <Pressable onPress={onPress} accessibilityRole="button" accessibilityLabel={label}
      style={{ flexDirection: 'row', alignItems: 'center', gap: 14, paddingVertical: 14 }}>
      <Text style={{ fontSize: 20, width: 28, textAlign: 'center' }}>{icon}</Text>
      <View style={{ flex: 1 }}>
        <Text style={[type.body, { fontWeight: '600', color: danger ? colors.red : colors.text }]}>{label}</Text>
        {sub ? <Text style={type.small}>{sub}</Text> : null}
      </View>
      <Text style={{ color: colors.faint, fontSize: 18 }}>›</Text>
    </Pressable>
  );
}

export function ProfileScreen() {
  const { user, nav, signOut, confirm, live } = useApp();
  const [unread, setUnread] = useState(0);
  useEffect(() => {
    api('/v1/me/notifications').then((r) => setUnread(r.unread)).catch(() => {});
  }, []);

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <Scroll>
        <View style={{ backgroundColor: colors.yellow, paddingTop: space(6), paddingBottom: space(3), paddingHorizontal: space(2) }}>
          <Row style={{ gap: 14 }}>
            <View style={{ width: 64, height: 64, borderRadius: 32, backgroundColor: '#fff', alignItems: 'center', justifyContent: 'center' }}>
              <Text style={{ fontSize: 28, fontWeight: '900', color: colors.green }}>{(user.name || '?')[0].toUpperCase()}</Text>
            </View>
            <View style={{ flex: 1 }}>
              <Text style={type.h2}>{user.name}</Text>
              <Text style={[type.small, { color: '#4A4000' }]}>+91 {user.phone}{user.roll_no ? ` · ${user.roll_no}` : ''}</Text>
              <Text style={[type.small, { color: '#4A4000' }]} numberOfLines={1}>🏫 {user.college?.name}</Text>
            </View>
          </Row>
        </View>
        <View style={{ padding: space(2), gap: 12 }}>
          <Card style={{ paddingVertical: 4 }}>
            <MenuRow icon="✏️" label="Edit profile" onPress={() => nav.push('editProfile')} />
            <Divider style={{ marginVertical: 0 }} />
            <MenuRow icon="🏫" label="Change campus" sub={user.college?.name} onPress={() => nav.push('college')} />
            <Divider style={{ marginVertical: 0 }} />
            <MenuRow icon="❤️" label="Favourites" onPress={() => nav.push('favorites')} />
            <Divider style={{ marginVertical: 0 }} />
            <MenuRow icon="🔔" label="Notifications" sub={unread ? `${unread} unread` : 'Order updates inbox'} onPress={() => nav.push('notifications')} />
          </Card>
          <Card style={{ paddingVertical: 4 }}>
            <MenuRow icon="💬" label="Help & support" sub="Delayed, missing or wrong order" onPress={() => nav.push('support', {})} />
            <Divider style={{ marginVertical: 0 }} />
            <MenuRow icon="🔒" label="Privacy" sub="We store only what’s needed for your orders" onPress={() => nav.push('privacy')} />
          </Card>
          <Card style={{ paddingVertical: 4 }}>
            <MenuRow icon="🚪" label="Log out" danger onPress={async () => (await confirm({ title: 'Log out?', confirmText: 'Log out', destructive: true })) && signOut()} />
          </Card>
          <Text style={[type.small, { textAlign: 'center' }]}>CampusBite v1.0 · {live ? 'live updates on' : 'reconnecting…'}{'\n'}{API_URL}</Text>
        </View>
      </Scroll>
    </View>
  );
}

export function FavoritesScreen() {
  const { nav, toggleFavorite, user } = useApp();
  const [items, setItems] = useState(null);
  const [error, setError] = useState(null);
  const load = useCallback(() => api('/v1/me/favorites').then((r) => { setItems(r.items); setError(null); }).catch(setError), []);
  useEffect(() => { load(); }, [load]);
  // Go through the store so the ♥ on menu screens stays in sync.
  const remove = async (id) => {
    if (await toggleFavorite(id)) setItems((cur) => cur.filter((i) => i.id !== id));
  };
  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <TopBar title="Favourites" onBack={nav.pop} />
      {error ? <ErrorState error={error} onRetry={load} /> : !items ? <ListSkeleton /> : (
        <Scroll contentStyle={{ padding: space(2), gap: 12 }}>
          {items.length === 0 ? <Empty emoji="❤️" title="No favourites yet" subtitle="Tap ♡ on a dish to save it here." /> : items.map((it) => {
            const otherCampus = it.kitchen.college_id !== user.college_id;
            return (
              <Card key={it.id}>
                {/* Open and remove are siblings so tapping ♥ never also opens the kitchen. */}
                <Row style={{ gap: 12 }}>
                  <Pressable accessibilityRole="button" accessibilityLabel={`Open ${it.name}`} disabled={otherCampus}
                    onPress={() => nav.push('kitchen', { kitchenId: it.kitchen.id, openItemId: it.id })}
                    style={{ flex: 1, flexDirection: 'row', alignItems: 'center', gap: 12, opacity: otherCampus ? 0.55 : 1 }}>
                    <Text style={{ fontSize: 32 }}>{it.emoji}</Text>
                    <View style={{ flex: 1 }}>
                      <Row style={{ gap: 6 }}><VegMark veg={it.is_veg} size={12} /><Text style={type.h3}>{it.name}</Text></Row>
                      <Text style={type.small}>
                        {it.kitchen.name} · {rupees(it.price_paise)}{it.sold_out ? ' · sold out' : ''}{otherCampus ? ' · other campus' : ''}
                      </Text>
                    </View>
                  </Pressable>
                  <Pressable accessibilityRole="button" onPress={() => remove(it.id)} accessibilityLabel={`Remove ${it.name} from favourites`} hitSlop={10}>
                    <Text style={{ fontSize: 22, color: colors.red }}>♥</Text>
                  </Pressable>
                </Row>
              </Card>
            );
          })}
        </Scroll>
      )}
    </View>
  );
}

export function NotificationsScreen() {
  const { nav } = useApp();
  const [items, setItems] = useState(null);
  useEffect(() => {
    api('/v1/me/notifications').then((r) => {
      setItems(r.items);
      if (r.unread) api('/v1/me/notifications/read', { method: 'POST' }).catch(() => {});
    }).catch(() => setItems([]));
  }, []);
  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <TopBar title="Notifications" onBack={nav.pop} />
      {!items ? <ListSkeleton /> : (
        <Scroll contentStyle={{ padding: space(2), gap: 10 }}>
          {items.length === 0 ? <Empty emoji="🔔" title="You’re all caught up" /> : items.map((n) => (
            <Card key={n.id} onPress={n.order_id ? () => nav.push('order', { orderId: n.order_id }) : undefined}
              style={!n.is_read && { borderLeftWidth: 4, borderLeftColor: colors.yellow }}>
              <Text style={type.h3}>{n.title}</Text>
              <Text style={[type.body, { marginTop: 2 }]}>{n.body}</Text>
              <Text style={[type.small, { marginTop: 4 }]}>{new Date(n.created_at).toLocaleString()}</Text>
            </Card>
          ))}
        </Scroll>
      )}
    </View>
  );
}

const CATEGORIES = [
  ['DELAYED', 'Order delayed'],
  ['MISSING_ITEM', 'Missing item'],
  ['WRONG_ORDER', 'Wrong order'],
  ['PAYMENT', 'Payment issue'],
  ['REFUND', 'Refund'],
  ['OTHER', 'Something else'],
];

export function SupportScreen({ orderId, orderNumber }) {
  const { nav, toast } = useApp();
  const [category, setCategory] = useState(orderId ? 'DELAYED' : 'OTHER');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [tickets, setTickets] = useState(null);
  const load = () => api('/v1/support').then((r) => setTickets(r.items)).catch(() => setTickets([]));
  useEffect(() => { load(); }, []);

  const submit = async () => {
    if (message.trim().length < 5) return toast('Please describe the issue');
    setBusy(true);
    try {
      await api('/v1/support', { method: 'POST', body: { order_id: orderId || null, category, message: message.trim() } });
      toast('Ticket raised. Our team will get back to you.', 'success');
      setMessage('');
      load();
    } catch (e) {
      toast(e.message, 'error');
    }
    setBusy(false);
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <TopBar title="Help & support" subtitle={orderNumber ? `About order ${orderNumber}` : undefined} onBack={nav.pop} />
      <Scroll contentStyle={{ padding: space(2), gap: 12 }}>
        <Card>
          <Text style={[type.h3, { marginBottom: 10 }]}>What went wrong?</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 14 }}>
            {CATEGORIES.map(([id, label]) => <Chip key={id} label={label} active={category === id} onPress={() => setCategory(id)} />)}
          </View>
          <Field label="Details" placeholder="Tell us what happened" value={message} onChangeText={setMessage} multiline
            inputStyle={{ height: 110, paddingTop: 12, textAlignVertical: 'top' }} maxLength={2000} />
          <Btn title="Submit ticket" onPress={submit} loading={busy} />
        </Card>
        {tickets?.length ? <Text style={[type.label, { marginTop: 8 }]}>Your tickets</Text> : null}
        {(tickets || []).map((t) => (
          <Card key={t.id}>
            <Row style={{ justifyContent: 'space-between' }}>
              <Text style={type.h3}>#{t.id} · {CATEGORIES.find((c) => c[0] === t.category)?.[1]}</Text>
              <Text style={{ fontWeight: '700', fontSize: 12, color: t.status === 'RESOLVED' ? colors.green : '#9A6700' }}>{t.status.replace('_', ' ')}</Text>
            </Row>
            <Text style={[type.body, { marginTop: 4 }]}>{t.message}</Text>
            {t.admin_note ? <Text style={[type.small, { marginTop: 6, color: colors.green }]}>Support: {t.admin_note}</Text> : null}
          </Card>
        ))}
      </Scroll>
    </View>
  );
}

export function PrivacyScreen() {
  const { nav } = useApp();
  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <TopBar title="Privacy" onBack={nav.pop} />
      <Scroll contentStyle={{ padding: space(3) }}>
        {[
          ['What we store', 'Your mobile number, name, optional college email/roll number, selected campus and order history.'],
          ['What kitchens see', 'Only your first name and the last 4 digits of your phone for handing over your order.'],
          ['Location', 'Used only once, with your permission, to sort nearby colleges. It is never used to decide access.'],
          ['Payments', 'Card and UPI details are handled by the payment provider. CampusBite never stores them.'],
          ['Your control', 'Ask support to delete your account. Financial records are kept as required by law.'],
        ].map(([h, b]) => (
          <View key={h} style={{ marginBottom: 18 }}>
            <Text style={type.h3}>{h}</Text>
            <Text style={[type.body, { marginTop: 4, color: colors.muted }]}>{b}</Text>
          </View>
        ))}
      </Scroll>
    </View>
  );
}

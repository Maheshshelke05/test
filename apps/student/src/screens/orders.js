import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, FlatList, Pressable, Text, View } from 'react-native';
import QRCode from 'react-native-qrcode-svg';
import { api } from '../api';
import { useApp, useLiveRefresh } from '../store';
import { colors, radius, rupees, space, STATUS, type } from '../theme';
import { Btn, Card, Chip, Divider, Empty, ErrorState, ListSkeleton, Row, Scroll, StatusPill, TopBar, VegMark } from '../ui';

const fmtTime = (iso) => (iso ? new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) : '');
const fmtDate = (iso) => new Date(iso).toLocaleDateString([], { day: 'numeric', month: 'short' }) + ', ' + fmtTime(iso);

export function OrdersScreen() {
  const { nav } = useApp();
  const [tab, setTab] = useState('active');
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      setData(await api(`/v1/orders?active=${tab === 'active'}&size=50`));
      setError(null);
    } catch (e) {
      setError(e);
    }
    setRefreshing(false);
  }, [tab]);
  useEffect(() => {
    setData(null);
    load();
  }, [load]);
  useLiveRefresh(load, (e) => e.type === 'order_updated');

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <View style={{ backgroundColor: colors.surface, paddingTop: space(5), paddingHorizontal: space(2), paddingBottom: space(1.5) }}>
        <Text style={type.h1}>Your orders</Text>
        <Row style={{ gap: 8, marginTop: 12 }}>
          <Chip label="Active" active={tab === 'active'} onPress={() => setTab('active')} />
          <Chip label="Past orders" active={tab === 'past'} onPress={() => setTab('past')} />
        </Row>
      </View>
      {error ? <ErrorState error={error} onRetry={load} /> : !data ? <ListSkeleton /> : (
        <FlatList
          data={data.items}
          keyExtractor={(o) => String(o.id)}
          refreshing={refreshing}
          onRefresh={() => { setRefreshing(true); load(); }}
          contentContainerStyle={{ padding: space(2), gap: 12, paddingBottom: 140 }}
          ListEmptyComponent={tab === 'active'
            ? <Empty emoji="🍽️" title="No active orders" subtitle="Hungry? Your next meal is a few taps away." action="Order now" onAction={() => nav.tab('home')} />
            : <Empty emoji="🧾" title="No past orders yet" />}
          renderItem={({ item: o }) => (
            <Card onPress={() => nav.push('order', { orderId: o.id })} accessibilityLabel={`Order ${o.order_number}, ${STATUS[o.status]?.label}`}>
              <Row style={{ justifyContent: 'space-between', marginBottom: 8 }}>
                <Row style={{ gap: 8 }}>
                  <Text style={{ fontSize: 24 }}>{o.kitchen.emoji}</Text>
                  <View>
                    <Text style={type.h3}>{o.kitchen.name}</Text>
                    <Text style={type.small}>{o.order_number} · {fmtDate(o.created_at)}</Text>
                  </View>
                </Row>
                <Text style={type.h3}>{rupees(o.total_paise)}</Text>
              </Row>
              <Text style={[type.small, { color: colors.text }]} numberOfLines={1}>{o.items.map((i) => `${i.quantity} × ${i.name}`).join(', ')}</Text>
              <Row style={{ justifyContent: 'space-between', marginTop: 10 }}>
                <StatusPill status={o.status} />
                {o.payment_status === 'PENDING' && o.payment_method !== 'CASH' && o.status === 'PENDING_ACCEPTANCE'
                  ? <Text style={{ color: colors.red, fontWeight: '700', fontSize: 12 }}>Payment pending</Text>
                  : o.payment_status === 'REFUND_PENDING' ? <Text style={{ color: '#9A6700', fontWeight: '700', fontSize: 12 }}>Refund processing</Text>
                  : o.payment_status === 'REFUNDED' ? <Text style={{ color: colors.green, fontWeight: '700', fontSize: 12 }}>Refunded</Text> : null}
              </Row>
            </Card>
          )}
        />
      )}
    </View>
  );
}

const STEPS = [
  { key: 'created_at', label: 'Order placed' },
  { key: 'paid_at', label: 'Payment confirmed', online: true },
  { key: 'accepted_at', label: 'Accepted by kitchen' },
  { key: 'preparing_at', label: 'Being prepared' },
  { key: 'ready_at', label: 'Ready at counter' },
  { key: 'completed_at', label: 'Collected' },
];

function Timeline({ o }) {
  const steps = STEPS.filter((st) => !st.online || o.payment_method !== 'CASH');
  const current = steps.findIndex((st) => !o[st.key]);
  return (
    <View accessibilityLabel="Order progress">
      {steps.map((st, i) => {
        const done = !!o[st.key];
        const isNext = i === current && !['REJECTED', 'CANCELLED'].includes(o.status);
        return (
          <Row key={st.key} style={{ alignItems: 'flex-start', gap: 12 }}>
            <View style={{ alignItems: 'center', width: 22 }}>
              <View style={{ width: 22, height: 22, borderRadius: 11, alignItems: 'center', justifyContent: 'center', backgroundColor: done ? colors.green : isNext ? colors.yellow : colors.border }}>
                <Text style={{ color: '#fff', fontSize: 12, fontWeight: '900' }}>{done ? '✓' : ''}</Text>
              </View>
              {i < steps.length - 1 ? <View style={{ width: 2, height: 26, backgroundColor: done ? colors.green : colors.border }} /> : null}
            </View>
            <View style={{ flex: 1, flexDirection: 'row', justifyContent: 'space-between' }}>
              <Text style={[type.body, { fontWeight: done || isNext ? '700' : '400', color: done || isNext ? colors.text : colors.faint }]}>
                {st.label}{isNext ? ' …' : ''}
              </Text>
              <Text style={type.small}>{fmtTime(o[st.key])}</Text>
            </View>
          </Row>
        );
      })}
    </View>
  );
}

function PickupCard({ order }) {
  const [pick, setPick] = useState(null);
  const [left, setLeft] = useState(0);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      setPick(await api(`/v1/orders/${order.id}/pickup-code`));
      setError(null);
    } catch (e) {
      setError(e.message);
    }
  }, [order.id]);
  useEffect(() => { load(); }, [load, order.version]);
  useEffect(() => {
    if (!pick) return;
    const tick = () => {
      const s = Math.max(0, Math.round((new Date(pick.expires_at) - Date.now()) / 1000));
      setLeft(s);
      if (s === 0) load(); // server rotates expired codes
    };
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, [pick]);

  return (
    <Card style={{ alignItems: 'center', borderWidth: 2, borderColor: colors.green }}>
      <Text style={[type.label, { color: colors.green }]}>Show this at {order.kitchen.counter_location || 'the counter'}</Text>
      {error ? <Text style={{ color: colors.red, marginTop: 12 }}>{error}</Text> : !pick ? <ActivityIndicator style={{ margin: 40 }} color={colors.green} /> : (
        <>
          <View style={{ padding: 12, backgroundColor: '#fff', marginTop: 12 }} accessibilityLabel="Pickup QR code">
            <QRCode value={pick.qr_payload} size={180} color={colors.text} />
          </View>
          <Text style={[type.small, { marginTop: 8 }]}>or tell the cashier this code</Text>
          <Text style={{ fontSize: 40, fontWeight: '900', letterSpacing: 10, color: colors.text, marginTop: 4 }} accessibilityLabel={`Pickup code ${pick.code.split('').join(' ')}`}>
            {pick.code}
          </Text>
          <Text style={[type.small, { marginTop: 4 }]}>Refreshes in {Math.floor(left / 60)}:{String(left % 60).padStart(2, '0')} · one-time use</Text>
        </>
      )}
    </Card>
  );
}

function Stars({ value, onRate }) {
  return (
    <Row style={{ gap: 6 }}>
      {[1, 2, 3, 4, 5].map((n) => (
        <Pressable accessibilityRole="button" key={n} onPress={() => onRate(n)} accessibilityLabel={`Rate ${n} stars`} hitSlop={6}>
          <Text style={{ fontSize: 32, color: n <= value ? colors.yellow : colors.border }}>★</Text>
        </Pressable>
      ))}
    </Row>
  );
}

export function OrderScreen({ orderId }) {
  const { nav, toast, confirm, addToCart, setCart } = useApp();
  const [o, setO] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setO(await api(`/v1/orders/${orderId}`));
      setError(null);
    } catch (e) {
      setError(e);
    }
  }, [orderId]);
  useEffect(() => { load(); }, [load]);
  useLiveRefresh(load, (e) => e.order_id === orderId, 15000);

  if (error) return <View style={{ flex: 1, backgroundColor: colors.surface }}><TopBar title="Order" onBack={nav.pop} /><ErrorState error={error} onRetry={load} /></View>;
  if (!o) return <View style={{ flex: 1, backgroundColor: colors.surface }}><TopBar title="Order" onBack={nav.pop} /><ListSkeleton rows={3} /></View>;

  const unpaid = o.payment_method !== 'CASH' && ['PENDING', 'FAILED'].includes(o.payment_status) && o.status === 'PENDING_ACCEPTANCE';
  const closed = ['REJECTED', 'CANCELLED'].includes(o.status);

  const cancel = async () => {
    if (!(await confirm({ title: 'Cancel order?', message: 'The kitchen hasn’t accepted yet. Any payment will be refunded.', confirmText: 'Cancel order', cancelText: 'Keep', destructive: true }))) return;
    setBusy(true);
    try {
      setO(await api(`/v1/orders/${o.id}/cancel`, { method: 'POST' }));
      toast('Order cancelled');
    } catch (e) {
      toast(e.message, 'error');
      load();
    }
    setBusy(false);
  };

  const rate = async (n) => {
    try {
      await api(`/v1/orders/${o.id}/rate`, { method: 'POST', body: { rating: n } });
      toast('Thanks for rating!', 'success');
      load();
    } catch (e) {
      toast(e.message, 'error');
    }
  };

  const reorder = async () => {
    setBusy(true);
    try {
      const [q, kitchen] = await Promise.all([api(`/v1/orders/${o.id}/reorder`, { method: 'POST' }), api(`/v1/kitchens/${o.kitchen.id}`)]);
      const ok = q.lines.filter((l) => l.ok);
      if (!ok.length) {
        toast('None of these items are available right now');
      } else {
        const lines = ok.map((l) => ({
          key: `${l.menu_item_id}:${l.options.map((x) => x.choice_id).sort((a, b) => a - b).join(',')}`,
          menu_item_id: l.menu_item_id, name: l.name, emoji: l.emoji, is_veg: l.is_veg, quantity: l.quantity,
          choice_ids: l.options.map((x) => x.choice_id), options_label: l.options.map((x) => x.name).join(', '),
          unit_price_paise: l.unit_price_paise,
        }));
        setCart({ kitchen: { id: kitchen.id, name: kitchen.name, emoji: kitchen.emoji, college_id: kitchen.college_id }, lines, instructions: '' });
        if (q.problems.length) toast(`${q.problems.length} item(s) skipped: ${q.problems[0].message}`);
        nav.push('cart');
      }
    } catch (e) {
      toast(e.message, 'error');
    }
    setBusy(false);
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <TopBar title={`Order ${o.order_number}`} subtitle={`${o.kitchen.name} · ${fmtDate(o.created_at)}`} onBack={nav.pop} />
      <Scroll onRefresh={load} contentStyle={{ padding: space(2), gap: 12 }}>
        <Card style={{ backgroundColor: STATUS[o.status].bg, shadowOpacity: 0 }}>
          <Text style={{ fontSize: 22, fontWeight: '900', color: STATUS[o.status].color }}>{STATUS[o.status].icon} {STATUS[o.status].label}</Text>
          <Text style={{ color: STATUS[o.status].color, marginTop: 4, opacity: 0.9 }}>
            {o.status === 'PENDING_ACCEPTANCE' ? (unpaid ? 'Complete payment to send this order to the kitchen.' : 'The kitchen will accept your order shortly.')
              : o.status === 'ACCEPTED' || o.status === 'PREPARING' ? `Estimated ready in ~${o.eta_minutes} min. ETA is an estimate.`
              : o.status === 'READY' ? `Collect from ${o.kitchen.counter_location || 'the counter'}.`
              : o.status === 'COMPLETED' ? 'Enjoy your meal!'
              : o.reason}
          </Text>
          {o.ack_overdue ? <Text style={{ marginTop: 6, color: colors.red, fontWeight: '700' }}>Taking longer than usual — we’ve alerted the kitchen.</Text> : null}
        </Card>

        {unpaid ? <Btn title={o.payment_status === 'FAILED' ? 'Retry payment' : 'Complete payment'} onPress={() => nav.push('pay', { orderId: o.id })} /> : null}
        {o.status === 'READY' ? <PickupCard order={o} /> : null}
        {closed && o.payment_status === 'REFUND_PENDING' ? <Card><Text style={type.body}>💸 Refund of {rupees(o.total_paise)} initiated. It usually reflects within a few minutes in test mode.</Text></Card> : null}
        {closed && o.payment_status === 'REFUNDED' ? <Card><Text style={type.body}>✅ {rupees(o.total_paise)} refunded to your original payment method.</Text></Card> : null}

        {o.status === 'COMPLETED' ? (
          <Card style={{ alignItems: 'center' }}>
            <Text style={[type.h3, { marginBottom: 6 }]}>{o.rating ? 'You rated this order' : 'How was your food?'}</Text>
            <Stars value={o.rating || 0} onRate={o.rating ? () => {} : rate} />
          </Card>
        ) : null}

        {!closed ? <Card><Timeline o={o} /></Card> : null}

        <Card>
          <Text style={[type.h3, { marginBottom: 8 }]}>Items</Text>
          {o.items.map((it, i) => (
            <Row key={i} style={{ gap: 8, marginBottom: 8, alignItems: 'flex-start' }}>
              <View style={{ marginTop: 3 }}><VegMark veg={it.is_veg} size={12} /></View>
              <View style={{ flex: 1 }}>
                <Text style={type.body}>{it.quantity} × {it.name}</Text>
                {it.options.length ? <Text style={type.small}>{it.options.map((x) => x.name).join(', ')}</Text> : null}
              </View>
              <Text style={type.body}>{rupees(it.line_total_paise)}</Text>
            </Row>
          ))}
          {o.instructions ? <Text style={[type.small, { marginTop: 4 }]}>📝 {o.instructions}</Text> : null}
          <Divider />
          <Row style={{ justifyContent: 'space-between' }}><Text style={type.small}>Item total</Text><Text style={type.small}>{rupees(o.subtotal_paise)}</Text></Row>
          <Row style={{ justifyContent: 'space-between', marginTop: 4 }}><Text style={type.small}>GST</Text><Text style={type.small}>{rupees(o.tax_paise)}</Text></Row>
          <Row style={{ justifyContent: 'space-between', marginTop: 8 }}>
            <Text style={type.h3}>Total</Text>
            <Text style={type.h3}>{rupees(o.total_paise)}</Text>
          </Row>
          <Text style={[type.small, { marginTop: 4 }]}>
            {o.payment_method === 'CASH' ? 'Pay at counter' : o.payment_method === 'MOCK_CARD' ? 'Card (test)' : 'UPI (test)'} · {o.payment_status.replace('_', ' ').toLowerCase()}
          </Text>
        </Card>

        <Row style={{ gap: 12 }}>
          {o.status === 'PENDING_ACCEPTANCE' ? <Btn title="Cancel order" variant="danger" onPress={cancel} loading={busy} style={{ flex: 1 }} /> : null}
          {['COMPLETED', 'CANCELLED', 'REJECTED'].includes(o.status) ? <Btn title="Reorder" variant="secondary" onPress={reorder} loading={busy} style={{ flex: 1 }} /> : null}
          <Btn title="Get help" variant="ghost" onPress={() => nav.push('support', { orderId: o.id, orderNumber: o.order_number })} style={{ flex: 1 }} />
        </Row>
      </Scroll>
    </View>
  );
}

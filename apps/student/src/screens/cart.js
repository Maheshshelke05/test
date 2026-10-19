import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, Text, View } from 'react-native';
import { api, newIdempotencyKey } from '../api';
import { useApp } from '../store';
import { colors, radius, rupees, space, type } from '../theme';
import { Btn, Card, Divider, Empty, Field, Row, Scroll, Stepper, TopBar, VegMark } from '../ui';

const METHODS = [
  { id: 'MOCK_UPI', icon: '📱', label: 'UPI', sub: 'Test mode — no real money' },
  { id: 'MOCK_CARD', icon: '💳', label: 'Card', sub: 'Test mode — no real money' },
  { id: 'CASH', icon: '💵', label: 'Pay at counter', sub: 'Pay cash/UPI when you collect' },
];

export function CartScreen() {
  const { cart, setLineQty, clearCart, setInstructions, nav, toast, confirm } = useApp();
  const [quote, setQuote] = useState(null);
  const [quoteError, setQuoteError] = useState(null);
  const [method, setMethod] = useState('MOCK_UPI');
  const [placing, setPlacing] = useState(false);
  const idem = useRef(newIdempotencyKey());
  const payload = () => ({
    kitchen_id: cart.kitchen.id,
    items: cart.lines.map((l) => ({ menu_item_id: l.menu_item_id, quantity: l.quantity, choice_ids: l.choice_ids })),
  });

  const refreshQuote = async () => {
    if (!cart.kitchen) return;
    try {
      setQuote(await api('/v1/orders/quote', { method: 'POST', body: payload() }));
      setQuoteError(null);
    } catch (e) {
      setQuoteError(e);
    }
  };

  useEffect(() => {
    idem.current = newIdempotencyKey(); // a changed cart is a new checkout attempt
    const t = setTimeout(refreshQuote, 250);
    return () => clearTimeout(t);
  }, [JSON.stringify(cart.lines)]);

  if (!cart.kitchen) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.surface }}>
        <TopBar title="Your cart" onBack={nav.pop} />
        <Empty emoji="🛒" title="Your cart is empty" subtitle="Add something tasty from a campus kitchen." action="Browse kitchens" onAction={() => nav.tab('kitchens')} />
      </View>
    );
  }

  const problemFor = (id) => quote?.problems?.find((p) => p.menu_item_id === id);

  const place = async () => {
    setPlacing(true);
    try {
      const order = await api('/v1/orders', {
        method: 'POST',
        headers: { 'Idempotency-Key': idem.current },
        body: { ...payload(), payment_method: method, instructions: cart.instructions || null, expected_total_paise: quote?.total_paise },
      });
      clearCart();
      if (method === 'CASH') {
        toast(`Order ${order.order_number} placed!`, 'success');
        nav.replace('order', { orderId: order.id });
      } else {
        nav.replace('pay', { orderId: order.id });
      }
    } catch (e) {
      if (e.code === 'PRICE_CHANGED') {
        const q = e.fields.quote;
        setQuote(q);
        await confirm({ title: 'Prices updated', message: `The kitchen changed some prices. New total is ${rupees(q.total_paise)}. Review and place the order again.`, confirmText: 'OK', hideCancel: true });
      } else {
        toast(e.message, 'error');
        refreshQuote();
      }
    } finally {
      setPlacing(false);
    }
  };

  const clear = async () => {
    if (await confirm({ title: 'Clear cart?', message: 'Remove all items from your cart?', confirmText: 'Clear', destructive: true })) {
      clearCart();
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <TopBar title="Checkout" subtitle={`${cart.kitchen.emoji} ${cart.kitchen.name}`} onBack={nav.pop}
        right={<Pressable accessibilityRole="button" onPress={clear} hitSlop={10} accessibilityLabel="Clear cart"><Text style={{ color: colors.red, fontWeight: '700' }}>Clear</Text></Pressable>} />
      <Scroll contentStyle={{ padding: space(2), gap: 12, paddingBottom: 180 }}>
        <Card style={{ backgroundColor: colors.greenSoft, shadowOpacity: 0 }}>
          <Row style={{ gap: 10 }}>
            <Text style={{ fontSize: 24 }}>🏃</Text>
            <View style={{ flex: 1 }}>
              <Text style={type.h3}>Counter pickup · ASAP</Text>
              <Text style={type.small}>{quote ? `Ready in about ${quote.eta_minutes} min (estimate, not a guarantee)` : 'Calculating…'}</Text>
            </View>
          </Row>
        </Card>
        {quote?.closed_reason ? (
          <Card style={{ backgroundColor: colors.redSoft, shadowOpacity: 0 }}>
            <Text style={{ color: colors.red, fontWeight: '700' }}>{quote.closed_reason}</Text>
          </Card>
        ) : null}

        <Card>
          {cart.lines.map((l, i) => {
            const p = problemFor(l.menu_item_id);
            const server = quote?.lines?.[i];
            return (
              <View key={l.key}>
                {i ? <Divider /> : null}
                <Row style={{ gap: 10, alignItems: 'flex-start' }}>
                  <View style={{ marginTop: 3 }}><VegMark veg={l.is_veg} size={12} /></View>
                  <View style={{ flex: 1 }}>
                    <Text style={[type.body, { fontWeight: '600' }]}>{l.name}</Text>
                    {l.options_label ? <Text style={type.small}>{l.options_label}</Text> : null}
                    {p ? <Text style={[type.small, { color: colors.red, fontWeight: '600' }]}>{p.message}</Text> : null}
                    {server && server.unit_price_paise !== l.unit_price_paise ? (
                      <Text style={[type.small, { color: '#9A6700', fontWeight: '600' }]}>Price updated to {rupees(server.unit_price_paise)}</Text>
                    ) : null}
                  </View>
                  <View style={{ alignItems: 'flex-end', gap: 6 }}>
                    <Stepper qty={l.quantity} small max={l.max_per_order || 50} onInc={() => setLineQty(l.key, l.quantity + 1)} onDec={() => setLineQty(l.key, l.quantity - 1)} />
                    <Text style={[type.body, { fontWeight: '700' }]}>{rupees(server?.line_total_paise ?? l.unit_price_paise * l.quantity)}</Text>
                  </View>
                </Row>
              </View>
            );
          })}
          <Divider />
          <Pressable accessibilityRole="button" onPress={() => nav.push('kitchen', { kitchenId: cart.kitchen.id })}><Text style={{ color: colors.green, fontWeight: '700' }}>+ Add more items</Text></Pressable>
        </Card>

        <Card>
          <Field label="Cooking instructions (optional)" placeholder="e.g. less spicy, no onion" value={cart.instructions} onChangeText={setInstructions} maxLength={300} style={{ marginBottom: 0 }} />
        </Card>

        <Card>
          <Text style={[type.h3, { marginBottom: 8 }]}>Pay with</Text>
          {METHODS.map((m) => (
            <Pressable key={m.id} onPress={() => setMethod(m.id)} accessibilityRole="radio" accessibilityState={{ selected: method === m.id }}
              style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 10, gap: 12 }}>
              <Text style={{ fontSize: 22 }}>{m.icon}</Text>
              <View style={{ flex: 1 }}>
                <Text style={[type.body, { fontWeight: '600' }]}>{m.label}</Text>
                <Text style={type.small}>{m.sub}</Text>
              </View>
              <View style={{ width: 22, height: 22, borderRadius: 11, borderWidth: 2, borderColor: method === m.id ? colors.green : colors.border, alignItems: 'center', justifyContent: 'center' }}>
                {method === m.id ? <View style={{ width: 12, height: 12, borderRadius: 6, backgroundColor: colors.green }} /> : null}
              </View>
            </Pressable>
          ))}
        </Card>

        <Card>
          <Text style={[type.h3, { marginBottom: 8 }]}>Bill details</Text>
          {quote ? (
            <>
              <Row style={{ justifyContent: 'space-between', marginBottom: 6 }}><Text style={type.body}>Item total</Text><Text style={type.body}>{rupees(quote.subtotal_paise)}</Text></Row>
              <Row style={{ justifyContent: 'space-between', marginBottom: 6 }}><Text style={type.body}>GST (5%)</Text><Text style={type.body}>{rupees(quote.tax_paise)}</Text></Row>
              {quote.fee_paise ? <Row style={{ justifyContent: 'space-between', marginBottom: 6 }}><Text style={type.body}>Platform fee</Text><Text style={type.body}>{rupees(quote.fee_paise)}</Text></Row> : null}
              <Divider style={{ marginVertical: 8 }} />
              <Row style={{ justifyContent: 'space-between' }}><Text style={type.h3}>To pay</Text><Text style={type.h3}>{rupees(quote.total_paise)}</Text></Row>
            </>
          ) : quoteError ? (
            <Text style={{ color: colors.red }}>{quoteError.message}</Text>
          ) : (
            <ActivityIndicator color={colors.green} />
          )}
        </Card>
        <Text style={[type.small, { textAlign: 'center' }]}>Prices and availability are confirmed by the kitchen’s live menu when you place the order.</Text>
      </Scroll>

      <View style={{ position: 'absolute', left: 0, right: 0, bottom: 0, backgroundColor: colors.surface, padding: space(2), paddingBottom: space(3), borderTopWidth: 1, borderTopColor: colors.border }}>
        <Btn
          title={quote ? `${method === 'CASH' ? 'Place order' : 'Proceed to pay'} · ${rupees(quote.total_paise)}` : 'Checking cart…'}
          onPress={place}
          loading={placing}
          disabled={!quote || !quote.can_order}
        />
      </View>
    </View>
  );
}

export function PaymentScreen({ orderId }) {
  const { nav, toast } = useApp();
  const [order, setOrder] = useState(null);
  const [state, setState] = useState('idle');

  useEffect(() => {
    api(`/v1/orders/${orderId}`).then(setOrder).catch((e) => toast(e.message, 'error'));
  }, [orderId]);

  const pay = async (outcome) => {
    setState('processing');
    try {
      const r = await api(`/v1/orders/${orderId}/pay`, { method: 'POST', body: { outcome } });
      setOrder(r.order);
      if (r.order.payment_status === 'PAID') {
        setState('success');
        setTimeout(() => nav.replace('order', { orderId }), 900);
      } else {
        setState('failed');
      }
    } catch (e) {
      // Timeouts are not failures: we show "processing" and let the server reconcile.
      if (e.code === 'NETWORK') setState('unknown');
      else {
        toast(e.message, 'error');
        setState('idle');
      }
    }
  };

  if (!order) return <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.surface }}><ActivityIndicator color={colors.green} size="large" /></View>;

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <TopBar title="Payment" subtitle={`Order ${order.order_number}`} onBack={() => nav.replace('order', { orderId })} />
      <View style={{ padding: space(3), alignItems: 'center' }}>
        <View style={{ backgroundColor: colors.yellowSoft, borderRadius: radius.md, paddingHorizontal: 12, paddingVertical: 6, marginBottom: space(3) }}>
          <Text style={[type.small, { color: '#7A5B00', fontWeight: '700' }]}>SANDBOX GATEWAY · No real money moves</Text>
        </View>
        <Text style={type.small}>Amount</Text>
        <Text style={{ fontSize: 44, fontWeight: '900', color: colors.text }}>{rupees(order.total_paise)}</Text>
        <Text style={[type.small, { marginBottom: space(4) }]}>{order.kitchen.name} · {order.payment_method === 'MOCK_CARD' ? 'Card' : 'UPI'}</Text>

        {state === 'success' ? (
          <Text style={{ fontSize: 22, fontWeight: '800', color: colors.green }}>✅ Payment successful</Text>
        ) : state === 'processing' ? (
          <><ActivityIndicator color={colors.green} size="large" /><Text style={[type.body, { marginTop: 12 }]}>Confirming with bank…</Text></>
        ) : state === 'unknown' ? (
          <View style={{ alignItems: 'center' }}>
            <Text style={[type.h3, { textAlign: 'center' }]}>⏳ Payment processing</Text>
            <Text style={[type.small, { textAlign: 'center', marginVertical: 8 }]}>We couldn’t confirm yet. If money was debited it will reflect shortly — don’t pay twice.</Text>
            <Btn title="Check order status" onPress={() => nav.replace('order', { orderId })} />
          </View>
        ) : (
          <View style={{ width: '100%', gap: 12 }}>
            {state === 'failed' ? (
              <View style={{ backgroundColor: colors.redSoft, padding: 12, borderRadius: radius.md }}>
                <Text style={{ color: colors.red, fontWeight: '700' }}>Payment failed. No money was taken. You can retry.</Text>
              </View>
            ) : null}
            <Btn title={`${state === 'failed' ? 'Retry' : 'Pay'} ${rupees(order.total_paise)}`} onPress={() => pay('success')} />
            <Btn title="Simulate failed payment" variant="danger" onPress={() => pay('fail')} />
            <Text style={[type.small, { textAlign: 'center' }]}>Unpaid orders are cancelled automatically after 15 minutes.</Text>
          </View>
        )}
      </View>
    </View>
  );
}

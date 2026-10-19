import { CameraView, useCameraPermissions } from 'expo-camera';
import { useCallback, useEffect, useRef, useState } from 'react';
import { FlatList, Pressable, ScrollView, Switch, Text, View } from 'react-native';
import { api } from '../api';
import { useKitchen, useLive } from '../store';
import { colors, radius, rupees, space, STATUS, type } from '../theme';
import { Btn, Card, Chip, Empty, ErrorState, Field, ListSkeleton, Row, Sheet, VegMark } from '../ui';

const TABS = [
  { id: 'PENDING_ACCEPTANCE', label: 'New' },
  { id: 'ACCEPTED', label: 'Accepted' },
  { id: 'PREPARING', label: 'Preparing' },
  { id: 'READY', label: 'Ready' },
  { id: 'COMPLETED', label: 'Done (24h)' },
];
const REJECT_REASONS = ['Item out of stock', 'Kitchen too busy', 'Closing soon', 'Duplicate order'];

function minutesAgo(iso) {
  const m = Math.max(0, Math.round((Date.now() - new Date(iso)) / 60000));
  return m < 1 ? 'just now' : m < 60 ? `${m} min ago` : `${Math.floor(m / 60)}h ${m % 60}m ago`;
}

function OrderCard({ o, onAction, busy, can }) {
  const late = o.status === 'PENDING_ACCEPTANCE' && o.ack_overdue;
  const age = o.accepted_at && ['ACCEPTED', 'PREPARING'].includes(o.status)
    ? Math.round((Date.now() - new Date(o.accepted_at)) / 60000) : null;
  const overdue = age != null && o.eta_minutes && age > o.eta_minutes;
  return (
    <Card testID="order-card" style={[{ gap: 10 }, (late || overdue) && { borderWidth: 2, borderColor: colors.red }]}>
      <Row style={{ justifyContent: 'space-between' }}>
        <View>
          <Text style={{ fontSize: 20, fontWeight: '900', color: colors.text }}>{o.order_number}</Text>
          <Text style={type.small}>{o.student.name} · ••{o.student.phone_last4} · {minutesAgo(o.created_at)}</Text>
        </View>
        <View style={{ alignItems: 'flex-end' }}>
          <Text style={type.h3}>{rupees(o.total_paise)}</Text>
          <Text style={{ fontSize: 11, fontWeight: '800', color: o.payment_status === 'PAID' ? colors.green : '#9A6700' }}>
            {o.payment_method === 'CASH' ? (o.payment_status === 'PAID' ? 'CASH · PAID' : 'COLLECT CASH') : o.payment_status}
          </Text>
        </View>
      </Row>
      <View style={{ backgroundColor: colors.bg, borderRadius: radius.md, padding: 10, gap: 6 }}>
        {o.items.map((it, i) => (
          <Row key={i} style={{ gap: 8, alignItems: 'flex-start' }}>
            <View style={{ marginTop: 4 }}><VegMark veg={it.is_veg} size={12} /></View>
            <Text style={{ fontSize: 17, fontWeight: '800', minWidth: 28 }}>{it.quantity}×</Text>
            <View style={{ flex: 1 }}>
              <Text style={{ fontSize: 16, fontWeight: '600', color: colors.text }}>{it.name}</Text>
              {it.options.length ? <Text style={type.small}>{it.options.map((x) => x.name).join(', ')}</Text> : null}
            </View>
          </Row>
        ))}
        {o.instructions ? <Text style={{ color: '#9A6700', fontWeight: '700' }}>📝 {o.instructions}</Text> : null}
      </View>
      {late ? <Text style={{ color: colors.red, fontWeight: '800' }}>⚠️ Waiting too long — accept or reject now</Text> : null}
      {age != null ? (
        <Text style={{ fontWeight: '700', color: overdue ? colors.red : colors.muted }}>
          ⏱ {age} min since accepted · ETA {o.eta_minutes} min{overdue ? ' — running late' : ''}
        </Text>
      ) : null}
      {o.status === 'PENDING_ACCEPTANCE' && can.frontDesk ? (
        <Row style={{ gap: 10 }}>
          <Btn title="Reject" variant="danger" onPress={() => onAction('reject', o)} style={{ flex: 1 }} disabled={busy} />
          <Btn title="Accept" onPress={() => onAction('accept', o)} style={{ flex: 2 }} loading={busy} />
        </Row>
      ) : null}
      {o.status === 'ACCEPTED' && can.cook ? <Btn title="👨‍🍳  Start preparing" variant="yellow" onPress={() => onAction('PREPARING', o)} loading={busy} /> : null}
      {o.status === 'PREPARING' && can.cook ? <Btn title="✅  Mark ready for pickup" onPress={() => onAction('READY', o)} loading={busy} /> : null}
      {o.status === 'READY' && can.frontDesk ? <Btn title="Verify pickup code" variant="secondary" onPress={() => onAction('verify', o)} /> : null}
      {['ACCEPTED', 'PREPARING', 'READY'].includes(o.status) && can.manage ? (
        <Pressable onPress={() => onAction('cancel', o)} accessibilityRole="button"><Text style={{ color: colors.red, textAlign: 'center', fontWeight: '600' }}>Cancel order</Text></Pressable>
      ) : null}
      {['COMPLETED', 'REJECTED', 'CANCELLED'].includes(o.status) ? (
        <Row style={{ justifyContent: 'space-between' }}>
          <Text style={{ fontWeight: '700', color: STATUS[o.status].color === '#FFFFFF' ? colors.green : STATUS[o.status].color }}>{STATUS[o.status].label}</Text>
          {o.reason ? <Text style={type.small}>{o.reason}</Text> : null}
        </Row>
      ) : null}
    </Card>
  );
}

export function PickupVerifier({ orderId, onDone }) {
  const { kitchenId, toast } = useKitchen();
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const [scanning, setScanning] = useState(false);
  const [permission, requestPermission] = useCameraPermissions();
  const scannedRef = useRef(false);

  const startScan = async () => {
    const p = permission?.granted ? permission : await requestPermission();
    if (!p?.granted) return setError('Camera permission denied. Type the 6-digit code instead.');
    scannedRef.current = false;
    setError(null);
    setScanning(true);
  };

  const onScanned = ({ data }) => {
    if (scannedRef.current) return; // the scanner fires repeatedly for the same frame
    scannedRef.current = true;
    setScanning(false);
    if (!String(data).startsWith('CBPICKUP:')) return setError('That QR is not a CampusBite pickup code');
    setCode(data);
    verify(data);
  };

  const verify = async (value = code) => {
    setBusy(true);
    setError(null);
    setResult(null); // never leave a previous success on screen next to a new failure
    try {
      const o = await api(`/v1/kitchen/kitchens/${kitchenId}/verify-pickup`, {
        method: 'POST',
        body: { code: value.trim(), order_id: orderId || null },
      });
      setResult(o);
      setCode('');
      toast(`${o.order_number} handed over`, 'success');
      onDone?.(o);
    } catch (e) {
      setError(e.message);
    }
    setBusy(false);
  };

  return (
    <View>
      {scanning ? (
        <View style={{ height: 280, borderRadius: radius.lg, overflow: 'hidden', marginBottom: 12, backgroundColor: '#000' }}>
          <CameraView style={{ flex: 1 }} facing="back" barcodeScannerSettings={{ barcodeTypes: ['qr'] }} onBarcodeScanned={onScanned} />
          <View pointerEvents="none" style={{ position: 'absolute', top: 50, left: '20%', right: '20%', bottom: 50, borderWidth: 3, borderColor: colors.yellow, borderRadius: 16 }} />
          <Pressable accessibilityRole="button" onPress={() => setScanning(false)} accessibilityLabel="Stop scanning"
            style={{ position: 'absolute', top: 10, right: 10, backgroundColor: 'rgba(0,0,0,0.6)', borderRadius: 16, paddingHorizontal: 12, paddingVertical: 6 }}>
            <Text style={{ color: '#fff', fontWeight: '700' }}>Close ✕</Text>
          </Pressable>
        </View>
      ) : (
        <Btn title="Scan student's QR" icon="📷" variant="yellow" onPress={startScan} style={{ marginBottom: 14 }} />
      )}
      <Field label="Or type the 6-digit pickup code" value={code} onChangeText={setCode} autoFocus={!scanning}
        keyboardType={code.startsWith('CB') ? 'default' : 'number-pad'} maxLength={40} error={error} onSubmitEditing={() => verify()}
        inputStyle={{ fontSize: 28, letterSpacing: 8, textAlign: 'center', height: 64 }} placeholder="••••••" />
      <Btn title="Verify & hand over" onPress={() => verify()} loading={busy} disabled={code.trim().length < 6} />
      {result ? (
        <Card style={{ marginTop: 16, backgroundColor: colors.greenSoft, shadowOpacity: 0 }}>
          <Text style={{ fontSize: 20, fontWeight: '900', color: colors.green }}>✅ {result.order_number} completed</Text>
          <Text style={type.body}>{result.student.name} · {result.items.map((i) => `${i.quantity}× ${i.name}`).join(', ')}</Text>
          {result.payment_method === 'CASH' ? <Text style={{ fontWeight: '800', marginTop: 6 }}>💵 Collect {rupees(result.total_paise)} cash</Text> : null}
        </Card>
      ) : null}
    </View>
  );
}

export function OrdersScreen() {
  const { kitchen, kitchenId, can, toast, confirm, live, loadKitchens, clearNew } = useKitchen();
  const [tab, setTab] = useState('PENDING_ACCEPTANCE');
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [acceptFor, setAcceptFor] = useState(null);
  const [rejectFor, setRejectFor] = useState(null);
  const [verifyFor, setVerifyFor] = useState(null);
  const [reason, setReason] = useState('');

  const load = useCallback(async () => {
    try {
      setData(await api(`/v1/kitchen/kitchens/${kitchenId}/orders?status=${tab}`));
      setError(null);
    } catch (e) {
      setError(e);
      // Access to this kitchen was removed: refresh memberships so the app moves on.
      if (e.status === 404) loadKitchens().catch(() => {});
    }
  }, [kitchenId, tab]);
  useEffect(() => {
    setData(null);
    load();
    if (tab === 'PENDING_ACCEPTANCE') clearNew();
  }, [load]);
  useLive(load, (e) => ['order_updated', 'order_created', 'new_order', 'ack_overdue'].includes(e.type), 10000);

  const run = async (o, fn) => {
    setBusyId(o.id);
    try {
      await fn();
    } catch (e) {
      toast(e.message, 'error');
    }
    setBusyId(null);
    load();
  };

  const onAction = async (action, o) => {
    if (action === 'accept') return setAcceptFor(o);
    if (action === 'reject') { setReason(''); return setRejectFor(o); }
    if (action === 'verify') return setVerifyFor(o);
    if (action === 'cancel') {
      if (!(await confirm({ title: `Cancel ${o.order_number}?`, message: 'The student will be notified and refunded if paid.', confirmText: 'Cancel order', destructive: true }))) return;
      return run(o, () => api(`/v1/kitchen/orders/${o.id}/cancel`, { method: 'POST', body: { version: o.version, reason: 'Cancelled by kitchen' } }));
    }
    run(o, () => api(`/v1/kitchen/orders/${o.id}/status`, { method: 'PATCH', body: { version: o.version, status: action } }));
  };

  const accept = (eta) => {
    const o = acceptFor;
    setAcceptFor(null);
    run(o, () => api(`/v1/kitchen/orders/${o.id}/accept`, { method: 'POST', body: { version: o.version, eta_minutes: eta } }));
  };
  const reject = () => {
    const o = rejectFor;
    setRejectFor(null);
    run(o, () => api(`/v1/kitchen/orders/${o.id}/reject`, { method: 'POST', body: { version: o.version, reason } }));
  };

  const toggleAccepting = async (v) => {
    try {
      await api(`/v1/kitchen/kitchens/${kitchenId}`, { method: 'PATCH', body: { is_accepting: v } });
      await loadKitchens();
      toast(v ? 'Now accepting orders' : 'Paused new orders');
    } catch (e) {
      toast(e.message, 'error');
    }
  };
  const toggleBusy = async (v) => {
    try {
      await api(`/v1/kitchen/kitchens/${kitchenId}`, { method: 'PATCH', body: { busy_mode: v } });
      await loadKitchens();
      toast(v ? 'Busy mode on: +10 min shown to students' : 'Busy mode off');
    } catch (e) {
      toast(e.message, 'error');
    }
  };

  const counts = data?.counts || {};
  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <View style={{ backgroundColor: colors.green, paddingTop: space(5), paddingHorizontal: space(2), paddingBottom: space(1.5) }}>
        <Row style={{ justifyContent: 'space-between' }}>
          <View style={{ flex: 1 }}>
            <Text style={{ color: '#fff', fontSize: 20, fontWeight: '900' }} numberOfLines={1}>{kitchen.emoji} {kitchen.name}</Text>
            <Text style={{ color: '#CDE9D6', fontSize: 12 }}>{live ? '🟢 Live' : '🟡 Reconnecting…'} · {kitchen.my_role.replace('kitchen_', '')}</Text>
          </View>
        </Row>
        {can.manage ? (
          <Row style={{ gap: 16, marginTop: 12 }}>
            <Row style={{ gap: 8 }}>
              <Switch value={kitchen.is_accepting} onValueChange={toggleAccepting} trackColor={{ true: colors.yellow, false: '#4B6B57' }} thumbColor="#fff"
                accessibilityLabel="Accepting orders" />
              <Text style={{ color: '#fff', fontWeight: '700' }}>{kitchen.is_accepting ? 'Accepting orders' : 'Paused'}</Text>
            </Row>
            <Row style={{ gap: 8 }}>
              <Switch value={kitchen.busy_mode} onValueChange={toggleBusy} trackColor={{ true: colors.yellow, false: '#4B6B57' }} thumbColor="#fff"
                accessibilityLabel="Busy mode" />
              <Text style={{ color: '#fff', fontWeight: '700' }}>Busy</Text>
            </Row>
          </Row>
        ) : null}
      </View>
      {kitchen.status === 'PENDING' ? (
        <View style={{ backgroundColor: colors.yellowSoft, padding: 12 }}>
          <Text style={{ fontWeight: '700' }}>⏳ Awaiting CampusBite approval. Set up your menu — students will see it once approved.</Text>
        </View>
      ) : null}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexGrow: 0, backgroundColor: colors.surface }}
        contentContainerStyle={{ gap: 8, padding: space(1.5) }}>
        {TABS.map((t) => (
          <Chip key={t.id} active={tab === t.id} onPress={() => setTab(t.id)}
            label={`${t.label}${counts[t.id] ? ` (${counts[t.id]})` : ''}`}
            style={t.id === 'PENDING_ACCEPTANCE' && counts[t.id] ? { borderColor: colors.red, borderWidth: 2 } : undefined} />
        ))}
      </ScrollView>
      {error ? <ErrorState error={error} onRetry={load} /> : !data ? <ListSkeleton /> : (
        <FlatList
          data={data.items}
          keyExtractor={(o) => String(o.id)}
          contentContainerStyle={{ padding: space(2), gap: 12, paddingBottom: 100 }}
          numColumns={1}
          ListEmptyComponent={<Empty emoji={tab === 'PENDING_ACCEPTANCE' ? '😌' : '📭'} title={tab === 'PENDING_ACCEPTANCE' ? 'No new orders' : 'Nothing here'}
            subtitle={tab === 'PENDING_ACCEPTANCE' ? 'New orders appear here instantly with a chime.' : undefined} />}
          renderItem={({ item }) => <OrderCard o={item} onAction={onAction} busy={busyId === item.id} can={can} />}
        />
      )}

      <Sheet visible={!!acceptFor} onClose={() => setAcceptFor(null)} title={`Accept ${acceptFor?.order_number}`}>
        <Text style={[type.body, { marginBottom: 12 }]}>How long until it’s ready?</Text>
        <Row style={{ gap: 10, flexWrap: 'wrap' }}>
          {[5, 10, 15, 20, 30].map((m) => (
            <Btn key={m} title={`${m} min`} variant={m === kitchen.prep_minutes ? 'primary' : 'secondary'} onPress={() => accept(m)} style={{ flexGrow: 1, minWidth: 90 }} />
          ))}
        </Row>
      </Sheet>

      <Sheet visible={!!rejectFor} onClose={() => setRejectFor(null)} title={`Reject ${rejectFor?.order_number}`}>
        <Text style={[type.small, { marginBottom: 10 }]}>The student is notified with this reason{rejectFor?.payment_status === 'PAID' ? ' and refunded automatically' : ''}.</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
          {REJECT_REASONS.map((r) => <Chip key={r} label={r} active={reason === r} onPress={() => setReason(r)} />)}
        </View>
        <Field placeholder="Or type a reason" value={reason} onChangeText={setReason} />
        <Btn title="Reject order" variant="danger" onPress={reject} disabled={reason.trim().length < 3} />
      </Sheet>

      <Sheet visible={!!verifyFor} onClose={() => setVerifyFor(null)} title={`Hand over ${verifyFor?.order_number}`}>
        {verifyFor ? <PickupVerifier orderId={verifyFor.id} onDone={() => { setTimeout(() => setVerifyFor(null), 1200); load(); }} /> : null}
      </Sheet>
    </View>
  );
}

export function VerifyScreen() {
  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <View style={{ backgroundColor: colors.green, paddingTop: space(5), padding: space(2) }}>
        <Text style={{ color: '#fff', fontSize: 20, fontWeight: '900' }}>Pickup counter</Text>
        <Text style={{ color: '#CDE9D6' }}>Scan the student’s QR or type their code. Each code works once.</Text>
      </View>
      <View style={{ padding: space(2) }}>
        <Card><PickupVerifier /></Card>
      </View>
    </View>
  );
}

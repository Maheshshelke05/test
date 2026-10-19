import { useCallback, useEffect, useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import { api } from '../api';
import { useKitchen } from '../store';
import { colors, radius, rupees, space, type } from '../theme';
import { Btn, Card, Chip, Divider, ErrorState, Field, ListSkeleton, Row, Scroll, TopBar } from '../ui';

function Stat({ label, value, sub, tone }) {
  return (
    <View style={{ flexBasis: '47%', flexGrow: 1, backgroundColor: colors.surface, borderRadius: radius.lg, padding: 14 }}>
      <Text style={type.small}>{label}</Text>
      <Text style={{ fontSize: 22, fontWeight: '900', color: tone || colors.text, marginTop: 4 }}>{value}</Text>
      {sub ? <Text style={type.small}>{sub}</Text> : null}
    </View>
  );
}

function Bars({ rows, valueKey, labelKey, format = (v) => v }) {
  const max = Math.max(1, ...rows.map((r) => r[valueKey]));
  return (
    <View style={{ flexDirection: 'row', alignItems: 'flex-end', height: 140, gap: 4 }} accessibilityLabel="Bar chart">
      {rows.map((r, i) => (
        <View key={i} style={{ flex: 1, alignItems: 'center' }}>
          <Text style={{ fontSize: 9, color: colors.muted }}>{r[valueKey] ? format(r[valueKey]) : ''}</Text>
          <View style={{ width: '80%', height: Math.max(2, (r[valueKey] / max) * 100), backgroundColor: colors.green, borderRadius: 4 }} />
          <Text style={{ fontSize: 9, color: colors.muted, marginTop: 4 }} numberOfLines={1}>{r[labelKey]}</Text>
        </View>
      ))}
    </View>
  );
}

export function ReportsScreen({ onBack }) {
  const { kitchenId } = useKitchen();
  const [days, setDays] = useState(7);
  const [r, setR] = useState(null);
  const [error, setError] = useState(null);
  const load = useCallback(() => {
    setR(null);
    api(`/v1/kitchen/kitchens/${kitchenId}/reports?days=${days}`).then((x) => { setR(x); setError(null); }).catch(setError);
  }, [kitchenId, days]);
  useEffect(() => { load(); }, [load]);

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <TopBar title="Sales & reports" onBack={onBack} />
      <Row style={{ gap: 8, padding: space(2), paddingBottom: 0 }}>
        {[1, 7, 30].map((d) => <Chip key={d} label={d === 1 ? 'Today' : `${d} days`} active={days === d} onPress={() => setDays(d)} />)}
      </Row>
      {error ? <ErrorState error={error} onRetry={load} /> : !r ? <ListSkeleton rows={3} /> : (
        <Scroll contentStyle={{ padding: space(2), gap: 12 }}>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
            <Stat label="Gross sales" value={rupees(r.gross_sales_paise)} sub={`${r.completed_orders} completed orders`} />
            <Stat label="Your net payout" value={rupees(r.net_payout_paise)} sub={`after ${rupees(r.platform_commission_paise)} commission`} tone={colors.green} />
            <Stat label="Avg order value" value={rupees(r.avg_order_paise)} />
            <Stat label="Cancelled / rejected" value={String(r.cancelled_orders)} sub={r.refunds_paise ? `${rupees(r.refunds_paise)} refunded` : undefined} tone={r.cancelled_orders ? colors.red : undefined} />
            <Stat label="Prep time p50" value={r.prep_p50_min != null ? `${r.prep_p50_min} min` : '—'} sub={r.prep_p90_min != null ? `p90 ${r.prep_p90_min} min` : undefined} />
            <Stat label="GST collected" value={rupees(r.tax_paise)} />
          </View>
          {r.by_day.length ? (
            <Card>
              <Text style={[type.h3, { marginBottom: 12 }]}>Daily sales</Text>
              <Bars rows={r.by_day.slice(-14).map((d) => ({ ...d, day: d.date.slice(8) }))} valueKey="sales_paise" labelKey="day" format={(v) => `₹${Math.round(v / 100)}`} />
            </Card>
          ) : null}
          <Card>
            <Text style={[type.h3, { marginBottom: 12 }]}>Peak hours (orders)</Text>
            <Bars rows={r.by_hour.filter((h) => h.hour >= 7 && h.hour <= 22).map((h) => ({ ...h, label: `${h.hour}` }))} valueKey="orders" labelKey="label" />
          </Card>
          <Card>
            <Text style={[type.h3, { marginBottom: 8 }]}>Top items</Text>
            {r.top_items.length ? r.top_items.map((t, i) => (
              <Row key={t.name} style={{ justifyContent: 'space-between', paddingVertical: 6 }}>
                <Text style={type.body}>{i + 1}. {t.name}</Text>
                <Text style={type.small}>{t.quantity} sold · {rupees(t.sales_paise)}</Text>
              </Row>
            )) : <Text style={type.small}>No sales in this period.</Text>}
          </Card>
          <Text style={[type.small, { textAlign: 'center' }]}>Cancelled and refunded orders are excluded from sales. Times in {r.timezone}.</Text>
        </Scroll>
      )}
    </View>
  );
}

const ROLES = [
  ['kitchen_cashier', 'Cashier', 'Accept orders, verify pickups'],
  ['kitchen_cook', 'Cook', 'Prepare and mark ready'],
  ['kitchen_manager', 'Manager', 'Everything except ownership'],
];

export function StaffScreen({ onBack }) {
  const { kitchenId, toast, confirm, can } = useKitchen();
  const [staff, setStaff] = useState(null);
  const [form, setForm] = useState({ phone: '', name: '', role: 'kitchen_cashier' });
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => api(`/v1/kitchen/kitchens/${kitchenId}/staff`).then((r) => setStaff(r.items)).catch((e) => toast(e.message, 'error')), [kitchenId]);
  useEffect(() => { load(); }, [load]);

  const add = async () => {
    setBusy(true);
    try {
      await api(`/v1/kitchen/kitchens/${kitchenId}/staff`, { method: 'POST', body: { ...form, name: form.name || null } });
      toast('Staff added. They can log in with their number.', 'success');
      setForm({ phone: '', name: '', role: 'kitchen_cashier' });
      load();
    } catch (e) {
      toast(e.message, 'error');
    }
    setBusy(false);
  };
  const remove = async (m) => {
    if (!(await confirm({ title: `Remove ${m.name || m.phone}?`, message: 'They lose access immediately.', confirmText: 'Remove', destructive: true }))) return;
    try {
      await api(`/v1/kitchen/kitchens/${kitchenId}/staff/${m.user_id}`, { method: 'DELETE' });
      load();
    } catch (e) {
      toast(e.message, 'error');
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <TopBar title="Staff & roles" onBack={onBack} />
      <Scroll contentStyle={{ padding: space(2), gap: 12 }}>
        <Card>
          {!staff ? <Text style={type.small}>Loading…</Text> : staff.map((m, i) => (
            <View key={m.user_id}>
              {i ? <Divider /> : null}
              <Row style={{ justifyContent: 'space-between' }}>
                <View>
                  <Text style={type.h3}>{m.name || 'Unnamed'}</Text>
                  <Text style={type.small}>+91 {m.phone} · {m.role.replace('kitchen_', '')}</Text>
                </View>
                {m.role !== 'kitchen_owner' ? (
                  <Pressable accessibilityRole="button" onPress={() => remove(m)} hitSlop={8} accessibilityLabel={`Remove ${m.name}`}>
                    <Text style={{ color: colors.red, fontWeight: '700' }}>Remove</Text>
                  </Pressable>
                ) : <Text style={{ fontWeight: '700', color: colors.green }}>Owner</Text>}
              </Row>
            </View>
          ))}
        </Card>
        <Card>
          <Text style={[type.h3, { marginBottom: 10 }]}>Invite staff</Text>
          <Field label="Mobile number" value={form.phone} onChangeText={(v) => setForm({ ...form, phone: v.replace(/\D/g, '') })} keyboardType="phone-pad" maxLength={10} />
          <Field label="Name" value={form.name} onChangeText={(v) => setForm({ ...form, name: v })} />
          {ROLES.filter(([id]) => id !== 'kitchen_manager' || can.owner).map(([id, label, sub]) => (
            <Pressable key={id} onPress={() => setForm({ ...form, role: id })} accessibilityRole="radio" accessibilityState={{ selected: form.role === id }}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8 }}>
              <View style={{ width: 20, height: 20, borderRadius: 10, borderWidth: 2, borderColor: form.role === id ? colors.green : colors.border, alignItems: 'center', justifyContent: 'center' }}>
                {form.role === id ? <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: colors.green }} /> : null}
              </View>
              <View><Text style={type.body}>{label}</Text><Text style={type.small}>{sub}</Text></View>
            </Pressable>
          ))}
          <Btn title="Add staff member" onPress={add} loading={busy} disabled={form.phone.length !== 10} style={{ marginTop: 8 }} />
        </Card>
      </Scroll>
    </View>
  );
}

const HHMM = /^([01]\d|2[0-3]):[0-5]\d$/;

function WeeklyHoursCard() {
  const { kitchen, kitchenId, loadKitchens, toast } = useKitchen();
  const [days, setDays] = useState(kitchen.weekly_hours);
  const [busy, setBusy] = useState(false);
  const update = (i, patch) => setDays(days.map((d, j) => (j === i ? { ...d, ...patch } : d)));
  const bad = days.some((d) => !d.is_closed && (!HHMM.test(d.opens_at) || !HHMM.test(d.closes_at)));

  const save = async () => {
    setBusy(true);
    try {
      await api(`/v1/kitchen/kitchens/${kitchenId}/hours`, {
        method: 'PUT',
        body: { days: days.map(({ weekday, opens_at, closes_at, is_closed }) => ({ weekday, opens_at, closes_at, is_closed })) },
      });
      await loadKitchens();
      toast('Weekly hours saved', 'success');
    } catch (e) {
      toast(e.message, 'error');
    }
    setBusy(false);
  };

  return (
    <Card>
      <Text style={type.h3}>Weekly hours</Text>
      <Text style={[type.small, { marginBottom: 10 }]}>Campus time (IST). Closing time before opening time means it runs past midnight.</Text>
      {days.map((d, i) => (
        <Row key={d.weekday} style={{ gap: 8, marginBottom: 8 }}>
          <Text style={[type.body, { width: 40, fontWeight: '700' }]}>{d.day}</Text>
          {d.is_closed ? (
            <Text style={[type.body, { flex: 1, color: colors.red, fontWeight: '600' }]}>Closed all day</Text>
          ) : (
            <>
              <Field value={d.opens_at} onChangeText={(v) => update(i, { opens_at: v })} maxLength={5} accessibilityLabel={`${d.day} opens`}
                style={{ flex: 1, marginBottom: 0 }} inputStyle={{ height: 40, textAlign: 'center' }} error={HHMM.test(d.opens_at) ? null : ' '} />
              <Text style={type.small}>to</Text>
              <Field value={d.closes_at} onChangeText={(v) => update(i, { closes_at: v })} maxLength={5} accessibilityLabel={`${d.day} closes`}
                style={{ flex: 1, marginBottom: 0 }} inputStyle={{ height: 40, textAlign: 'center' }} error={HHMM.test(d.closes_at) ? null : ' '} />
            </>
          )}
          <Chip label={d.is_closed ? 'Open' : 'Close'} onPress={() => update(i, { is_closed: !d.is_closed })} />
        </Row>
      ))}
      <Btn title="Save weekly hours" small onPress={save} loading={busy} disabled={bad} style={{ marginTop: 6 }} />
    </Card>
  );
}

function ClosuresCard() {
  const { kitchen, kitchenId, loadKitchens, toast } = useKitchen();
  const [date, setDate] = useState('');
  const [reason, setReason] = useState('Holiday');
  const [busy, setBusy] = useState(false);
  const call = async (path, opts, msg) => {
    setBusy(true);
    try {
      await api(path, opts);
      await loadKitchens();
      toast(msg, 'success');
      setDate('');
    } catch (e) {
      toast(e.message, 'error');
    }
    setBusy(false);
  };
  return (
    <Card>
      <Text style={type.h3}>Holidays & closed days</Text>
      <Text style={[type.small, { marginBottom: 10 }]}>Exams, festivals or counter maintenance. Students see the reason and when you reopen.</Text>
      {kitchen.closures.length === 0 ? <Text style={[type.small, { marginBottom: 10 }]}>No upcoming closures.</Text> : kitchen.closures.map((c) => (
        <Row key={c.id} style={{ justifyContent: 'space-between', paddingVertical: 6 }}>
          <Text style={type.body}>📅 {c.date} · {c.reason}</Text>
          <Pressable accessibilityRole="button" onPress={() => call(`/v1/kitchen/kitchens/${kitchenId}/closures/${c.id}`, { method: 'DELETE' }, 'Closure removed')}
            hitSlop={8} accessibilityLabel={`Remove closure on ${c.date}`}>
            <Text style={{ color: colors.red, fontWeight: '700' }}>Remove</Text>
          </Pressable>
        </Row>
      ))}
      <Row style={{ gap: 8, alignItems: 'flex-start' }}>
        <Field label="Date (YYYY-MM-DD)" value={date} onChangeText={setDate} maxLength={10} placeholder="2026-11-01" style={{ flex: 1 }} />
        <Field label="Reason" value={reason} onChangeText={setReason} maxLength={120} style={{ flex: 1 }} />
      </Row>
      <Row style={{ gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
        {['Holiday', 'Exam day', 'Festival', 'Maintenance'].map((r) => <Chip key={r} label={r} active={reason === r} onPress={() => setReason(r)} />)}
      </Row>
      <Btn title="Add closed day" small variant="secondary" loading={busy} disabled={!/^\d{4}-\d{2}-\d{2}$/.test(date)}
        onPress={() => call(`/v1/kitchen/kitchens/${kitchenId}/closures`, { method: 'POST', body: { date, reason } }, 'Closed day added')} />
    </Card>
  );
}

export function SettingsScreen({ onBack }) {
  const { kitchen, kitchenId, loadKitchens, toast } = useKitchen();
  const [f, setF] = useState({
    counter_location: kitchen.counter_location, description: kitchen.description, emoji: kitchen.emoji,
    prep_minutes: String(kitchen.base_prep_minutes),
  });
  const [busy, setBusy] = useState(false);
  const set = (k) => (v) => setF({ ...f, [k]: v });
  const save = async () => {
    setBusy(true);
    try {
      await api(`/v1/kitchen/kitchens/${kitchenId}`, { method: 'PATCH', body: { ...f, prep_minutes: parseInt(f.prep_minutes, 10) || 15 } });
      await loadKitchens();
      toast('Settings saved', 'success');
      onBack();
    } catch (e) {
      toast(e.message, 'error');
    }
    setBusy(false);
  };
  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <TopBar title="Kitchen settings" onBack={onBack} />
      <Scroll contentStyle={{ padding: space(2), gap: 12 }}>
        <WeeklyHoursCard />
        <ClosuresCard />
        <Card>
          <Field label="Default prep time (minutes)" value={f.prep_minutes} onChangeText={(v) => set('prep_minutes')(v.replace(/\D/g, ''))} keyboardType="number-pad" />
        </Card>
        <Card>
          <Field label="Pickup counter location" value={f.counter_location} onChangeText={set('counter_location')} />
          <Field label="Description" value={f.description} onChangeText={set('description')} />
          <Field label="Icon" value={f.emoji} onChangeText={set('emoji')} maxLength={4} inputStyle={{ fontSize: 24 }} />
        </Card>
        <Btn title="Save settings" onPress={save} loading={busy} />
      </Scroll>
    </View>
  );
}

export function MoreScreen() {
  const { kitchen, can, signOut, user, kitchens, setKitchenId, confirm } = useKitchen();
  const [page, setPage] = useState(null);
  if (page === 'reports') return <ReportsScreen onBack={() => setPage(null)} />;
  if (page === 'staff') return <StaffScreen onBack={() => setPage(null)} />;
  if (page === 'settings') return <SettingsScreen onBack={() => setPage(null)} />;

  const Item = ({ icon, label, sub, onPress }) => (
    <Pressable onPress={onPress} accessibilityRole="button" style={{ flexDirection: 'row', alignItems: 'center', gap: 14, paddingVertical: 14 }}>
      <Text style={{ fontSize: 20, width: 28, textAlign: 'center' }}>{icon}</Text>
      <View style={{ flex: 1 }}><Text style={[type.body, { fontWeight: '600' }]}>{label}</Text>{sub ? <Text style={type.small}>{sub}</Text> : null}</View>
      <Text style={{ color: colors.faint, fontSize: 18 }}>›</Text>
    </Pressable>
  );
  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <View style={{ backgroundColor: colors.green, paddingTop: space(5), padding: space(2) }}>
        <Text style={{ color: '#fff', fontSize: 20, fontWeight: '900' }}>{kitchen.emoji} {kitchen.name}</Text>
        <Text style={{ color: '#CDE9D6' }}>{kitchen.college.name}</Text>
        <Text style={{ color: '#CDE9D6', marginTop: 4 }}>{user.name} · {kitchen.my_role.replace('kitchen_', '')}</Text>
      </View>
      <Scroll contentStyle={{ padding: space(2), gap: 12 }}>
        <Card style={{ paddingVertical: 4 }}>
          {can.manage ? <Item icon="📊" label="Sales & reports" sub="Sales, payouts, peak hours, top items" onPress={() => setPage('reports')} /> : null}
          {can.manage ? <Item icon="👥" label="Staff & roles" onPress={() => setPage('staff')} /> : null}
          {can.manage ? <Item icon="⚙️" label="Hours & settings" sub={`Today ${kitchen.opens_at ? `${kitchen.opens_at}–${kitchen.closes_at}` : 'closed'} · ${kitchen.base_prep_minutes} min prep`} onPress={() => setPage('settings')} /> : null}
          {kitchens.length > 1 ? <Item icon="🔁" label="Switch kitchen" onPress={() => setKitchenId(null)} /> : null}
          <Item icon="🚪" label="Log out" onPress={async () => (await confirm({ title: 'Log out?', confirmText: 'Log out', destructive: true })) && signOut()} />
        </Card>
        <Text style={[type.small, { textAlign: 'center' }]}>Need help? Contact CampusBite partner support.</Text>
      </Scroll>
    </View>
  );
}

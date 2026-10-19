import { useEffect, useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, Text, View } from 'react-native';
import { api } from '../api';
import { useKitchen } from '../store';
import { colors, radius, space, type } from '../theme';
import { Btn, Card, Chip, Field, Row, Scroll, TopBar } from '../ui';

export function Login() {
  const { signIn } = useKitchen();
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [step, setStep] = useState('phone');
  const [devCode, setDevCode] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const request = async () => {
    setError(null);
    if (!/^[6-9]\d{9}$/.test(phone)) return setError('Enter a valid 10-digit mobile number');
    setBusy(true);
    try {
      const r = await api('/v1/auth/otp/request', { method: 'POST', body: { phone } });
      setDevCode(r.dev_code || null);
      setStep('otp');
    } catch (e) {
      setError(e.message);
    }
    setBusy(false);
  };
  const verify = async () => {
    setError(null);
    setBusy(true);
    try {
      await signIn(await api('/v1/auth/otp/verify', { method: 'POST', body: { phone, code } }));
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1, backgroundColor: colors.green }}>
      <View style={{ paddingTop: space(8), paddingHorizontal: space(3), paddingBottom: space(4) }}>
        <Text style={{ fontSize: 28, fontWeight: '900', color: colors.yellow }}>campusbite</Text>
        <Text style={{ color: '#fff', fontSize: 18, fontWeight: '700', marginTop: 4 }}>Kitchen Partner</Text>
        <Text style={{ color: '#CDE9D6', marginTop: 6 }}>Manage orders, menu and pickups for your campus kitchen.</Text>
      </View>
      <View style={{ flex: 1, backgroundColor: colors.surface, borderTopLeftRadius: 28, borderTopRightRadius: 28, padding: space(3) }}>
        {step === 'phone' ? (
          <>
            <Text style={type.h2}>Staff login</Text>
            <Text style={[type.small, { marginBottom: space(3) }]}>Owners, managers, cashiers and cooks sign in with their mobile number.</Text>
            <Field label="Mobile number" keyboardType="phone-pad" maxLength={10} value={phone} placeholder="10-digit mobile"
              onChangeText={(t) => setPhone(t.replace(/\D/g, ''))} error={error} onSubmitEditing={request} autoFocus />
            <Btn title="Send OTP" onPress={request} loading={busy} disabled={phone.length !== 10} />
          </>
        ) : (
          <>
            <Text style={type.h2}>Enter OTP</Text>
            <Text style={[type.small, { marginBottom: space(2) }]}>
              Sent to +91 {phone}. <Text style={{ color: colors.green, fontWeight: '700' }} onPress={() => setStep('phone')}>Change</Text>
            </Text>
            {devCode ? (
              <View style={{ backgroundColor: colors.yellowSoft, padding: 10, borderRadius: radius.sm, marginBottom: 12 }}>
                <Text style={type.small}>Local test mode — OTP is <Text style={{ fontWeight: '800', color: colors.text }}>{devCode}</Text></Text>
              </View>
            ) : null}
            <Field label="OTP" keyboardType="number-pad" maxLength={6} value={code} onChangeText={(t) => setCode(t.replace(/\D/g, ''))}
              error={error} onSubmitEditing={verify} inputStyle={{ letterSpacing: 8, fontSize: 22, textAlign: 'center' }} autoFocus />
            <Btn title="Verify" onPress={verify} loading={busy} disabled={code.length < 6} />
          </>
        )}
      </View>
    </KeyboardAvoidingView>
  );
}

export function RegisterKitchen({ onBack }) {
  const { loadKitchens, setKitchenId, toast, user } = useKitchen();
  const [colleges, setColleges] = useState([]);
  const [form, setForm] = useState({ college_id: null, name: '', cuisine: '', counter_location: '', description: '', fssai_number: '', owner_name: user?.name || '' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const set = (k) => (v) => setForm({ ...form, [k]: v });
  useEffect(() => {
    api('/v1/colleges').then((r) => setColleges(r.items)).catch(() => {});
  }, []);

  const submit = async () => {
    setError(null);
    if (!form.college_id) return setError('Choose your college');
    if (form.name.trim().length < 2) return setError('Enter your kitchen name');
    setBusy(true);
    try {
      const k = await api('/v1/kitchens/register', { method: 'POST', body: { ...form, fssai_number: form.fssai_number || null } });
      await loadKitchens();
      setKitchenId(k.id);
      toast('Application submitted for approval', 'success');
    } catch (e) {
      setError(e.message);
    }
    setBusy(false);
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <TopBar title="Register your kitchen" subtitle="CampusBite reviews every kitchen before it goes live" onBack={onBack} />
      <Scroll contentStyle={{ padding: space(2), gap: 12 }}>
        <Card>
          <Text style={[type.h3, { marginBottom: 10 }]}>1. Choose college</Text>
          <View style={{ gap: 8 }}>
            {colleges.map((c) => (
              <Pressable key={c.id} onPress={() => set('college_id')(c.id)} accessibilityRole="radio" accessibilityState={{ selected: form.college_id === c.id }}
                style={{ padding: 12, borderRadius: radius.md, borderWidth: 1.5, borderColor: form.college_id === c.id ? colors.green : colors.border, backgroundColor: form.college_id === c.id ? colors.greenSoft : '#fff' }}>
                <Text style={type.h3}>{c.name}</Text>
                <Text style={type.small}>{c.address}</Text>
              </Pressable>
            ))}
          </View>
        </Card>
        <Card>
          <Text style={[type.h3, { marginBottom: 10 }]}>2. Kitchen details</Text>
          {!user?.name ? <Field label="Your name" value={form.owner_name} onChangeText={set('owner_name')} /> : null}
          <Field label="Kitchen name *" value={form.name} onChangeText={set('name')} placeholder="e.g. Campus Canteen" />
          <Field label="Cuisine" value={form.cuisine} onChangeText={set('cuisine')} placeholder="e.g. Snacks • Chai • Thali" />
          <Field label="Pickup counter location" value={form.counter_location} onChangeText={set('counter_location')} placeholder="e.g. Ground floor, Block A" />
          <Field label="Short description" value={form.description} onChangeText={set('description')} />
          <Field label="FSSAI registration number" value={form.fssai_number} onChangeText={set('fssai_number')} keyboardType="number-pad" />
          {error ? <Text style={{ color: colors.red, marginBottom: 10 }}>{error}</Text> : null}
          <Btn title="Submit for approval" onPress={submit} loading={busy} />
        </Card>
      </Scroll>
    </View>
  );
}

export function KitchenPicker() {
  const { kitchens, setKitchenId, signOut, user } = useKitchen();
  const [registering, setRegistering] = useState(false);
  if (registering) return <RegisterKitchen onBack={() => setRegistering(false)} />;
  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <View style={{ backgroundColor: colors.green, paddingTop: space(6), padding: space(2.5) }}>
        <Text style={{ color: colors.yellow, fontWeight: '900', fontSize: 22 }}>campusbite kitchen</Text>
        <Text style={{ color: '#fff', marginTop: 4 }}>Hi {user?.name || user?.phone}</Text>
      </View>
      <Scroll contentStyle={{ padding: space(2), gap: 12 }}>
        {kitchens?.length ? <Text style={type.label}>Your kitchens</Text> : (
          <Card>
            <Text style={type.h3}>You’re not linked to a kitchen yet</Text>
            <Text style={[type.small, { marginTop: 4 }]}>Register your kitchen, or ask your kitchen owner to add your number as staff.</Text>
          </Card>
        )}
        {(kitchens || []).map((k) => (
          <Card key={k.id} onPress={() => setKitchenId(k.id)}>
            <Row style={{ gap: 12 }}>
              <Text style={{ fontSize: 32 }}>{k.emoji}</Text>
              <View style={{ flex: 1 }}>
                <Text style={type.h3}>{k.name}</Text>
                <Text style={type.small}>{k.college.name}</Text>
                <Text style={[type.small, { fontWeight: '700', color: k.status === 'APPROVED' ? colors.green : '#9A6700' }]}>
                  {k.status} · {k.my_role.replace('kitchen_', '')}
                </Text>
              </View>
              <Text style={{ fontSize: 20, color: colors.faint }}>›</Text>
            </Row>
          </Card>
        ))}
        <Btn title="Register a new kitchen" variant="secondary" icon="＋" onPress={() => setRegistering(true)} />
        <Btn title="Log out" variant="ghost" onPress={signOut} />
      </Scroll>
    </View>
  );
}

export function StatusGate() {
  const { kitchen, setKitchenId, loadKitchens, kitchens } = useKitchen();
  const [checking, setChecking] = useState(false);
  const msg = {
    PENDING: ['⏳', 'Awaiting approval', 'CampusBite is reviewing your kitchen details and documents. You can set up your menu meanwhile — it goes live once approved.'],
    REJECTED: ['❌', 'Application not approved', kitchen.status_reason || 'Contact CampusBite support for details.'],
    SUSPENDED: ['⛔', 'Kitchen suspended', kitchen.status_reason || 'New orders are paused. Contact CampusBite support.'],
  }[kitchen.status];
  return (
    <View style={{ flex: 1, backgroundColor: colors.bg, padding: space(3), justifyContent: 'center' }}>
      <Card style={{ alignItems: 'center', padding: space(4) }}>
        <Text style={{ fontSize: 56 }}>{msg[0]}</Text>
        <Text style={[type.h2, { marginTop: 12, textAlign: 'center' }]}>{msg[1]}</Text>
        <Text style={[type.body, { marginTop: 8, textAlign: 'center', color: colors.muted }]}>{msg[2]}</Text>
        <Text style={[type.small, { marginTop: 16 }]}>{kitchen.emoji} {kitchen.name} · {kitchen.college.name}</Text>
        <Btn title="Check status" loading={checking} style={{ marginTop: 20, alignSelf: 'stretch' }}
          onPress={async () => { setChecking(true); await loadKitchens().catch(() => {}); setChecking(false); }} />
        {kitchens.length > 1 ? <Btn title="Switch kitchen" variant="ghost" onPress={() => setKitchenId(null)} /> : null}
      </Card>
    </View>
  );
}
